import json
import unittest
from unittest.mock import patch

from app.services.external.pawchive import account, client


class PawchiveAccountTests(unittest.TestCase):
    def setUp(self):
        with account._sessions_lock:
            account._sessions.clear()

    def tearDown(self):
        with account._sessions_lock:
            account._sessions.clear()

    def test_login_keeps_session_per_he_user_and_returns_account_favorites(self):
        favorite = {"service": "fanbox", "id": "creator-7", "name": "Favorite author"}
        replies = [
            (200, [("Set-Cookie", "csrf=nonce; Path=/; HttpOnly")], b"login form"),
            (302, [("Set-Cookie", "session=opaque; Path=/; HttpOnly")], b""),
            (200, [("Content-Type", "application/json")], json.dumps([favorite]).encode()),
        ]
        calls = []

        def request(target, **kwargs):
            calls.append((target, kwargs))
            return replies.pop(0)

        with patch.object(client, "account_request", side_effect=request):
            result = account.login(42, "owner", "secret")

        self.assertTrue(result["connected"])
        self.assertEqual(result["items"][0]["creator_name"], "Favorite author")
        self.assertTrue(account.status(42)["connected"])
        self.assertFalse(account.status(43)["connected"])
        self.assertEqual(calls[1][1]["form"], {
            "location": "/favorites",
            "username": "owner",
            "password": "secret",
        })
        self.assertEqual(calls[2][1]["cookies"], {"csrf": "nonce", "session": "opaque"})

    def test_favorite_mutation_uses_fixed_account_endpoint_and_user_session(self):
        session = account.AccountSession(cookies={"session": "opaque"})
        with account._sessions_lock:
            account._sessions[42] = session

        with patch.object(client, "account_request", return_value=(204, [], b"")) as request:
            result = account.set_favorite(42, "fanbox", "creator-7", True)

        self.assertEqual(result, {
            "service": "fanbox",
            "creator_id": "creator-7",
            "favorite": True,
        })
        request.assert_called_once_with(
            "/api/v1/favorites/creator/fanbox/creator-7",
            method="POST",
            cookies={"session": "opaque"},
            form=None,
        )

    def test_account_request_rejects_non_allowlisted_paths(self):
        with self.assertRaises(client.PawchiveError) as raised:
            client.account_request("https://attacker.example/steal", method="GET")
        self.assertEqual(raised.exception.code, "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
