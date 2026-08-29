import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, migrations, models, schemas
from app.routers import media as media_routes


class TagsApiTest(unittest.TestCase):
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

        # Seed sample folder, media and tags
        db = self.Session()
        try:
            self.folder = models.Folder(path="/test/folder", status="idle", scan_mode="auto")
            db.add(self.folder)
            db.commit()
            db.refresh(self.folder)

            self.media1 = models.Media(
                folder_id=self.folder.id,
                title="Media 1",
                relative_path="media1.mp4",
                absolute_path="/test/folder/media1.mp4",
                media_type="video",
                extension=".mp4",
                file_size=1024,
            )
            self.media2 = models.Media(
                folder_id=self.folder.id,
                title="Media 2",
                relative_path="media2.mp4",
                absolute_path="/test/folder/media2.mp4",
                media_type="video",
                extension=".mp4",
                file_size=2048,
            )
            db.add_all([self.media1, self.media2])
            db.commit()

            self.tag_gen = models.Tag(name="GeneralTag", namespace="general")
            self.tag_art = models.Tag(name="ArtistTag", namespace="artist")
            self.tag_char = models.Tag(name="CharacterTag", namespace="character")
            db.add_all([self.tag_gen, self.tag_art, self.tag_char])
            db.commit()

            # Link tags
            self.media1.tags.extend([self.tag_gen, self.tag_art])
            self.media2.tags.append(self.tag_gen)
            db.commit()
        finally:
            db.close()

    def tearDown(self):
        self.patch_db.stop()

    def test_list_tags_with_counts_and_namespaces(self):
        db = self.Session()
        try:
            tags = media_routes.list_tags(db=db)
            self.assertEqual(len(tags), 3)
            tag_map = {t.name: t for t in tags}

            self.assertIn("ArtistTag", tag_map)
            self.assertEqual(tag_map["ArtistTag"].namespace, "artist")
            self.assertEqual(tag_map["ArtistTag"].count, 1)

            self.assertIn("GeneralTag", tag_map)
            self.assertEqual(tag_map["GeneralTag"].namespace, "general")
            self.assertEqual(tag_map["GeneralTag"].count, 2)

            self.assertIn("CharacterTag", tag_map)
            self.assertEqual(tag_map["CharacterTag"].namespace, "character")
            self.assertEqual(tag_map["CharacterTag"].count, 0)
        finally:
            db.close()

    def test_tag_rename_and_namespace_update(self):
        db = self.Session()
        try:
            # Update name and namespace
            res = media_routes.update_tag(
                tag_id=self.tag_char.id,
                payload=schemas.TagUpdate(name="UpdatedCharTag", namespace="character"),
                db=db,
            )
            self.assertEqual(res.name, "UpdatedCharTag")
            self.assertEqual(res.namespace, "character")

            # Empty name should fail 400
            with self.assertRaises(HTTPException) as ctx:
                media_routes.update_tag(
                    tag_id=self.tag_char.id,
                    payload=schemas.TagUpdate(name="   "),
                    db=db,
                )
            self.assertEqual(ctx.exception.status_code, 400)

            # Duplicate (name, namespace) should fail 409
            with self.assertRaises(HTTPException) as ctx:
                media_routes.update_tag(
                    tag_id=self.tag_char.id,
                    payload=schemas.TagUpdate(name="GeneralTag", namespace="general"),
                    db=db,
                )
            self.assertEqual(ctx.exception.status_code, 409)

            # Non-existent tag should fail 404
            with self.assertRaises(HTTPException) as ctx:
                media_routes.update_tag(
                    tag_id=99999,
                    payload=schemas.TagUpdate(name="Foo"),
                    db=db,
                )
            self.assertEqual(ctx.exception.status_code, 404)
        finally:
            db.close()

    def test_tag_merge(self):
        db = self.Session()
        try:
            # Merge tag_art into tag_char
            res = media_routes.merge_tag(
                tag_id=self.tag_art.id,
                payload=schemas.TagMergeRequest(target_id=self.tag_char.id),
                db=db,
            )
            self.assertEqual(res["source_id"], self.tag_art.id)
            self.assertEqual(res["target_id"], self.tag_char.id)

            # Source tag should no longer exist
            self.assertIsNone(db.query(models.Tag).filter(models.Tag.id == self.tag_art.id).first())
            # media1 should now have tag_char
            media1 = db.query(models.Media).filter(models.Media.id == self.media1.id).first()
            tag_ids = [t.id for t in media1.tags]
            self.assertIn(self.tag_char.id, tag_ids)
            self.assertNotIn(self.tag_art.id, tag_ids)

            # Cannot merge into itself (400)
            with self.assertRaises(HTTPException) as ctx:
                media_routes.merge_tag(
                    tag_id=self.tag_char.id,
                    payload=schemas.TagMergeRequest(target_id=self.tag_char.id),
                    db=db,
                )
            self.assertEqual(ctx.exception.status_code, 400)

            # Non-existent target (404)
            with self.assertRaises(HTTPException) as ctx:
                media_routes.merge_tag(
                    tag_id=self.tag_char.id,
                    payload=schemas.TagMergeRequest(target_id=99999),
                    db=db,
                )
            self.assertEqual(ctx.exception.status_code, 404)
        finally:
            db.close()

    def test_tag_delete(self):
        db = self.Session()
        try:
            res = media_routes.delete_tag(tag_id=self.tag_gen.id, db=db)
            self.assertEqual(res["id"], self.tag_gen.id)

            # Tag should be gone
            self.assertIsNone(db.query(models.Tag).filter(models.Tag.id == self.tag_gen.id).first())
            # Media items still exist but without tag_gen
            media1 = db.query(models.Media).filter(models.Media.id == self.media1.id).first()
            self.assertIsNotNone(media1)
            self.assertNotIn(self.tag_gen.id, [t.id for t in media1.tags])

            # Deleting non-existent tag gives 404
            with self.assertRaises(HTTPException) as ctx:
                media_routes.delete_tag(tag_id=99999, db=db)
            self.assertEqual(ctx.exception.status_code, 404)
        finally:
            db.close()

    def test_media_add_and_remove_tag(self):
        db = self.Session()
        try:
            # Add a new tag to media2
            media = media_routes.add_media_tag(
                media_id=self.media2.id,
                payload=schemas.TagCreate(name="NewTag", namespace="custom"),
                db=db,
            )
            tag_names = [t.name for t in media.tags]
            self.assertIn("NewTag", tag_names)

            new_tag = db.query(models.Tag).filter(models.Tag.name == "NewTag").first()
            self.assertIsNotNone(new_tag)
            self.assertEqual(new_tag.namespace, "custom")

            # Remove tag
            media_after = media_routes.remove_media_tag(
                media_id=self.media2.id,
                tag_id=new_tag.id,
                db=db,
            )
            tag_names_after = [t.name for t in media_after.tags]
            self.assertNotIn("NewTag", tag_names_after)
        finally:
            db.close()

    def test_migration_ensure_tag_columns_idempotent(self):
        with patch.object(migrations, "engine", self.engine):
            migrations.ensure_tag_columns()
            migrations.ensure_tag_columns()


if __name__ == "__main__":
    unittest.main()
