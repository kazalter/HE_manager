from fastapi import APIRouter

from .asmr import (
    asmr_ping_mirrors,
    asmr_recheck_covers,
    create_asmr_download_job,
    push_asmr_to_downloader,
    router as asmr_router,
    sync_asmr_favorites,
)
from .downloader import (
    downloader_callback,
    router as downloader_router,
)
from .sources_items import (
    cancel_external_download_job,
    get_external_download_job,
    get_external_favorite_cover,
    list_external_favorites,
    list_external_sources,
    reconcile_external_favorites,
    router as sources_items_router,
    update_external_source,
)
from .wnacg import (
    create_wnacg_download_job,
    push_wnacg_to_downloader,
    router as wnacg_router,
    sync_wnacg_favorites,
)

router = APIRouter()
router.include_router(sources_items_router)
router.include_router(wnacg_router)
router.include_router(asmr_router)
router.include_router(downloader_router)

__all__ = [
    "router",
    "list_external_sources",
    "update_external_source",
    "list_external_favorites",
    "reconcile_external_favorites",
    "get_external_favorite_cover",
    "cancel_external_download_job",
    "get_external_download_job",
    "sync_wnacg_favorites",
    "create_wnacg_download_job",
    "push_wnacg_to_downloader",
    "asmr_ping_mirrors",
    "asmr_recheck_covers",
    "sync_asmr_favorites",
    "create_asmr_download_job",
    "push_asmr_to_downloader",
    "downloader_callback",
]
