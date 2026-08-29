from typing import Optional


DOWNLOAD_JOBS: dict[str, dict] = {}


class DownloadCancelled(Exception):
    def __init__(self, item_dir: Optional[str] = None):
        super().__init__("Download cancelled")
        self.item_dir = item_dir


def is_cancel_requested(job: dict) -> bool:
    return bool(job.get("cancel_requested"))


def find_task(job: dict, item_id: int) -> Optional[dict]:
    for task in job.get("tasks", []):
        if task.get("item_id") == item_id:
            return task
    return None
