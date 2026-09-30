import os
import tempfile
import unittest
from unittest.mock import patch

from app.services.external.pawchive import client, normalize, provider, refs

IMAGE = "/ab/cd/" + "a" * 64 + ".jpg"
VIDEO = "/01/23/" + "b" * 64 + ".mp4"


def post(number=1):
    return {
        "id": str(number), "user": "456", "service": "fanbox",
        "title": "Example", "published": "2026-09-27T08:00:00",
        "file": {"name": "cover.jpg", "path": IMAGE},
        "attachments": [
            {"name": "duplicate.jpg", "path": IMAGE},
            {"name": "clip.mp4", "path": VIDEO},
            {"name": "archive.zip", "path": "/aa/bb/" + "c" * 64 + ".zip"},
        ],
    }


class NormalizeTests(unittest.TestCase):
    def test_main_file_order_dedup_and_unsupported(self):
        result = normalize.normalize_post(post(), detail=True)
        self.assertEqual(result["reported_attachment_count"], 3)
        self.assertEqual(result["playable_count"], 2)
        self.assertEqual([a["original_index"] for a in result["attachments"]], [0, 2, 3])
        self.assertEqual([a["media_type"] for a in result["attachments"]], ["image", "video", "unsupported"])
        self.assertIsNone(result["attachments"][-1]["stream_ref"])

    def test_list_entries_report_media_counts_without_attachments(self):
        result = normalize.normalize_post(post())
        self.assertEqual((result["image_count"], result["video_count"], result["playable_count"]), (1, 1, 2))
        self.assertEqual(result["attachments"], [])
        empty = normalize.normalize_post({**post(), "file": None, "attachments": [
            {"name": "archive.zip", "path": "/aa/bb/" + "c" * 64 + ".zip"}]})
        self.assertEqual((empty["image_count"], empty["video_count"], empty["playable_count"]), (0, 0, 0))

    def test_rejects_arbitrary_media_path(self):
        self.assertIsNone(normalize.file_type("http://127.0.0.1/private.mp4"))
        self.assertIsNone(normalize.file_type("/../../private.mp4"))


class ProviderTests(unittest.TestCase):
    def test_scope_bound_cursor_and_real_next_page_probe(self):
        def fake_get(path, params):
            return [post(i) for i in range(50)] if params["o"] == 0 else [post(50)]

        with patch.object(client, "get_json", side_effect=fake_get) as mocked:
            page = provider.list_posts(query="cat")
            self.assertEqual(len(page["items"]), 50)
            self.assertTrue(page["has_more"])
            self.assertEqual(mocked.call_count, 2)
            second = provider.list_posts(query="cat", cursor=page["next_cursor"])
            self.assertEqual(len(second["items"]), 1)
            self.assertFalse(second["has_more"])
            with self.assertRaises(client.PawchiveError):
                provider.list_posts(query="dog", cursor=page["next_cursor"])

    def test_global_tag_is_rejected(self):
        with self.assertRaises(client.PawchiveError):
            provider.list_posts(tag="tag")


class RefSecretTests(unittest.TestCase):
    def test_generated_secret_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HE_PAWCHIVE_STREAM_SECRET": ""}), \
                patch.object(refs, "SECRET_PATH", os.path.join(directory, "pawchive_stream.key")):
            first = refs._load_secret()
            self.assertGreaterEqual(len(first), 32)
            self.assertEqual(refs._load_secret(), first)
            if os.name != "nt":
                self.assertEqual(os.stat(refs.SECRET_PATH).st_mode & 0o777, 0o600)

    def test_configured_secret_wins(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HE_PAWCHIVE_STREAM_SECRET": "configured"}), \
                patch.object(refs, "SECRET_PATH", os.path.join(directory, "pawchive_stream.key")):
            self.assertEqual(refs._load_secret(), b"configured")
            self.assertFalse(os.path.exists(refs.SECRET_PATH))


if __name__ == "__main__":
    unittest.main()
