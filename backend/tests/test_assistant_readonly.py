import importlib
import json
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from app import recommendations, models
from tests.assistant_fixtures import assistant_fixture, business_snapshot


class AssistantReadonlyTests(unittest.TestCase):
    def setUp(self):
        try:
            self.readonly = importlib.import_module("app.assistant.readonly")
        except ModuleNotFoundError:
            self.fail("Assistant read-only tools have not been implemented")
        self.f = assistant_fixture(self)

    def execute(self, name, args=None):
        return self.readonly.execute_read_tool(
            self.f.db, self.f.principal, self.f.context, name, args or {}
        )

    def test_search_filters_hidden_missing_and_has_bounded_paging(self):
        page = self.execute("search_media", {"limit": 50})
        self.assertEqual(page["total"], 62)
        self.assertEqual(len(page["items"]), 50)
        self.assertTrue(page["has_more"])
        ids = {row["id"] for row in page["items"]}
        self.assertNotIn(3, ids)
        self.assertNotIn(4, ids)
        tail = self.execute("search_media", {"limit": 50, "offset": 50})
        self.assertEqual(len(tail["items"]), 12)
        self.assertFalse(tail["has_more"])
        with self.assertRaises(HTTPException) as caught:
            self.execute("search_media", {"limit": 51})
        self.assertEqual(caught.exception.status_code, 422)

    def test_queries_do_not_write_business_tables(self):
        before = business_snapshot(self.f.engine)
        for name, args in [
            ("search_media", {"query": "温馨"}),
            ("get_media_detail", {"media_id": 1}),
            ("get_library_stats", {}),
            ("list_tags", {}),
            ("list_folders", {}),
            ("list_duplicate_candidates", {}),
            ("recommend_media", {"media_type": "audio"}),
        ]:
            self.execute(name, args)
        self.assertEqual(business_snapshot(self.f.engine), before)
        self.f.db.expire_all()
        media = self.f.db.get(models.Media, 1)
        self.assertEqual(media.view_status, "unviewed")
        self.assertIsNone(media.last_opened_at)

    def test_detail_preserves_untrusted_text_but_excludes_paths_and_urls(self):
        detail = self.execute("get_media_detail", {"media_id": 1})
        encoded = json.dumps(detail, ensure_ascii=False)
        self.assertIn("<script>", detail["title"])
        self.assertNotIn("absolute_path", encoded)
        self.assertNotIn("relative_path", encoded)
        self.assertNotIn("source_url", encoded)
        self.assertNotIn("SECRET", encoded)
        self.assertNotIn("/private/", encoded)
        with self.assertRaises(HTTPException):
            self.execute("get_media_detail", {"media_id": 3})

    def test_windows_and_linux_folder_names_never_return_absolute_paths(self):
        result = self.execute("list_folders")
        self.assertEqual(
            [x["display_name"] for x in result["items"]], ["Books", "Audio"]
        )
        self.assertNotIn("/private/", json.dumps(result))
        self.assertNotIn("D:", json.dumps(result))

    def test_stats_and_duplicate_records_are_real_bounded_metadata(self):
        stats = self.execute("get_library_stats")
        self.assertEqual(
            stats,
            {
                "total": 62,
                "by_type": {"manga": 1, "audio": 1, "video": 60},
                "favorite_count": 1,
                "watched_count": 0,
            },
        )
        dup = self.execute("list_duplicate_candidates")
        self.assertEqual(dup["items"][0]["media_ids"], [1, 3])
        self.assertEqual(dup["items"][0]["score"], 98)
        self.assertNotIn("/private/", json.dumps(dup))

    def test_audio_recommendation_uses_metadata_and_avoid_tags(self):
        result = self.execute("recommend_media", {"media_type": "audio"})
        self.assertEqual(result["method"], "metadata_filter")
        self.assertEqual([x["id"] for x in result["items"]], [2])
        self.assertTrue(result["basis"])
        excluded = self.execute(
            "recommend_media", {"media_type": "audio", "avoid_tags": ["音乐"]}
        )
        self.assertEqual(excluded["items"], [])

    def test_manga_recommendation_skips_both_internal_model_calls(self):
        with (
            patch.object(
                recommendations,
                "call_deepseek",
                side_effect=AssertionError("assistant must not call nested AI"),
            ),
            patch.object(recommendations, "deepseek_configured", return_value=True),
        ):
            result = self.execute(
                "recommend_media", {"media_type": "manga", "query": "温馨"}
            )
        self.assertEqual(result["method"], "manga_retrieval")
        self.assertTrue(result["items"])
        self.assertTrue(result["basis"])

    def test_legacy_recommendation_default_still_uses_ai(self):
        replies = [
            '{"intent":"browse","slots":{},"positive_terms":[],"avoid_terms":[],"tone":[],"length":"any"}',
            '{"items":[{"id":1,"reason":"Synthetic AI reason"}]}',
        ]
        with (
            patch.object(recommendations, "deepseek_configured", return_value=True),
            patch.object(
                recommendations, "call_deepseek", side_effect=replies
            ) as called,
        ):
            result = recommendations.recommend_manga(self.f.db, "随便", 1, [], [])
        self.assertEqual(called.call_count, 2)
        self.assertTrue(result["ai_enabled"])
        self.assertEqual(result["recommendations"][0]["reason"], "Synthetic AI reason")

    def test_unknown_fields_or_generic_tools_are_rejected(self):
        for name, args in [
            ("terminal", {"command": "rm"}),
            ("search_media", {"sql": "select *"}),
            ("get_media_detail", {"media_id": 1, "user_id": 2}),
        ]:
            with self.assertRaises(HTTPException):
                self.execute(name, args)
