"""Scanner facade module for media discovery and metadata generation."""
from datetime import datetime
import hashlib
import json
import os
import threading
import traceback
import zipfile

import cv2
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from . import database, models
from .scanners import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MANGA_EXTENSIONS,
    SKIP_FOLDERS,
    VIDEO_EXTENSIONS,
    VIDEO_PREVIEW_SEMAPHORE,
    _FOLDER_SCAN_RESERVATIONS,
    _FOLDER_SCAN_RESERVATIONS_LOCK,
    _generate_sprite_vtt as _scanners_generate_sprite_vtt,
    _owns_folder_scan_reservation,
    apply_local_dedup_precheck,
    count_audio_tracks,
    count_manga_pages,
    directory_size,
    get_folder_thumbnail,
    get_image_metadata,
    get_image_thumbnail,
    get_manga_thumbnail,
    get_video_metadata,
    get_video_thumbnail as _scanners_get_video_thumbnail,
    get_work_cover_path,
    has_audio_file_recursive,
    has_image_file,
    is_valid_frame,
    make_work_thumbnail,
    media_type_for_extension,
    read_tracks_json,
    release_folder_scan,
    reserve_folder_scan,
    scan_folder,
    should_skip_dir,
)


def _generate_sprite_vtt(video_path, base_name, thumbnail_dir, interval=2):
    return _scanners_generate_sprite_vtt(video_path, base_name, thumbnail_dir, interval)


def get_video_thumbnail(video_path, thumb_path):
    return _scanners_get_video_thumbnail(
        video_path,
        thumb_path,
        semaphore=VIDEO_PREVIEW_SEMAPHORE,
        cv2_module=cv2,
    )


def generate_sprite_vtt(video_path, base_name, thumbnail_dir, interval=2):
    with VIDEO_PREVIEW_SEMAPHORE:
        return _generate_sprite_vtt(video_path, base_name, thumbnail_dir, interval)


__all__ = [
    "AUDIO_EXTENSIONS",
    "IMAGE_EXTENSIONS",
    "MANGA_EXTENSIONS",
    "SKIP_FOLDERS",
    "VIDEO_EXTENSIONS",
    "VIDEO_PREVIEW_SEMAPHORE",
    "_FOLDER_SCAN_RESERVATIONS",
    "_FOLDER_SCAN_RESERVATIONS_LOCK",
    "_generate_sprite_vtt",
    "_owns_folder_scan_reservation",
    "apply_local_dedup_precheck",
    "count_audio_tracks",
    "count_manga_pages",
    "cv2",
    "database",
    "datetime",
    "directory_size",
    "generate_sprite_vtt",
    "get_folder_thumbnail",
    "get_image_metadata",
    "get_image_thumbnail",
    "get_manga_thumbnail",
    "get_video_metadata",
    "get_video_thumbnail",
    "get_work_cover_path",
    "has_audio_file_recursive",
    "has_image_file",
    "hashlib",
    "Image",
    "is_valid_frame",
    "json",
    "make_work_thumbnail",
    "media_type_for_extension",
    "models",
    "np",
    "os",
    "read_tracks_json",
    "release_folder_scan",
    "reserve_folder_scan",
    "scan_folder",
    "should_skip_dir",
    "threading",
    "traceback",
    "zipfile",
]
