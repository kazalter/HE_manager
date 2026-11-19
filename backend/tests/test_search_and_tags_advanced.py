import os
import tempfile
import unittest

from fastapi import Response
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.routers import media as media_routes
from app.services import media_fts


class SearchAndTagFiltersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db_path = os.path.join(self.tmp.name, "fts_test.db")
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        models.Base.metadata.create_all(bind=self.engine)
        media_fts.ensure_fts_table(self.engine)
        media_fts.install_fts_session_hooks()
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)

        self.folder = models.Folder(path=self.tmp.name, scan_mode="auto")
        self.db.add(self.folder)
        self.db.flush()

    def _add_media(self, title: str, *, artist: str | None = None, tags: list[tuple[str, str]] = ()):
        media = models.Media(
            folder_id=self.folder.id,
            title=title,
            artist=artist,
            relative_path=f"{title}.cbz",
            absolute_path=os.path.join(self.tmp.name, f"{title}.cbz"),
            media_type="manga",
            extension=".cbz",
            file_size=100,
            duplicate_status="unique",
            is_missing=False,
        )
        for name, namespace in tags:
            tag = self.db.query(models.Tag).filter_by(name=name, namespace=namespace).first()
            if not tag:
                tag = models.Tag(name=name, namespace=namespace)
                self.db.add(tag)
                self.db.flush()
            media.tags.append(tag)
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)
        return media

    def test_multi_tag_and_or_exclude_and_namespace_filters(self):
        m1 = self._add_media("Book One", tags=[("純愛", "general"), ("巨乳", "general"), ("Alice", "artist")])
        m2 = self._add_media("Book Two", tags=[("纯爱", "general"), ("NTR", "general"), ("Bob", "artist")])
        m3 = self._add_media("Book Three", tags=[("巨乳", "general"), ("CircleZ", "circle")])

        # Single tag backward compatibility (with trad/simp expansion)
        res_single = media_routes.list_media(Response(), tag="纯爱", db=self.db)
        self.assertEqual({m.id for m in res_single}, {m1.id, m2.id})

        # Multi-tag AND mode (default)
        res_and = media_routes.list_media(Response(), tags="纯爱,巨乳", tag_mode="all", db=self.db)
        self.assertEqual([m.id for m in res_and], [m1.id])

        # Multi-tag OR mode
        res_or = media_routes.list_media(Response(), tags="纯爱,巨乳", tag_mode="any", db=self.db)
        self.assertEqual({m.id for m in res_or}, {m1.id, m2.id, m3.id})

        # Exclude tags
        res_excl = media_routes.list_media(
            Response(), tags="纯爱", exclude_tags="NTR", db=self.db
        )
        self.assertEqual([m.id for m in res_excl], [m1.id])

        # Namespace filter
        res_ns = media_routes.list_media(Response(), tag_namespace="circle", db=self.db)
        self.assertEqual([m.id for m in res_ns], [m3.id])

        # Mobile endpoint supports the same multi-tag filters
        res_mob = media_routes.list_mobile_media(
            Response(), tags="纯爱,巨乳", tag_mode="any", exclude_tags="NTR", db=self.db
        )
        self.assertEqual({m.id for m in res_mob}, {m1.id, m3.id})

    def test_fts5_syncs_live_and_accelerates_cjk_latin_and_synonym_search(self):
        m1 = self._add_media(
            "[Alpha] 魔法少女の日常",
            artist="AuthorOne",
            tags=[("純愛", "general")],
        )
        m2 = self._add_media(
            "幼馴染と過ごす夏",
            artist="AuthorTwo",
            tags=[("ShortStory", "general")],
        )
        self.db.add(models.MangaMetadataProfile(
            media_id=m1.id,
            parsed_circle="MoonCircle",
            parody="BlueArchive",
        ))
        self.db.commit()

        # Verify FTS table is populated and ready.
        self.assertTrue(media_fts.fts_is_ready(self.db))
        fts_rows = self.db.execute(text("SELECT media_id FROM media_fts ORDER BY media_id")).fetchall()
        self.assertEqual([r[0] for r in fts_rows], [m1.id, m2.id])

        # CJK 1-char, 2-char, >=3-char searches
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="魔", db=self.db)], [m1.id])
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="魔法", db=self.db)], [m1.id])
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="魔法少女", db=self.db)], [m1.id])

        # Latin substring >= 3 chars (trigram FTS) & metadata profile match
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="Archiv", db=self.db)], [m1.id])
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="MoonCircle", db=self.db)], [m1.id])

        # Short <= 2-char ASCII gracefully skips FTS pre-filter and falls back to LIKE
        self.assertIsNone(media_fts.build_fts_match_expression("Al"))
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="Al", db=self.db)], [m1.id])

        # Synonym expansion via FTS + exact filter (青梅竹马 -> 幼馴染)
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="青梅竹马", db=self.db)], [m2.id])

        # Rebuild from scratch works idempotently
        self.assertEqual(media_fts.rebuild_media_fts(self.db), 0)
        self.assertEqual(media_fts.rebuild_media_fts(self.db, force=True), 2)

        # Updating title and deleting media stays synced
        m2.title = "Updated Title XYZ"
        self.db.commit()
        self.assertEqual([m.id for m in media_routes.list_media(Response(), search="XYZ", db=self.db)], [m2.id])
        self.db.delete(m2)
        self.db.commit()
        self.assertEqual(media_routes.list_media(Response(), search="XYZ", db=self.db), [])


if __name__ == "__main__":
    unittest.main()
