import json
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import (
    asmr_source,
    database,
    external_sources,
    manga_metadata,
    manga_retrievers,
    manga_vector,
    metadata_enrichment,
    models,
    recommendations,
)
from app.routers import system as system_routes
from app.services import external_metadata_backfill
from app.services.external import asmr as asmr_service
from app.services.external import wnacg as wnacg_service
from app.x_import import storage as x_storage


class MetadataEnrichmentTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        models.Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=self.engine,
        )
        self.patch_db = patch.object(database, "SessionLocal", self.Session)
        self.patch_db.start()

    def tearDown(self):
        self.patch_db.stop()
        self.engine.dispose()

    def test_parse_title_metadata_does_not_treat_bracketed_artist_as_parody(self):
        parsed = manga_metadata.parse_title_metadata(
            "[CircleA (ArtistB)] Clean Title (Original) (C103) [中文]"
        )
        self.assertEqual(parsed["parsed_circle"], "CircleA")
        self.assertEqual(parsed["parsed_artist"], "ArtistB")
        self.assertEqual(parsed["parsed_title"], "Clean Title (Original) (C103)")
        self.assertEqual(parsed["parody"], "Original")
        self.assertEqual(parsed["language"], "中文")

        parsed_no_parody = manga_metadata.parse_title_metadata(
            "[CircleA (ArtistB)] Standalone Title [DL版]"
        )
        self.assertEqual(parsed_no_parody["parsed_circle"], "CircleA")
        self.assertEqual(parsed_no_parody["parsed_artist"], "ArtistB")
        self.assertIsNone(parsed_no_parody["parody"])

    def test_extract_hashtags_ignores_urls_and_numeric_tags(self):
        tags = metadata_enrichment.extract_hashtags(
            "Check https://example.com/p#frag #illustration #原神 #123 #AIArt #illustration"
        )
        self.assertEqual(tags, ["illustration", "原神", "AIArt"])

    def test_enrich_manga_media_reads_source_txt_and_sidecar_and_skips_scanlation_noise(self):
        db = self.Session()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                book_dir = os.path.join(tmp, "book1")
                os.makedirs(book_dir, exist_ok=True)
                with open(os.path.join(book_dir, "source.txt"), "w", encoding="utf-8") as f:
                    f.write("https://www.wnacg.com/photos-index-aid-987654.html\n")
                metadata_enrichment.write_metadata_json(
                    book_dir,
                    {
                        "source_site": "wnacg",
                        "category": "同人誌",
                        "tags": ["纯爱", "黑丝", "白杨汉化组", "纯爱"],
                        "intro": "甜蜜治愈的同人作品",
                    },
                )

                folder = models.Folder(path=tmp, scan_mode="manga")
                media = models.Media(
                    folder=folder,
                    title="[CircleOne (ArtistOne)] Sweet Story (Blue Archive) [中国翻訳]",
                    relative_path="book1",
                    absolute_path=book_dir,
                    media_type="manga",
                    extension=".dir",
                    file_size=2048,
                    page_count=32,
                )
                db.add_all([folder, media])
                db.commit()

                res = metadata_enrichment.enrich_manga_media(db, media)
                db.commit()
                db.refresh(media)

                self.assertEqual(media.source_site, "wnacg")
                self.assertEqual(media.source_url, "https://www.wnacg.com/photos-index-aid-987654.html")
                self.assertEqual(media.artist, "ArtistOne")
                self.assertGreater(res["tags_attached"], 0)

                tag_ns = {t.name: t.namespace for t in media.tags}
                self.assertEqual(tag_ns.get("ArtistOne"), "artist")
                self.assertEqual(tag_ns.get("CircleOne"), "circle")
                self.assertEqual(tag_ns.get("Blue Archive"), "parody")
                self.assertEqual(tag_ns.get("纯爱"), "general")
                self.assertEqual(tag_ns.get("黑丝"), "general")
                self.assertNotIn("白杨汉化组", tag_ns)

                self.assertIsNotNone(media.metadata_profile)
                self.assertEqual(media.metadata_profile.analyzer_version, manga_metadata.ANALYZER_VERSION)
                self.assertFalse(
                    manga_metadata.needs_metadata(
                        media,
                        sidecar=metadata_enrichment.read_metadata_json(book_dir),
                    )
                )
        finally:
            db.close()

    def test_enrich_x_media_and_storage_upsert_and_standalone_untouched(self):
        db = self.Session()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = models.Folder(path=tmp, scan_mode="auto")
                db.add(folder)
                db.commit()

                img_path = os.path.join(tmp, "20260101_111.jpg")
                with open(img_path, "wb") as f:
                    f.write(b"fake-img")

                post = models.XPost(
                    tweet_id="111",
                    url="https://x.com/painter_x/status/111",
                    author_screen_name="painter_x",
                    full_text="New art! #OC #猫耳 #999",
                    media_count=1,
                    has_media=True,
                )
                db.add(post)
                db.flush()

                x_item = models.XMediaItem(
                    post_id=post.id,
                    media_index=0,
                    media_type="photo",
                    remote_url="https://pbs.twimg.com/media/111.jpg",
                    local_path=img_path,
                    width=100,
                    height=100,
                )
                db.add(x_item)
                db.flush()

                media = x_storage.upsert_library_media(
                    x_item,
                    post,
                    folder,
                    img_path,
                    8,
                    tmp,
                    db,
                )
                db.commit()
                db.refresh(media)

                self.assertEqual(media.artist, "painter_x")
                tag_ns = {t.name: t.namespace for t in media.tags}
                self.assertEqual(tag_ns.get("painter_x"), "artist")
                self.assertEqual(tag_ns.get("OC"), "general")
                self.assertEqual(tag_ns.get("猫耳"), "general")
                self.assertNotIn("999", tag_ns)

                standalone = models.Media(
                    folder_id=folder.id,
                    title="Vacation Clip",
                    relative_path="clip.mp4",
                    absolute_path=os.path.join(tmp, "clip.mp4"),
                    media_type="video",
                    extension=".mp4",
                    file_size=1024,
                )
                db.add(standalone)
                db.commit()

                res_standalone = metadata_enrichment.enrich_media_metadata(db, standalone)
                self.assertEqual(res_standalone.get("tags_attached", 0), 0)
                self.assertIsNone(standalone.artist)
                self.assertEqual(len(standalone.tags), 0)
        finally:
            db.close()

    def test_enrich_audio_media_from_sidecar_and_stats_backfill(self):
        db = self.Session()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio_dir = os.path.join(tmp, "RJ1495967")
                os.makedirs(audio_dir, exist_ok=True)
                metadata_enrichment.write_metadata_json(
                    audio_dir,
                    {
                        "source_site": "asmr",
                        "external_id": "RJ1495967",
                        "circle": "音声社团",
                        "vas": ["声优A", "声优B"],
                        "tags": ["耳搔", "治愈"],
                        "release": "2026-01-01",
                    },
                )
                folder = models.Folder(path=tmp, scan_mode="audio")
                audio = models.Media(
                    folder=folder,
                    title="RJ1495967 治愈音声",
                    relative_path="RJ1495967",
                    absolute_path=audio_dir,
                    media_type="audio",
                    extension=".dir",
                    file_size=4096,
                    source_site="asmr",
                    source_url="https://asmr.one/work/RJ1495967",
                )
                db.add_all([folder, audio])
                db.commit()

                res = system_routes.run_metadata_backfill(limit=100, force=False, db=db)
                self.assertGreaterEqual(res["updated"], 1)
                db.refresh(audio)

                self.assertEqual(audio.artist, "声优A, 声优B")
                tag_ns = {t.name: t.namespace for t in audio.tags}
                self.assertEqual(tag_ns.get("声优A"), "artist")
                self.assertEqual(tag_ns.get("声优B"), "artist")
                self.assertEqual(tag_ns.get("音声社团"), "circle")
                self.assertEqual(tag_ns.get("耳搔"), "general")
                self.assertEqual(tag_ns.get("治愈"), "general")

                stats = system_routes.get_metadata_stats(db=db)
                self.assertEqual(stats["audio_total"], 1)
                self.assertEqual(stats["with_artist"], 1)
                self.assertEqual(stats["tagged_media"], 1)
        finally:
            db.close()

    def test_phase2_parsers_sidecar_and_backfill_batch(self):
        wnacg_html = """
        <html><body>
          <h2>[CircleX (AuthorY)] Test Work [中文]</h2>
          <div class="uwconn">
            <label>分類：同人誌</label>
            <label>頁數：24P</label>
            <a class="tagshow" href="/albums-index-tag-黑絲.html">黑絲</a>
            <a class="tagshow" href="/albums-index-tag-黑絲.html">黑絲</a>
            <a class="tagshow" href="/albums-index-tag-純愛.html">純愛</a>
            <p>簡介：这是一段测试简介</p>
          </div>
        </body></html>
        """
        wnacg_detail = external_sources.parse_wnacg_work_detail(wnacg_html, external_id="55555")
        self.assertEqual(wnacg_detail.external_id, "55555")
        self.assertEqual(wnacg_detail.category, "同人誌")
        self.assertEqual(wnacg_detail.page_count, 24)
        self.assertEqual(wnacg_detail.tags, ["黑絲", "純愛"])
        self.assertEqual(wnacg_detail.intro, "这是一段测试简介")

        asmr_payload = {
            "id": 1495967,
            "title": "Test ASMR Work",
            "circle": {"name": "CircleZ"},
            "vas": [{"name": "CV1"}],
            "tags": [{"name": "耳かき", "i18n": {"zh-cn": {"name": "掏耳朵"}}}],
            "release": "2026-02-01",
            "age_category_string": "adult",
            "has_subtitle": True,
            "duration": 1800,
            "rate_average_2dp": 4.85,
        }
        asmr_detail = asmr_source.parse_asmr_work_detail(asmr_payload, fallback_id="RJ1495967")
        self.assertEqual(asmr_detail.external_id, "RJ1495967")
        self.assertEqual(asmr_detail.circle, "CircleZ")
        self.assertEqual(asmr_detail.vas, ["CV1"])
        self.assertEqual(asmr_detail.tags, ["掏耳朵"])
        self.assertTrue(asmr_detail.has_subtitle)

        db = self.Session()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manga_dir = os.path.join(tmp, "m1")
                os.makedirs(manga_dir, exist_ok=True)
                ext_source = models.ExternalFavoriteSource(
                    source_type="wnacg",
                    name="WNACG",
                    favorites_url="https://www.wnacg.com",
                )
                db.add(ext_source)
                db.flush()
                ext_item = models.ExternalFavoriteItem(
                    source_id=ext_source.id,
                    source_type="wnacg",
                    external_id="55555",
                    title="[CircleX (AuthorY)] Test Work [中文]",
                    url="https://www.wnacg.com/photos-index-aid-55555.html",
                    category_name="同人誌",
                )
                db.add(ext_item)
                db.flush()
                wnacg_service._write_wnacg_source_marker(
                    ext_item,
                    manga_dir,
                    detail={"tags": ["黑絲", "純愛"]},
                )
                self.assertTrue(os.path.exists(os.path.join(manga_dir, "source.txt")))

                audio_dir = os.path.join(tmp, "a1")
                os.makedirs(audio_dir, exist_ok=True)

                folder = models.Folder(path=tmp, scan_mode="auto")
                manga = models.Media(
                    folder=folder,
                    title="[CircleX (AuthorY)] Test Work [中文]",
                    relative_path="m1",
                    absolute_path=manga_dir,
                    media_type="manga",
                    extension=".dir",
                    file_size=1024,
                    source_site="wnacg",
                    source_url="https://www.wnacg.com/photos-index-aid-55555.html",
                )
                audio = models.Media(
                    folder=folder,
                    title="RJ1495967 Test ASMR Work",
                    relative_path="a1",
                    absolute_path=audio_dir,
                    media_type="audio",
                    extension=".dir",
                    file_size=1024,
                    source_site="asmr",
                    source_url="https://asmr.one/work/RJ1495967",
                )
                db.add_all([folder, manga, audio])
                db.commit()

                with patch.object(external_sources, "fetch_wnacg_work_detail", return_value=wnacg_detail), \
                        patch.object(asmr_source, "fetch_work_detail", return_value=asmr_detail):
                    batch_summary = external_metadata_backfill.run_external_details_batch(
                        db,
                        limit=10,
                        delay_seconds=0.0,
                    )

                self.assertEqual(batch_summary["total"], 2)
                self.assertEqual(batch_summary["completed"], 2)
                self.assertEqual(batch_summary["failed"], 0)
                self.assertGreater(batch_summary["tags_attached"], 0)

                manga_sidecar = metadata_enrichment.read_metadata_json(manga_dir)
                self.assertTrue(manga_sidecar["scraped"])
                self.assertEqual(manga_sidecar["tags"], ["黑絲", "純愛"])

                audio_sidecar = metadata_enrichment.read_metadata_json(audio_dir)
                self.assertTrue(audio_sidecar["scraped"])
                self.assertEqual(audio_sidecar["tags"], ["掏耳朵"])
        finally:
            db.close()

    def test_phase3_local_similar_to_without_embeddings(self):
        db = self.Session()
        try:
            folder = models.Folder(path="D:\\Manga", scan_mode="manga")
            db.add(folder)
            db.flush()

            def make_book(title, *, artist=None, circle=None, parody=None, tags=()):
                m = models.Media(
                    folder_id=folder.id,
                    title=title,
                    relative_path=f"{title}.cbz",
                    absolute_path=f"D:\\Manga\\{title}.cbz",
                    media_type="manga",
                    extension=".cbz",
                    file_size=1024,
                    artist=artist,
                )
                db.add(m)
                db.flush()
                if circle or parody:
                    prof = models.MangaMetadataProfile(
                        media_id=m.id,
                        parsed_title=title,
                        parsed_artist=artist,
                        parsed_circle=circle,
                        parody=parody,
                        external_tags="[]",
                    )
                    db.add(prof)
                for tag_name, ns in tags:
                    tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
                    if not tag:
                        tag = models.Tag(name=tag_name, namespace=ns)
                        db.add(tag)
                        db.flush()
                    m.tags.append(tag)
                return m

            target = make_book(
                "[AlphaCircle (AlphaArtist)] Target Story (Blue Archive) [中文]",
                artist="AlphaArtist",
                circle="AlphaCircle",
                parody="Blue Archive",
                tags=[("黑丝", "general"), ("纯爱", "general"), ("中文", "language")],
            )
            same_artist = make_book(
                "[AlphaCircle (AlphaArtist)] Another Work [中文]",
                artist="AlphaArtist",
                circle="AlphaCircle",
                tags=[("黑丝", "general"), ("中文", "language")],
            )
            same_parody_tags = make_book(
                "[OtherCircle (OtherArtist)] BA Romance (Blue Archive) [中文]",
                artist="OtherArtist",
                circle="OtherCircle",
                parody="Blue Archive",
                tags=[("黑丝", "general"), ("纯爱", "general"), ("中文", "language")],
            )
            noise_only = make_book(
                "[UnrelatedCircle (UnrelatedArtist)] Action Fight [中文]",
                artist="UnrelatedArtist",
                circle="UnrelatedCircle",
                tags=[("机战", "general"), ("中文", "language")],
            )
            db.commit()

            candidates = manga_retrievers.visible_manga(db)
            with patch.object(manga_vector, "is_model_cached", side_effect=AssertionError("should not check model")):
                ref, neighbours = manga_retrievers.similar_to(db, "Target Story", candidates)

            self.assertIsNotNone(ref)
            self.assertEqual(ref.id, target.id)
            neighbour_ids = [mid for mid, _ in neighbours]
            self.assertIn(same_artist.id, neighbour_ids)
            self.assertIn(same_parody_tags.id, neighbour_ids)
            self.assertNotIn(noise_only.id, neighbour_ids)

            with patch.object(manga_vector, "is_model_cached", side_effect=AssertionError("should not check model")):
                rec = recommendations.recommend_manga(
                    db=db,
                    query="类似《Target Story》",
                    limit=5,
                    avoid_tags=[],
                    preferred_tags=[],
                    allow_ai=False,
                )
            rec_ids = [item["media"].id for item in rec["recommendations"]]
            self.assertEqual(rec["parsed_preferences"]["intent"], "similar_to")
            self.assertIn(same_artist.id, rec_ids)
            self.assertIn(same_parody_tags.id, rec_ids)
            self.assertNotIn(noise_only.id, rec_ids)
        finally:
            db.close()

    def test_phase3_similar_to_optional_cached_vector_still_works(self):
        db = self.Session()
        try:
            folder = models.Folder(path="D:\\Manga", scan_mode="manga")
            db.add(folder)
            db.flush()

            m1 = models.Media(
                folder_id=folder.id,
                title="Reference Book",
                relative_path="r.cbz",
                absolute_path="D:\\Manga\\r.cbz",
                media_type="manga",
                extension=".cbz",
                file_size=1024,
            )
            m2 = models.Media(
                folder_id=folder.id,
                title="Vector Neighbour",
                relative_path="n.cbz",
                absolute_path="D:\\Manga\\n.cbz",
                media_type="manga",
                extension=".cbz",
                file_size=1024,
            )
            db.add_all([m1, m2])
            db.flush()

            vec = np.zeros(manga_vector.VECTOR_DIM, dtype=np.float32)
            vec[0] = 1.0
            blob = manga_vector.serialize_vec(vec)
            db.add_all([
                models.MangaAIProfile(
                    media_id=m1.id, embedding=blob, embedding_model=manga_vector.MODEL_NAME,
                    style_tags="[]", story_tags="[]", tone_tags="[]", recommendation_keywords="[]",
                ),
                models.MangaAIProfile(
                    media_id=m2.id, embedding=blob, embedding_model=manga_vector.MODEL_NAME,
                    style_tags="[]", story_tags="[]", tone_tags="[]", recommendation_keywords="[]",
                ),
            ])
            db.commit()

            candidates = manga_retrievers.visible_manga(db)
            _, neighbours = manga_retrievers.similar_to(db, "Reference Book", candidates)
            self.assertEqual([mid for mid, _ in neighbours], [m2.id])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
