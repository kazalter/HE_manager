import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth, models


class AccessTokenPolicyTest(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
