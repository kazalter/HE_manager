import importlib
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi import HTTPException
from app import models
from app.assistant.models import AssistantProposal, AssistantAudit, AssistantRun
from tests.assistant_fixtures import assistant_fixture, business_snapshot


class AssistantActionTests(unittest.TestCase):
    def setUp(self):
        try:
            self.proposals = importlib.import_module("app.assistant.proposals")
            self.actions = importlib.import_module("app.assistant.actions")
        except ModuleNotFoundError:
            self.fail("Confirmed assistant actions have not been implemented")
        from app.assistant import store

        self.store = store
        self.f = assistant_fixture(self)

    def create(self, media_id=1, patch=None):
        return self.proposals.create_proposal(
            self.f.db,
            self.f.principal,
            self.f.context,
            "media_update",
            {"media_id": media_id, "patch": patch or {"rating": 5}},
        )

    def preview(self, p):
        return self.proposals.get_owned_proposal(self.f.db, 1, p.id)

    def confirm(self, p, **kwargs):
        return self.actions.confirm_proposal(
            self.f.db, 1, p.id, self.preview(p).payload_hash, **kwargs
        )

    def test_preview_has_no_business_writes_and_confirmation_applies_only_allowed_fields(
        self,
    ):
        before = business_snapshot(self.f.engine)
        p = self.create(
            patch={
                "rating": 5,
                "favorite": False,
                "add_tags": [{"name": " 新标签 ", "namespace": " "}],
                "remove_tag_ids": [1],
            }
        )
        self.assertEqual(p.state, "pending")
        self.assertEqual(business_snapshot(self.f.engine), before)
        preview = self.preview(p)
        self.assertEqual(preview.before["rating"], 4)
        self.assertEqual(preview.after["rating"], 5)
        result = self.confirm(p)
        self.assertEqual(result.state, "applied")
        self.f.db.expire_all()
        row = self.f.db.get(models.Media, 1)
        self.assertEqual(row.rating, 5)
        self.assertFalse(row.favorite)
        self.assertEqual(
            [(t.name, t.namespace) for t in row.tags], [("新标签", "general")]
        )
        self.assertIsNone(row.last_opened_at)
        self.assertEqual(row.view_status, "unviewed")
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 1)

    def test_truncated_tag_preview_still_exposes_exact_additions_and_removals(self):
        media = self.f.db.get(models.Media, 1)
        for i in range(100, 160):
            tag = models.Tag(id=i, name="已有标签" + str(i), namespace="general")
            self.f.db.add(tag)
            media.tags.append(tag)
        self.f.db.commit()
        before = business_snapshot(self.f.engine)
        proposal = self.create(
            patch={"add_tags": [{"name": "新增标签"}], "remove_tag_ids": [159]}
        )
        preview = self.preview(proposal)
        self.assertTrue(preview.after["tags_truncated"])
        self.assertEqual(
            preview.after["add_tags"], [{"name": "新增标签", "namespace": "general"}]
        )
        self.assertEqual(
            preview.after["remove_tags"],
            [{"id": 159, "name": "已有标签159", "namespace": "general"}],
        )
        self.assertLessEqual(len(preview.after["tags"]), 50)
        self.assertEqual(business_snapshot(self.f.engine), before)

    def test_retry_does_not_refresh_snapshot_or_expiration(self):
        p = self.create()
        self.f.db.expire_all()
        original = self.f.db.get(AssistantProposal, str(p.id))
        before = original.before_json
        expires = original.expires_at
        self.f.db.get(models.Media, 1).rating = 1
        self.f.db.commit()
        retry = self.create()
        self.assertEqual(retry.id, p.id)
        self.f.db.expire_all()
        row = self.f.db.get(AssistantProposal, str(p.id))
        self.assertEqual(row.before_json, before)
        self.assertEqual(row.expires_at, expires)
        self.assertEqual(int((expires - row.created_at).total_seconds()), 300)

    def test_same_patch_different_targets_creates_distinct_proposals(self):
        a = self.create(1)
        b = self.create(2)
        self.assertNotEqual(a.id, b.id)
        self.assertNotEqual(self.preview(a).payload_hash, self.preview(b).payload_hash)

    def test_changed_old_value_marks_stale_and_does_not_overwrite(self):
        p = self.create()
        hash_value = self.preview(p).payload_hash
        self.f.db.get(models.Media, 1).rating = 2
        self.f.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.actions.confirm_proposal(self.f.db, 1, p.id, hash_value)
        self.assertEqual(caught.exception.status_code, 409)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "stale")
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 2)
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 0)

    def test_changed_tags_and_disappeared_target_are_stale(self):
        p = self.create(patch={"add_tags": [{"name": "测试"}]})
        self.f.db.get(models.Media, 1).tags = []
        self.f.db.commit()
        with self.assertRaises(HTTPException):
            self.confirm(p)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "stale")
        other = self.create(2)
        self.f.db.delete(self.f.db.get(models.Media, 2))
        self.f.db.commit()
        with self.assertRaises(HTTPException):
            self.confirm(other)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantProposal, str(other.id)).state, "stale")

    def test_rejected_and_expired_proposals_never_revive(self):
        p = self.create()
        rejected = self.proposals.reject_proposal(self.f.db, 1, p.id)
        self.assertEqual(rejected.state, "rejected")
        with self.assertRaises(HTTPException):
            self.confirm(p)
        other = self.create(2)
        self.f.db.get(AssistantProposal, str(other.id)).expires_at = (
            datetime.utcnow() - timedelta(seconds=1)
        )
        self.f.db.commit()
        with self.assertRaises(HTTPException):
            self.confirm(other)
        self.f.db.expire_all()
        self.assertEqual(
            self.f.db.get(AssistantProposal, str(other.id)).state, "expired"
        )
        self.assertEqual(self.create(2).state, "expired")

    def test_hash_mismatch_ownership_and_demoted_user_fail_closed(self):
        p = self.create()
        with self.assertRaises(HTTPException):
            self.actions.confirm_proposal(self.f.db, 1, p.id, "wrong")
        with self.assertRaises(HTTPException) as caught:
            self.proposals.get_owned_proposal(self.f.db, 2, p.id)
        self.assertEqual(caught.exception.status_code, 404)
        hash_value = self.preview(p).payload_hash
        self.f.db.get(models.User, 1).is_admin = False
        self.f.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.actions.confirm_proposal(self.f.db, 1, p.id, hash_value)
        self.assertEqual(caught.exception.status_code, 403)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 4)

    def test_simultaneous_confirmation_applies_once(self):
        p = self.create()
        hash_value = self.preview(p).payload_hash
        barrier = threading.Barrier(2)

        def worker():
            with self.f.factory() as db:
                barrier.wait(timeout=5)
                return self.actions.confirm_proposal(
                    db, 1, p.id, hash_value
                ).model_dump(mode="json")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(results[0], results[1])
        self.f.db.expire_all()
        self.assertEqual(
            self.f.db.query(AssistantAudit).filter_by(proposal_id=str(p.id)).count(), 1
        )

    def test_stop_commit_before_confirm_blocks_write(self):
        p = self.create()
        hash_value = self.preview(p).payload_hash
        committed = threading.Event()

        def stopper():
            with self.f.factory() as db:
                self.store.mark_run_stopping(db, 1, self.f.rid)
            committed.set()

        def confirmer():
            self.assertTrue(committed.wait(5))
            with self.f.factory() as db:
                with self.assertRaises(HTTPException) as caught:
                    self.actions.confirm_proposal(db, 1, p.id, hash_value)
                return caught.exception.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(stopper)
            b = pool.submit(confirmer)
            a.result(10)
            self.assertEqual(b.result(10), 409)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 4)
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 0)

    def test_confirm_commit_before_stop_preserves_result(self):
        p = self.create()
        hash_value = self.preview(p).payload_hash
        committed = threading.Event()

        def confirmer():
            with self.f.factory() as db:
                result = self.actions.confirm_proposal(db, 1, p.id, hash_value)
            committed.set()
            return result

        def stopper():
            self.assertTrue(committed.wait(5))
            with self.f.factory() as db:
                self.store.mark_run_stopping(db, 1, self.f.rid)

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(confirmer)
            b = pool.submit(stopper)
            self.assertEqual(a.result(10).state, "applied")
            b.result(10)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 5)
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "applied")
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 1)

    def test_clear_commit_before_late_proposal_blocks_creation(self):
        committed = threading.Event()

        def clearer():
            with self.f.factory() as db:
                self.store.mark_session_deleting(db, 1, self.f.sid)
            committed.set()

        def proposer():
            self.assertTrue(committed.wait(5))
            with self.f.factory() as db:
                with self.assertRaises(HTTPException):
                    self.proposals.create_proposal(
                        db,
                        self.f.principal,
                        self.f.context,
                        "media_update",
                        {"media_id": 1, "patch": {"rating": 5}},
                    )

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(clearer)
            b = pool.submit(proposer)
            a.result(10)
            b.result(10)
        self.assertEqual(self.f.db.query(AssistantProposal).count(), 0)

    def test_completed_run_pending_proposal_can_confirm(self):
        p = self.create()
        run = self.f.db.get(AssistantRun, self.f.rid)
        run.status = "completed"
        run.executor_exited_at = datetime.utcnow()
        self.f.db.commit()
        self.assertEqual(self.confirm(p).state, "applied")

    def test_old_credential_url_only_has_fingerprint_in_preview_and_audit(self):
        p = self.create(patch={"source_url": "https://safe.example/work/1"})
        raw = json.dumps(self.preview(p).model_dump(mode="json"), ensure_ascii=False)
        self.assertNotIn("SECRET", raw)
        self.assertNotIn("user:secret", raw)
        self.confirm(p)
        self.f.db.expire_all()
        audit = self.f.db.query(AssistantAudit).one()
        self.assertNotIn("SECRET", audit.changes_json)
        self.assertEqual(
            self.f.db.get(models.Media, 1).source_url, "https://safe.example/work/1"
        )

    def test_unsafe_empty_conflicting_and_oversize_changes_are_rejected(self):
        patches = [
            {"absolute_path": "/evil"},
            {"rating": 4},
            {"source_url": "https://example.test/?token=secret"},
            {"add_tags": [{"name": "温馨"}], "remove_tag_ids": [1]},
            {"add_tags": [{"name": str(i)} for i in range(21)]},
            {},
        ]
        for value in patches:
            with self.assertRaises(HTTPException):
                self.proposals.create_proposal(
                    self.f.db,
                    self.f.principal,
                    self.f.context,
                    "media_update",
                    {"media_id": 1, "patch": value},
                )
        self.assertEqual(self.f.db.query(AssistantProposal).count(), 0)

    def test_mid_transaction_failure_rolls_back_business_consumption_and_audit(self):
        p = self.create(patch={"rating": 5, "add_tags": [{"name": "新"}]})
        with patch.object(
            self.actions.tagging,
            "attach_tag",
            side_effect=RuntimeError("synthetic write failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.confirm(p)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 4)
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "pending")
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 0)

    def test_manual_source_change_is_stale_using_irreversible_fingerprint(self):
        p = self.create(patch={"source_url": "https://safe.example/new"})
        self.f.db.get(models.Media, 1).source_url = "https://another.example/work"
        self.f.db.commit()
        with self.assertRaises(HTTPException):
            self.confirm(p)
        self.f.db.expire_all()
        self.assertEqual(
            self.f.db.get(models.Media, 1).source_url, "https://another.example/work"
        )
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "stale")

    def test_public_route_accepts_only_hash_and_internal_tool_only_returns_ack(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers import assistant as routes
        from app.assistant import internal_app

        public = FastAPI()
        public.include_router(routes.router)

        def get_db():
            with self.f.factory() as db:
                yield db

        public.dependency_overrides[routes.get_db] = get_db
        public.dependency_overrides[routes.auth.require_admin] = lambda: self.f.db.get(
            models.User, 1
        )
        internal_app.app.dependency_overrides[internal_app.get_db] = get_db
        self.addCleanup(internal_app.app.dependency_overrides.clear)
        with TestClient(internal_app.app) as client:
            response = client.post(
                "/tools/propose_media_update",
                json={
                    "context": self.f.context.model_dump(mode="json"),
                    "args": {"media_id": 1, "patch": {"rating": 5}},
                },
                headers={"Authorization": "Bearer " + self.f.token},
            )
        self.assertEqual(response.status_code, 200, response.text)
        ack = response.json()["result"]
        self.assertEqual(
            set(ack),
            {
                "id",
                "kind",
                "target_id",
                "target_label",
                "state",
                "expires_at",
                "reason",
                "impact_count",
                "reversibility",
            },
        )
        p = self.proposals.get_owned_proposal(self.f.db, 1, ack["id"])
        with TestClient(public) as client:
            rejected = client.post(
                "/assistant/proposals/" + ack["id"] + "/confirm",
                json={"payload_hash": p.payload_hash, "patch": {"rating": 1}},
            )
            self.assertEqual(rejected.status_code, 422)
            confirmed = client.post(
                "/assistant/proposals/" + ack["id"] + "/confirm",
                json={"payload_hash": p.payload_hash},
            )
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 5)

    def test_running_run_past_deadline_cannot_confirm_before_watchdog_commit(self):
        p = self.create()
        self.f.db.get(AssistantRun, self.f.rid).deadline_at = (
            datetime.utcnow() - timedelta(seconds=1)
        )
        self.f.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.confirm(p)
        self.assertEqual(caught.exception.status_code, 409)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 4)
