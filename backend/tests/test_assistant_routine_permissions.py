"""Reads survive stale Hermes turn IDs; routine writes remain owned and audited."""
import json
import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app import models
from app.assistant import identity, internal_app, proposals, schemas
from app.assistant.models import AssistantRun, AssistantAudit, AssistantProposal
from app.routers import assistant
from tests.assistant_fixtures import assistant_fixture, business_snapshot


class RoutinePermissionTests(unittest.TestCase):
    def setUp(self):
        self.f = assistant_fixture(self)
        app = FastAPI()
        app.include_router(assistant.router)

        def db():
            with self.f.factory() as local:
                yield local

        app.dependency_overrides[assistant.get_db] = db
        internal_app.app.dependency_overrides[internal_app.get_db] = db
        self.addCleanup(internal_app.app.dependency_overrides.clear)
        self.public = TestClient(app)
        self.private = TestClient(internal_app.app)
        self.addCleanup(self.public.close)
        self.addCleanup(self.private.close)

    def new_turn(self):
        old = self.f.db.get(AssistantRun, self.f.rid)
        old.status = 'completed'
        old.executor_exited_at = datetime.utcnow()
        old.deadline_at = datetime.utcnow() - timedelta(days=15)
        rid = str(uuid4())
        self.f.db.add(AssistantRun(id=rid, user_id=1, session_id=self.f.sid,
            client_request_id=str(uuid4()), input_hash='new', status='running', api_key_generation=1,
            deadline_at=datetime.utcnow() + timedelta(seconds=900)))
        self.f.db.commit()
        return rid

    def manage(self, operation, token=None):
        return self.public.post('/assistant/internal/manage-library', json={
            'context': self.f.context.model_dump(mode='json'), 'args': {'operation': operation}},
            headers={'Authorization': 'Bearer ' + (token or self.f.token)})

    def test_repeated_reads_with_fifteen_day_old_context_bind_to_current_run(self):
        rid = self.new_turn()
        before = business_snapshot(self.f.engine)
        for _ in range(5):
            response = self.private.post('/tools/search_media', json={
                'context': self.f.context.model_dump(mode='json'),
                'args': {'media_type': 'manga', 'view_status': 'unviewed', 'limit': 5}},
                headers={'Authorization': 'Bearer ' + self.f.token})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['context']['run_id'], rid)
            self.assertEqual(response.json()['result']['items'][0]['id'], 1)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantRun, self.f.rid).tool_results_json, '[]')
        self.assertEqual(len(json.loads(self.f.db.get(AssistantRun, rid).tool_results_json)), 5)
        self.assertEqual(business_snapshot(self.f.engine), before)

    def test_no_current_executor_and_stopped_session_do_not_revive_reads(self):
        rid = self.new_turn()
        row = self.f.db.get(AssistantRun, rid)
        row.stop_requested_at = datetime.utcnow()
        self.f.db.commit()
        with self.assertRaises(HTTPException):
            identity.current_read_context(self.f.db, self.f.principal, self.f.context)

    def test_foreign_session_or_identity_cannot_rebind(self):
        self.new_turn()
        for context in (schemas.ToolContext(session_id=uuid4(), run_id=self.f.rid),
                        schemas.ToolContext(session_id=self.f.sid, run_id=uuid4())):
            with self.assertRaises(HTTPException):
                identity.current_read_context(self.f.db, self.f.principal, context)
        foreign = schemas.ToolPrincipal(user_id=2, profile_name='he-user-2')
        with self.assertRaises(HTTPException):
            identity.current_read_context(self.f.db, foreign, self.f.context)

    def test_direct_metadata_action_applies_once_and_has_audit(self):
        operation = {'kind': 'media_update', 'media_id': 1,
                     'patch': {'rating': 5, 'favorite': False, 'view_status': 'viewed'}}
        first = self.manage(operation)
        self.assertEqual(first.status_code, 200, first.text)
        repeated = self.manage(operation)
        self.assertEqual(first.json(), repeated.json())
        self.assertEqual(first.json()['state'], 'applied')
        self.f.db.expire_all()
        row = self.f.db.get(models.Media, 1)
        self.assertEqual((row.rating, row.favorite, row.view_status), (5, False, 'viewed'))
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 1)
        self.assertEqual(self.f.db.query(AssistantProposal).one().state, 'applied')

    def test_batch_and_tag_rename_apply_without_pending_approval(self):
        result = self.manage({'kind': 'media_batch_update', 'items': [
            {'media_id': 1, 'patch': {'favorite': False}}, {'media_id': 2, 'patch': {'favorite': True}}]})
        self.assertEqual(result.status_code, 200, result.text)
        result = self.manage({'kind': 'tag_rename', 'tag_id': 1, 'name': '新名字'})
        self.assertEqual(result.status_code, 200, result.text)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Tag, 1).name, '新名字')
        self.assertEqual(self.f.db.query(AssistantProposal).filter_by(state='pending').count(), 0)

    def test_preview_stays_preview_and_stale_writes_are_not_silently_rebound(self):
        proposals.create_proposal(self.f.db, self.f.principal, self.f.context, 'media_update',
                                  {'media_id': 1, 'patch': {'rating': 5}})
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 4)
        self.new_turn()
        response = self.manage({'kind': 'media_update', 'media_id': 1, 'patch': {'rating': 5}})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 4)

    def test_destructive_kinds_and_non_tool_credentials_are_rejected(self):
        before = business_snapshot(self.f.engine)
        for kind in ('delete_media', 'drop_database', 'tag_merge', 'file_move', 'shell'):
            self.assertEqual(self.manage({'kind': kind}).status_code, 422)
        response = self.manage({'kind': 'media_update', 'media_id': 1, 'patch': {'rating': 5}}, token='x'*40)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(business_snapshot(self.f.engine), before)
