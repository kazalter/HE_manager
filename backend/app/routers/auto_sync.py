from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import auto_sync as auto_sync_service
from .. import models, schemas
from ..database import get_db
from ..external_config import get_global_proxy, update_global_proxy
from ..services.media_access import get_source_or_404, get_x_source_or_404

router = APIRouter()


def init_scheduler() -> None:
    auto_sync_service.init()


@router.get("/auto-sync/status", response_model=schemas.AutoSyncStatus)
def get_auto_sync_status(db: Session = Depends(get_db)):
    sources_status = []

    for source in (
        db.query(models.ExternalFavoriteSource)
        .filter(models.ExternalFavoriteSource.source_type == "wnacg")
        .all()
    ):
        sources_status.append(schemas.AutoSyncSourceStatus(
            source_type="wnacg",
            source_id=source.id,
            source_name=source.name,
            enabled=source.auto_sync_enabled or False,
            interval_hours=source.auto_sync_interval_hours or 24,
            last_run_at=source.auto_sync_last_run_at,
            next_run_at=source.auto_sync_next_run_at,
            last_status=source.auto_sync_last_status,
            last_message=source.auto_sync_last_message,
            running=auto_sync_service.is_source_active("wnacg", source.id),
        ))

    for source in db.query(models.XImportSource).all():
        sources_status.append(schemas.AutoSyncSourceStatus(
            source_type="x",
            source_id=source.id,
            source_name=source.name,
            enabled=source.auto_sync_enabled or False,
            interval_hours=source.auto_sync_interval_hours or 24,
            last_run_at=source.auto_sync_last_run_at,
            next_run_at=source.auto_sync_next_run_at,
            last_status=source.auto_sync_last_status,
            last_message=source.auto_sync_last_message,
            running=auto_sync_service.is_source_active("x", source.id),
        ))

    return {"scheduler_running": auto_sync_service.is_running(), "sources": sources_status}


@router.patch("/auto-sync/wnacg/{source_id}", response_model=schemas.ExternalFavoriteSource)
def update_wnacg_auto_sync(
    source_id: int,
    payload: schemas.AutoSyncConfigUpdate,
    db: Session = Depends(get_db),
):
    source = get_source_or_404(source_id, db)
    if source.source_type != "wnacg":
        raise HTTPException(status_code=400, detail="不是 WNACG 数据源")

    if payload.auto_sync_enabled is True:
        if not source.cookie:
            raise HTTPException(status_code=400, detail="请先保存 Cookie 再启用自动同步")
        if not source.download_root_path:
            raise HTTPException(status_code=400, detail="请先设置下载路径再启用自动同步")

    data = payload.dict(exclude_unset=True)
    if "proxy" in data:
        source.proxy = (data["proxy"] or "").strip() or None
        db.commit()

    enabled = data.get("auto_sync_enabled", source.auto_sync_enabled or False)
    interval = data.get("auto_sync_interval_hours", source.auto_sync_interval_hours or 24)

    auto_sync_service.update_schedule("wnacg", source_id, enabled, interval)

    db.refresh(source)
    return source


@router.patch("/auto-sync/x/{source_id}", response_model=schemas.XImportSource)
def update_x_auto_sync(
    source_id: int,
    payload: schemas.AutoSyncConfigUpdate,
    db: Session = Depends(get_db),
):
    source = get_x_source_or_404(source_id, db)

    if payload.auto_sync_enabled is True:
        if not source.cookie:
            raise HTTPException(status_code=400, detail="请先保存 Cookie 再启用自动同步")
        if not source.download_root_path:
            raise HTTPException(status_code=400, detail="请先设置下载路径再启用自动同步")

    data = payload.dict(exclude_unset=True)
    if "proxy" in data:
        source.proxy = (data["proxy"] or "").strip() or None
        db.commit()

    enabled = data.get("auto_sync_enabled", source.auto_sync_enabled or False)
    interval = data.get("auto_sync_interval_hours", source.auto_sync_interval_hours or 24)

    auto_sync_service.update_schedule("x", source_id, enabled, interval)

    db.refresh(source)
    return source


@router.post("/auto-sync/wnacg/{source_id}/trigger")
def trigger_wnacg_auto_sync(source_id: int, db: Session = Depends(get_db)):
    source = get_source_or_404(source_id, db)
    if source.source_type != "wnacg":
        raise HTTPException(status_code=400, detail="不是 WNACG 数据源")
    if not source.cookie:
        raise HTTPException(status_code=400, detail="请先保存 Cookie")
    if not source.download_root_path:
        raise HTTPException(status_code=400, detail="请先设置下载路径")
    if not auto_sync_service.trigger_now("wnacg", source_id):
        raise HTTPException(status_code=409, detail="该数据源正在自动同步中")
    return {"message": "已触发自动同步+下载"}


@router.post("/auto-sync/x/{source_id}/trigger")
def trigger_x_auto_sync(source_id: int, db: Session = Depends(get_db)):
    source = get_x_source_or_404(source_id, db)
    if not source.cookie:
        raise HTTPException(status_code=400, detail="请先保存 Cookie")
    if not source.download_root_path:
        raise HTTPException(status_code=400, detail="请先设置下载路径")
    if not auto_sync_service.trigger_now("x", source_id):
        raise HTTPException(status_code=409, detail="该数据源正在自动同步中")
    return {"message": "已触发自动同步+下载"}


@router.get("/auto-sync/logs", response_model=List[schemas.AutoSyncLogEntry])
def get_auto_sync_logs(
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(models.AutoSyncLog)
    if source_type:
        query = query.filter(models.AutoSyncLog.source_type == source_type)
    if source_id:
        query = query.filter(models.AutoSyncLog.source_id == source_id)
    return query.order_by(models.AutoSyncLog.id.desc()).limit(min(limit, 200)).all()


@router.get("/auto-sync/proxy")
def get_auto_sync_global_proxy():
    return {"proxy": get_global_proxy()}


@router.patch("/auto-sync/proxy")
def update_auto_sync_global_proxy(payload: schemas.GlobalProxyUpdate):
    new_proxy = update_global_proxy(payload.proxy)
    return {"proxy": new_proxy}
