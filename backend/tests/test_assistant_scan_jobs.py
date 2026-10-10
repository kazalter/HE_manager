import importlib
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from app import models, scanner
from app.assistant.models import AssistantProposal, AssistantAudit
from tests.assistant_fixtures import assistant_fixture


class AssistantScanJobTests(unittest.TestCase):
    def setUp(self):
        try:
            self.proposals = importlib.import_module("app.assistant.proposals")
            self.actions = importlib.import_module("app.assistant.actions")
            self.jobs = importlib.import_module("app.assistant.scan_jobs")
        except ModuleNotFoundError:
            self.fail("Assistant scan jobs are not implemented")
        self.f = assistant_fixture(self)
        folder = self.f.root / "scan-folder"
        folder.mkdir()
        self.f.db.get(models.Folder, 1).path = str(folder)
        self.f.db.commit()
        session_patch = patch.object(self.jobs.database, "SessionLocal", self.f.factory)
        session_patch.start()
        self.addCleanup(session_patch.stop)
        self.queued = []
        self.addCleanup(self.release_queued)

    def release_queued(self):
        for _, folder_id, reservation in self.queued:
            scanner.release_folder_scan(folder_id, reservation)

    def create(self):
        return self.proposals.create_proposal(
            self.f.db, self.f.principal, self.f.context, "scan", {"folder_id": 1}
        )

    def confirm(self, p, enqueue=None):
        preview = self.proposals.get_owned_proposal(self.f.db, 1, p.id)
        return self.actions.confirm_proposal(
            self.f.db,
            1,
            p.id,
            preview.payload_hash,
            enqueue=enqueue or (lambda *args: self.queued.append(args)),
        )

    def test_only_explicit_confirmation_creates_one_job_and_one_audit(self):
        p = self.create()
        self.assertEqual(self.f.db.query(models.BackgroundJob).count(), 0)
        self.assertEqual(self.queued, [])
        result = self.confirm(p)
        again = self.confirm(p)
        self.assertEqual(result, again)
        self.assertEqual(result.state, "queued")
        self.assertEqual(len(self.queued), 1)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.query(models.BackgroundJob).count(), 1)
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 1)
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "queued")

    def test_simultaneous_confirmation_starts_only_one_scan(self):
        p = self.create()
        hash_value = self.proposals.get_owned_proposal(self.f.db, 1, p.id).payload_hash
        barrier = threading.Barrier(2)

        def confirm():
            with self.f.factory() as db:
                barrier.wait(timeout=5)
                return self.actions.confirm_proposal(
                    db,
                    1,
                    p.id,
                    hash_value,
                    enqueue=lambda *args: self.queued.append(args),
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: confirm(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.queued), 1)
        self.assertEqual(self.f.db.query(models.BackgroundJob).count(), 1)

    def test_scan_bool_result_and_exception_have_durable_terminal_snapshot(self):
        for outcome, status in [
            (True, "completed"),
            (False, "failed"),
            (RuntimeError("synthetic scanner failure"), "failed"),
        ]:
            if self.queued:
                from uuid import uuid4
                from app.assistant.models import AssistantRun
                from app.assistant.schemas import ToolContext

                rid = str(uuid4())
                self.f.db.add(
                    AssistantRun(
                        id=rid,
                        user_id=1,
                        session_id=self.f.sid,
                        client_request_id=str(uuid4()),
                        input_hash="fixture",
                        status="running",
                        deadline_at=datetime.utcnow() + timedelta(seconds=180),
                    )
                )
                self.f.db.commit()
                self.f.context = ToolContext(session_id=self.f.sid, run_id=rid)
            p = self.create()
            result = self.confirm(p)
            args = self.queued[-1]
            with patch.object(
                self.jobs.scanner,
                "scan_folder",
                side_effect=outcome if isinstance(outcome, Exception) else None,
                return_value=outcome,
            ) as scan:
                self.jobs.run_scan_job(*args)
            self.assertEqual(scan.call_count, 1)
            self.f.db.expire_all()
            self.assertEqual(
                self.jobs.get_owned_scan_job(self.f.db, 1, result.job_id).status, status
            )
            self.f.db.delete(self.f.db.get(models.BackgroundJob, result.job_id))
            self.f.db.commit()
            self.assertEqual(
                self.jobs.get_owned_scan_job(self.f.db, 1, result.job_id).status, status
            )
            reservation = scanner.reserve_folder_scan(args[1])
            self.assertIsNotNone(reservation)
            scanner.release_folder_scan(args[1], reservation)

    def test_queue_failure_is_failed_and_releases_reservation(self):
        p = self.create()

        def fail(*args):
            raise RuntimeError("synthetic queue failure")

        result = self.confirm(p, enqueue=fail)
        self.assertEqual(result.state, "failed")
        job = self.jobs.get_owned_scan_job(self.f.db, 1, result.job_id)
        self.assertEqual(job.status, "failed")
        reserved = scanner.reserve_folder_scan(1)
        self.assertIsNotNone(reserved)
        scanner.release_folder_scan(1, reserved)

    def test_storage_guard_and_existing_folder_reservation_block_queue(self):
        p = self.create()
        with patch.object(
            self.jobs.storage_guard,
            "ensure_folder_scannable",
            return_value=(False, "private path omitted"),
        ):
            with self.assertRaises(HTTPException) as caught:
                self.confirm(p)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(self.queued, [])
        reservation = scanner.reserve_folder_scan(1)
        try:
            with self.assertRaises(HTTPException) as caught:
                self.confirm(p)
            self.assertEqual(caught.exception.status_code, 409)
        finally:
            scanner.release_folder_scan(1, reservation)
        self.assertEqual(self.f.db.query(models.BackgroundJob).count(), 0)

    def test_folder_configuration_change_is_stale(self):
        p = self.create()
        self.f.db.get(models.Folder, 1).scan_mode = "manga"
        self.f.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.confirm(p)
        self.assertEqual(caught.exception.status_code, 409)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "stale")
        self.assertEqual(self.queued, [])

    def test_global_assistant_scan_and_capacity_rules_block_admission(self):
        p = self.create()
        self.f.db.add(
            models.BackgroundJob(
                job_id="already-running",
                kind="assistant_scan",
                status="running",
                payload_json="{}",
            )
        )
        self.f.db.commit()
        with self.assertRaises(HTTPException):
            self.confirm(p)
        self.f.db.delete(self.f.db.get(models.BackgroundJob, "already-running"))
        from app.services import job_lifecycle

        self.f.db.add(
            models.BackgroundJob(
                job_id="history",
                kind="assistant_scan",
                status="completed",
                payload_json="{}",
                finished_at=datetime.utcnow(),
            )
        )
        self.f.db.commit()
        with patch.object(job_lifecycle, "JOB_MAX_ENTRIES", 1):
            # Same pruning rule as existing registries: terminal history gives way.
            result = self.confirm(p)
        self.assertEqual(result.state, "queued")
        self.assertEqual(self.f.db.query(models.BackgroundJob).count(), 1)

    def test_restart_marks_interrupted_without_replaying_and_history_remains_owned(
        self,
    ):
        p = self.create()
        result = self.confirm(p)
        with patch.object(
            self.jobs.scanner,
            "scan_folder",
            side_effect=AssertionError("restart must not rescan"),
        ):
            self.assertEqual(self.jobs.recover_scan_jobs(), 1)
        job = self.jobs.get_owned_scan_job(self.f.db, 1, result.job_id)
        self.assertEqual(job.status, "interrupted")
        self.assertIn("部分", job.message)
        with self.assertRaises(HTTPException) as caught:
            self.jobs.get_owned_scan_job(self.f.db, 2, result.job_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_busy_final_status_retries_persistence_without_rescanning(self):
        p = self.create()
        result = self.confirm(p)
        original = self.jobs.persist_scan_status
        attempts = []

        def flaky(*args, **kwargs):
            if args[1] == "completed":
                attempts.append(1)
                if len(attempts) < 3:
                    raise OperationalError(
                        "UPDATE", {}, Exception("database is locked")
                    )
            return original(*args, **kwargs)

        with (
            patch.object(self.jobs, "persist_scan_status", side_effect=flaky),
            patch.object(self.jobs.scanner, "scan_folder", return_value=True) as scan,
        ):
            self.jobs.run_scan_job(*self.queued[0])
        self.assertEqual(scan.call_count, 1)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(
            self.jobs.get_owned_scan_job(self.f.db, 1, result.job_id).status,
            "completed",
        )

    def test_unavailable_final_status_is_explicit_and_scan_is_never_repeated(self):
        p = self.create()
        result = self.confirm(p)
        original = self.jobs.persist_scan_status

        def unavailable(*args, **kwargs):
            if args[1] == "completed":
                raise OperationalError("UPDATE", {}, Exception("database is locked"))
            return original(*args, **kwargs)

        with (
            patch.object(self.jobs, "persist_scan_status", side_effect=unavailable),
            patch.object(self.jobs.scanner, "scan_folder", return_value=True) as scan,
        ):
            self.jobs.run_scan_job(*self.queued[0])
        self.assertEqual(scan.call_count, 1)
        with self.assertRaises(HTTPException) as caught:
            self.jobs.get_owned_scan_job(self.f.db, 1, result.job_id)
        self.assertEqual(caught.exception.detail, "job_status_unavailable")
        reserved = scanner.reserve_folder_scan(1)
        self.assertIsNotNone(reserved)
        scanner.release_folder_scan(1, reserved)

    def test_expired_scan_is_consumed_even_when_storage_is_unavailable(self):
        p = self.create()
        self.f.db.get(AssistantProposal, str(p.id)).expires_at = (
            datetime.utcnow() - timedelta(seconds=1)
        )
        self.f.db.commit()
        with patch.object(
            self.jobs.storage_guard,
            "ensure_folder_scannable",
            return_value=(False, "unavailable"),
        ):
            with self.assertRaises(HTTPException) as caught:
                self.confirm(p)
        self.assertEqual(caught.exception.detail, "assistant_proposal_expired")
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "expired")

    def test_scan_transaction_failure_rolls_back_and_releases_reservation(self):
        p = self.create()
        from sqlalchemy import event

        def fail(*args):
            raise RuntimeError("synthetic audit failure")

        event.listen(AssistantAudit, "before_insert", fail)
        self.addCleanup(lambda: event.remove(AssistantAudit, "before_insert", fail))
        with self.assertRaises(RuntimeError):
            self.confirm(p)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.query(models.BackgroundJob).count(), 0)
        self.assertEqual(self.f.db.get(AssistantProposal, str(p.id)).state, "pending")
        self.assertEqual(self.queued, [])
        reserved = scanner.reserve_folder_scan(1)
        self.assertIsNotNone(reserved)
        scanner.release_folder_scan(1, reserved)
