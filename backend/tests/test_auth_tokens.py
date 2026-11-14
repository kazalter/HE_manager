import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, database, main, models


class AccessTokenPolicyTest(unittest.TestCase):
    def setUp(self):
        auth.invalidate_auth_cache()
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = models.User(
            username="tester",
            password_hash="not-used",
            is_admin=True,
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        auth.invalidate_auth_cache()
        self.db.close()
        self.engine.dispose()

    def add_token(self, raw: str, *, created_at: datetime, last_used_at=None, revoked=False):
        token = models.AccessToken(
            token_hash=auth.hash_token(raw),
            user_id=self.user.id,
            created_at=created_at,
            last_used_at=last_used_at,
            revoked=revoked,
        )
        self.db.add(token)
        self.db.commit()
        return token

    def test_last_used_timestamp_is_throttled(self):
        recent = datetime.utcnow()
        token = self.add_token("recent", created_at=recent, last_used_at=recent)

        user = auth.authenticate_access_token(self.db, "recent")
        self.assertEqual(user.id, self.user.id)
        self.db.refresh(token)
        self.assertEqual(token.last_used_at, recent)

        old_touch = recent - timedelta(seconds=auth.ACCESS_TOKEN_TOUCH_INTERVAL_SECONDS + 1)
        token.last_used_at = old_touch
        self.db.commit()
        auth.authenticate_access_token(self.db, "recent")
        self.db.refresh(token)
        self.assertGreater(token.last_used_at, old_touch)

    def test_cleanup_removes_expired_and_old_revoked_tokens(self):
        now = datetime.utcnow()
        expired = now - timedelta(days=auth.ACCESS_TOKEN_TTL_DAYS + 1)
        old_revoked = now - timedelta(days=auth.ACCESS_TOKEN_RETENTION_DAYS + 1)
        self.add_token("expired", created_at=expired)
        self.add_token("revoked", created_at=old_revoked, revoked=True)
        self.add_token("active", created_at=now)

        self.assertEqual(auth.cleanup_access_tokens(self.db, now=now), 2)
        hashes = {row.token_hash for row in self.db.query(models.AccessToken).all()}
        self.assertEqual(hashes, {auth.hash_token("active")})

    def test_query_tokens_only_work_for_binary_get_routes(self):
        allowed = [
            "/thumbnails/cover.jpg",
            "/stream/12",
            "/mobile/thumbnails/cover.jpg",
            "/mobile/stream/12",
            "/manga/12/page/3",
            "/mobile/manga/12/page/3",
            "/audio/12/track/3",
            "/external/favorites/12/cover",
            "/api/stream/12",
        ]
        for path in allowed:
            with self.subTest(path=path):
                self.assertTrue(auth.query_token_allowed("GET", path))

        denied = [
            ("GET", "/media"),
            ("GET", "/auth/me"),
            ("GET", "/audio/12/tracks"),
            ("GET", "/audio/12/track/3/lyrics"),
            ("POST", "/external/favorites/12/cover"),
        ]
        for method, path in denied:
            with self.subTest(path=path):
                self.assertFalse(auth.query_token_allowed(method, path))

    def test_request_token_cache_hits_and_invalidates(self):
        now = datetime.utcnow()
        self.add_token("cached-tok", created_at=now, last_used_at=now)

        first = auth.authenticate_request_token(self.db, "cached-tok")
        self.assertIsInstance(first, auth.CachedAuthUser)
        self.assertEqual(first.id, self.user.id)
        self.assertEqual(first.username, "tester")
        self.assertTrue(first.is_admin)
        self.assertTrue(first.is_active)
        self.assertEqual(first.created_at, self.user.created_at)

        with patch.object(self.db, "query", side_effect=AssertionError("should hit memory cache")):
            cached = auth.get_cached_request_user("cached-tok")
            self.assertEqual(cached, first)
            again = auth.authenticate_request_token(self.db, "cached-tok")
            self.assertEqual(again, first)

        # Revocation evicts immediately.
        self.assertTrue(auth.revoke_access_token(self.db, "cached-tok"))
        self.assertIsNone(auth.get_cached_request_user("cached-tok"))
        with self.assertRaises(HTTPException):
            auth.authenticate_request_token(self.db, "cached-tok")

    def test_request_token_cache_evicts_on_user_invalidation_and_cleanup(self):
        now = datetime.utcnow()
        self.add_token("user-tok", created_at=now, last_used_at=now)
        auth.authenticate_request_token(self.db, "user-tok")
        self.assertIsNotNone(auth.get_cached_request_user("user-tok"))

        auth.invalidate_user_auth_cache(self.user.id)
        self.assertIsNone(auth.get_cached_request_user("user-tok"))

        # Re-populate and verify cleanup clears cache when deleting rows.
        self.add_token("expired-tok", created_at=now - timedelta(days=auth.ACCESS_TOKEN_TTL_DAYS + 1))
        auth.authenticate_request_token(self.db, "user-tok")
        self.assertIsNotNone(auth.get_cached_request_user("user-tok"))
        deleted = auth.cleanup_access_tokens(self.db, now=now)
        self.assertEqual(deleted, 1)
        self.assertIsNone(auth.get_cached_request_user("user-tok"))

    def test_request_token_cache_respects_ttl_and_max_size(self):
        now = datetime.utcnow()
        self.add_token("ttl-tok", created_at=now, last_used_at=now)
        with patch("app.auth.time.monotonic", return_value=100.0):
            auth.authenticate_request_token(self.db, "ttl-tok")
        with patch("app.auth.time.monotonic", return_value=100.0 + auth.AUTH_CACHE_TTL_SECONDS + 1.0):
            self.assertIsNone(auth.get_cached_request_user("ttl-tok"))

        with patch("app.auth.AUTH_CACHE_MAX_SIZE", 2):
            for idx in range(3):
                raw = f"cap-{idx}"
                self.add_token(raw, created_at=now, last_used_at=now)
                auth.authenticate_request_token(self.db, raw)
            self.assertIsNone(auth.get_cached_request_user("cap-0"))
            self.assertIsNotNone(auth.get_cached_request_user("cap-1"))
            self.assertIsNotNone(auth.get_cached_request_user("cap-2"))

    def test_middleware_uses_cache_without_threadpool_and_thumbnails_cache_header(self):
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        models.Base.metadata.create_all(bind=test_engine)
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        db = TestSession()
        user = models.User(
            username="admin",
            password_hash="not-used",
            is_admin=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        raw_token = auth.create_access_token(db, user)
        db.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            thumb_file = os.path.join(tmpdir, "sample.jpg")
            with open(thumb_file, "wb") as fp:
                fp.write(b"\xff\xd8\xff\xd9")

            thumbnails_mount = next(
                route for route in main.app.routes if getattr(route, "name", None) == "thumbnails"
            )
            orig_app = thumbnails_mount.app
            thumbnails_mount.app = main.CachedThumbnailStaticFiles(directory=tmpdir)

            def override_get_db():
                session = TestSession()
                try:
                    yield session
                finally:
                    session.close()

            main.app.dependency_overrides[database.get_db] = override_get_db
            try:
                with patch.object(database, "SessionLocal", TestSession):
                    client = TestClient(main.app)
                    headers = {"Authorization": f"Bearer {raw_token}"}

                    # First request populates auth cache and returns Cache-Control on /thumbnails/.
                    resp1 = client.get(f"/thumbnails/sample.jpg?token={raw_token}")
                    self.assertEqual(resp1.status_code, 200)
                    self.assertEqual(resp1.headers.get("cache-control"), "private, max-age=86400")

                    # Second request hits auth cache without entering run_in_threadpool.
                    with patch("app.main.run_in_threadpool", side_effect=AssertionError("should not use threadpool")):
                        resp2 = client.get("/auth/me", headers=headers)
                        self.assertEqual(resp2.status_code, 200)
                        self.assertEqual(resp2.json()["username"], "admin")

                        resp3 = client.get(f"/thumbnails/sample.jpg?token={raw_token}")
                        self.assertEqual(resp3.status_code, 200)
                        self.assertEqual(resp3.headers.get("cache-control"), "private, max-age=86400")

                    # Updating the user via admin API invalidates the auth cache.
                    resp_upd = client.put(
                        f"/users/{user_id}",
                        json={"username": "admin2"},
                        headers=headers,
                    )
                    self.assertEqual(resp_upd.status_code, 200)
                    self.assertIsNone(auth.get_cached_request_user(raw_token))
            finally:
                main.app.dependency_overrides.pop(database.get_db, None)
                thumbnails_mount.app = orig_app
                test_engine.dispose()


if __name__ == "__main__":
    unittest.main()
