import os

from sqlalchemy.orm import Session

from .. import models

X_ARCHIVE_UPLOAD_DIR = os.path.join(os.getcwd(), "x_archive_uploads")
os.makedirs(X_ARCHIVE_UPLOAD_DIR, exist_ok=True)


def get_or_create_x_source(db: Session) -> models.XImportSource:
    source = db.query(models.XImportSource).order_by(models.XImportSource.id.asc()).first()
    if source:
        return source
    source = models.XImportSource(name="X 喜欢导入")
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def x_import_stats(source_id: int, db: Session) -> dict:
    base = db.query(models.XPost).filter(models.XPost.source_id == source_id)
    total = base.count()
    completed = base.filter(models.XPost.status == "completed").count()
    failed = base.filter(models.XPost.status == "failed").count()
    skipped = base.filter(models.XPost.status == "skipped").count()
    pending = base.filter(models.XPost.status.in_(["pending", "fetched", "downloading"])).count()
    media_query = (
        db.query(models.XMediaItem)
        .join(models.XPost, models.XPost.id == models.XMediaItem.post_id)
        .filter(models.XPost.source_id == source_id)
    )
    total_media = media_query.count()
    downloaded_media = media_query.filter(models.XMediaItem.status == "downloaded").count()
    return {
        "total_posts": total,
        "completed_posts": completed,
        "failed_posts": failed,
        "skipped_posts": skipped,
        "pending_posts": pending,
        "total_media": total_media,
        "downloaded_media": downloaded_media,
    }
