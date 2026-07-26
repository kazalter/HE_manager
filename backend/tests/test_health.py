import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import _public_path
from app.routers.root import healthz


class HealthRouteTest(unittest.TestCase):
    def test_health_checks_database_and_exposes_no_business_data(self):
        engine = create_engine("sqlite:///:memory:")
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            self.assertEqual(healthz(db), {"status": "ok", "database": "ok"})
        finally:
            db.close()
            engine.dispose()

    def test_health_is_public_with_or_without_api_prefix(self):
        self.assertTrue(_public_path("/healthz"))
        self.assertTrue(_public_path("/api/healthz"))
        self.assertFalse(_public_path("/media"))


if __name__ == "__main__":
    unittest.main()
