from sqlalchemy import inspect, text
from .database import engine

def ensure_folder_option_columns():
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("folders")}

    with engine.begin() as conn:
        if "thumbnail_enabled" not in columns:
            conn.execute(text("ALTER TABLE folders ADD COLUMN thumbnail_enabled BOOLEAN NOT NULL DEFAULT 1"))
        if "thumbnail_interval" not in columns:
            conn.execute(text("ALTER TABLE folders ADD COLUMN thumbnail_interval INTEGER NOT NULL DEFAULT 1"))


def ensure_media_option_columns():
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("media")}
    definitions = {
        "duration": "INTEGER",
        "width": "INTEGER",
        "height": "INTEGER",
        "page_count": "INTEGER",
        "rating": "INTEGER NOT NULL DEFAULT 0",
        "favorite": "BOOLEAN NOT NULL DEFAULT 0",
        "view_status": "VARCHAR NOT NULL DEFAULT 'unviewed'",
        "progress": "INTEGER NOT NULL DEFAULT 0",
        "last_opened_at": "DATETIME",
        "source_url": "VARCHAR",
        "source_site": "VARCHAR",
        "is_missing": "BOOLEAN NOT NULL DEFAULT 0",
        "missing_since": "DATETIME",
        "artist": "VARCHAR",
    }

    with engine.begin() as conn:
        for name, definition in definitions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE media ADD COLUMN {name} {definition}"))


def ensure_external_source_columns():
    inspector = inspect(engine)
    if not inspector.has_table("external_favorite_sources"):
        return
    columns = {column["name"] for column in inspector.get_columns("external_favorite_sources")}

    asmr_columns = {
        "api_mirrors": "TEXT",
        "audio_format_filter": "VARCHAR",
        "audio_version_filter": "VARCHAR",
        "username": "VARCHAR",
        "playlist_url": "VARCHAR",
    }

    auto_sync_columns = {
        "auto_sync_enabled": "BOOLEAN DEFAULT 0",
        "auto_sync_interval_hours": "INTEGER DEFAULT 24",
        "auto_sync_last_run_at": "DATETIME",
        "auto_sync_next_run_at": "DATETIME",
        "auto_sync_last_status": "VARCHAR",
        "auto_sync_last_message": "TEXT",
        "proxy": "VARCHAR",
    }

    with engine.begin() as conn:
        if "download_root_path" not in columns:
            conn.execute(text("ALTER TABLE external_favorite_sources ADD COLUMN download_root_path VARCHAR"))
        for name, definition in asmr_columns.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE external_favorite_sources ADD COLUMN {name} {definition}"))
        for name, definition in auto_sync_columns.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE external_favorite_sources ADD COLUMN {name} {definition}"))


def ensure_x_import_auto_sync_columns():
    inspector = inspect(engine)
    if not inspector.has_table("x_import_sources"):
        return
    columns = {column["name"] for column in inspector.get_columns("x_import_sources")}
    auto_sync_columns = {
        "auto_sync_enabled": "BOOLEAN DEFAULT 0",
        "auto_sync_interval_hours": "INTEGER DEFAULT 24",
        "auto_sync_last_run_at": "DATETIME",
        "auto_sync_next_run_at": "DATETIME",
        "auto_sync_last_status": "VARCHAR",
        "auto_sync_last_message": "TEXT",
        "proxy": "VARCHAR",
    }
    with engine.begin() as conn:
        for name, definition in auto_sync_columns.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE x_import_sources ADD COLUMN {name} {definition}"))


def ensure_external_favorite_item_columns():
    inspector = inspect(engine)
    if not inspector.has_table("external_favorite_items"):
        return
    columns = {column["name"] for column in inspector.get_columns("external_favorite_items")}

    with engine.begin() as conn:
        if "sync_position" not in columns:
            conn.execute(text("ALTER TABLE external_favorite_items ADD COLUMN sync_position INTEGER"))


def ensure_media_indexes():
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_folder_id ON media (folder_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_media_type ON media (media_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_folder_missing ON media (folder_id, is_missing)"))


def ensure_media_cover_info_columns():
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("media")}
    with engine.begin() as conn:
        if "cover_time_ms" not in columns:
            conn.execute(text("ALTER TABLE media ADD COLUMN cover_time_ms INTEGER"))
        if "cover_source" not in columns:
            conn.execute(text("ALTER TABLE media ADD COLUMN cover_source VARCHAR"))


def ensure_manga_ai_profile_columns():
    inspector = inspect(engine)
    if not inspector.has_table("manga_ai_profiles"):
        return
    columns = {column["name"] for column in inspector.get_columns("manga_ai_profiles")}
    with engine.begin() as conn:
        if "embedding" not in columns:
            conn.execute(text("ALTER TABLE manga_ai_profiles ADD COLUMN embedding BLOB"))
        if "embedding_model" not in columns:
            conn.execute(text("ALTER TABLE manga_ai_profiles ADD COLUMN embedding_model VARCHAR"))


def ensure_x_import_indexes():
    inspector = inspect(engine)
    if not inspector.has_table("x_posts"):
        return
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_x_posts_source_status ON x_posts (source_id, status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_x_media_items_post ON x_media_items (post_id)"))


def ensure_dedup_columns():
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("media")}
    with engine.begin() as conn:
        if "normalized_title" not in columns:
            conn.execute(text("ALTER TABLE media ADD COLUMN normalized_title VARCHAR"))
        if "duplicate_status" not in columns:
            conn.execute(text("ALTER TABLE media ADD COLUMN duplicate_status VARCHAR NOT NULL DEFAULT 'unique'"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_normalized_title ON media (normalized_title)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_duplicate_status ON media (duplicate_status)"))


def ensure_dedup_indexes():
    inspector = inspect(engine)
    if not inspector.has_table("duplicate_candidates"):
        return
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dup_candidates_status ON duplicate_candidates (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dup_candidates_level ON duplicate_candidates (level)"))


def run_schema_migrations():
    """Runs all manual idempotent schema migrations."""
    ensure_folder_option_columns()
    ensure_media_option_columns()
    ensure_external_source_columns()
    ensure_x_import_auto_sync_columns()
    ensure_external_favorite_item_columns()
    ensure_media_indexes()
    ensure_media_cover_info_columns()
    ensure_manga_ai_profile_columns()
    ensure_x_import_indexes()
    ensure_dedup_columns()
    ensure_dedup_indexes()
