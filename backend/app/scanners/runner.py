from datetime import datetime
import hashlib
import os
import traceback

from .. import database, models
from ..dedup import worker as dedup_worker
from .audio import (
    count_audio_tracks,
    get_work_cover_path,
    has_audio_file_recursive,
    make_work_thumbnail,
    read_tracks_json,
)
from .common import (
    AUDIO_EXTENSIONS,
    SKIP_FOLDERS,
    _owns_folder_scan_reservation,
    apply_local_dedup_precheck,
    directory_size,
    has_image_file,
    media_type_for_extension,
    release_folder_scan,
    reserve_folder_scan,
    should_skip_dir,
)
from .manga import (
    count_manga_pages,
    get_folder_thumbnail,
    get_image_metadata,
    get_image_thumbnail,
    get_manga_thumbnail,
)
from .video import (
    generate_sprite_vtt,
    get_video_metadata,
    get_video_thumbnail,
)


def scan_folder(folder_id: int, reservation: object | None = None) -> bool:
    """Scan one folder, rejecting concurrent work for the same folder id."""
    if reservation is None:
        reservation = reserve_folder_scan(folder_id)
    elif not _owns_folder_scan_reservation(folder_id, reservation):
        return False
    if reservation is None:
        return False

    db = None
    folder = None
    try:
        db = database.SessionLocal()
        folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
        if not folder:
            print(f"Folder with id {folder_id} not found in DB.")
            return False

        folder.status = "scanning"
        db.commit()

        thumbnail_dir = os.path.join(os.getcwd(), ".thumbnails")
        if not os.path.exists(thumbnail_dir):
            os.makedirs(thumbnail_dir)

        media_batch = []
        scanned_paths = set()
        BATCH_SIZE = 200
        processed_count = 0
        thumbnail_enabled = bool(folder.thumbnail_enabled)
        thumbnail_interval = max(1, int(folder.thumbnail_interval or 1))
        existing_media = {
            media.absolute_path: media
            for media in db.query(models.Media).filter(models.Media.folder_id == folder.id).all()
        }

        library_title_index: set[str] = set()
        for row in (
            db.query(models.Media.normalized_title)
            .filter(models.Media.duplicate_status.notin_(["strong_duplicate", "checking", "dedup_excluded"]))
            .all()
        ):
            value = (row[0] or "").strip()
            if value:
                library_title_index.add(value)
        pending_dedup_paths: list[str] = []

        print(
            f"--- Starting scan for folder: {folder.path} "
            f"[Mode: {folder.scan_mode}, Thumbnails: {thumbnail_enabled}, Interval: {thumbnail_interval}s] "
            f"at {datetime.now()} ---"
        )

        for root, dirs, files in os.walk(folder.path):
            dirs[:] = [name for name in dirs if name.lower() not in SKIP_FOLDERS]

            if should_skip_dir(root):
                continue

            # --- MANGA FOLDER LOGIC ---
            if folder.scan_mode == "manga":
                if has_image_file(files):
                    scanned_paths.add(root)
                    existing = existing_media.get(root)
                    if not existing:
                        rel_path = os.path.relpath(root, folder.path)
                        title = os.path.basename(root) if rel_path != "." else (os.path.basename(os.path.normpath(folder.path)) or folder.path)
                        page_count = count_manga_pages(root, ".dir")
                        media = models.Media(
                            folder_id=folder.id, title=title, relative_path=rel_path,
                            absolute_path=root, media_type='manga', extension='.dir',
                            file_size=directory_size(root),
                            page_count=page_count, is_missing=False
                        )
                        thumb_name = f"thumb_dir_{media.title}_{datetime.now().timestamp()}.jpg"
                        thumb_path = os.path.join(thumbnail_dir, thumb_name)
                        if get_folder_thumbnail(root, thumb_path):
                            media.cover_path = thumb_name

                        apply_local_dedup_precheck(media, library_title_index, pending_dedup_paths)
                        media_batch.append(media)
                        existing_media[root] = media
                        processed_count += 1
                        print(f"  + Added Folder Manga: {media.title}")

                        if len(media_batch) >= BATCH_SIZE:
                            db.add_all(media_batch)
                            db.commit()
                            media_batch = []
                    else:
                        existing.is_missing = False
                        existing.missing_since = None
                        if existing.page_count is None:
                            existing.page_count = count_manga_pages(root, ".dir")
                    dirs[:] = []
                continue

            # --- AUDIO WORK FOLDER LOGIC ---
            if folder.scan_mode == "audio_work":
                has_marker = ("tracks.json" in files) or ("source.txt" in files)
                has_audio_here = any(
                    os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS for f in files
                )
                is_work_root = (has_marker and has_audio_file_recursive(root)) or has_audio_here
                if is_work_root:
                    scanned_paths.add(root)
                    existing = existing_media.get(root)
                    manifest = read_tracks_json(root)
                    track_count = (
                        len(manifest["tracks"])
                        if manifest and isinstance(manifest.get("tracks"), list)
                        else count_audio_tracks(root)
                    )
                    total_duration = None
                    if manifest and isinstance(manifest.get("tracks"), list):
                        durations = [
                            float(t.get("duration") or 0)
                            for t in manifest["tracks"]
                            if isinstance(t, dict)
                        ]
                        total_duration = int(sum(durations)) if durations else None

                    if not existing:
                        rel_path = os.path.relpath(root, folder.path)
                        title = (manifest or {}).get("title") or (
                            os.path.basename(root)
                            if rel_path != "."
                            else (os.path.basename(os.path.normpath(folder.path)) or folder.path)
                        )
                        source_url = (manifest or {}).get("url") or None
                        media = models.Media(
                            folder_id=folder.id,
                            title=title,
                            relative_path=rel_path,
                            absolute_path=root,
                            media_type='audio',
                            extension='.dir',
                            file_size=directory_size(root),
                            page_count=track_count,
                            duration=total_duration,
                            source_url=source_url,
                            source_site='asmr' if source_url and 'asmr.one' in source_url else None,
                            is_missing=False,
                        )
                        cover_src = get_work_cover_path(root)
                        if cover_src:
                            thumb_name = f"thumb_audio_{hashlib.md5(root.encode()).hexdigest()[:12]}_{datetime.now().timestamp()}.jpg"
                            thumb_path = os.path.join(thumbnail_dir, thumb_name)
                            if make_work_thumbnail(cover_src, thumb_path):
                                media.cover_path = thumb_name

                        apply_local_dedup_precheck(media, library_title_index, pending_dedup_paths)
                        media_batch.append(media)
                        existing_media[root] = media
                        processed_count += 1
                        print(f"  + Added Audio Work: {media.title}")

                        if len(media_batch) >= BATCH_SIZE:
                            db.add_all(media_batch)
                            db.commit()
                            media_batch = []
                    else:
                        existing.is_missing = False
                        existing.missing_since = None
                        if existing.page_count != track_count:
                            existing.page_count = track_count
                        if total_duration is not None and existing.duration != total_duration:
                            existing.duration = total_duration
                    dirs[:] = []
                continue

            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    ext = os.path.splitext(file)[1].lower()

                    target_type = media_type_for_extension(folder.scan_mode, ext)
                    if not target_type:
                        continue

                    scanned_paths.add(file_path)
                    existing = existing_media.get(file_path)
                    if existing:
                        existing.is_missing = False
                        existing.missing_since = None
                        try:
                            file_size = os.path.getsize(file_path)
                            if existing.file_size != file_size:
                                existing.file_size = file_size
                        except OSError:
                            pass
                        continue

                    media = None
                    rel_path = os.path.relpath(file_path, folder.path)
                    file_size = os.path.getsize(file_path)

                    if target_type == 'video':
                        metadata = get_video_metadata(file_path)
                        media = models.Media(
                            folder_id=folder.id, title=file, relative_path=rel_path,
                            absolute_path=file_path, media_type='video', extension=ext, file_size=file_size,
                            duration=metadata["duration"], width=metadata["width"], height=metadata["height"],
                            is_missing=False
                        )
                        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:12]
                        base_name = f"thumb_v_{file_hash}_{datetime.now().timestamp()}".replace(' ', '_')
                        thumb_name = f"{base_name}.jpg"
                        thumb_path = os.path.join(thumbnail_dir, thumb_name)
                        success, t_ms, source = get_video_thumbnail(file_path, thumb_path)
                        if success:
                            media.cover_path = thumb_name
                            media.cover_time_ms = t_ms
                            media.cover_source = source
                            if thumbnail_enabled:
                                generate_sprite_vtt(
                                    file_path,
                                    base_name,
                                    thumbnail_dir,
                                    interval=thumbnail_interval,
                                )

                    elif target_type == 'manga':
                        page_count = count_manga_pages(file_path, ext)
                        media = models.Media(
                            folder_id=folder.id, title=file, relative_path=rel_path,
                            absolute_path=file_path, media_type='manga', extension=ext, file_size=file_size,
                            page_count=page_count, is_missing=False
                        )
                        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:12]
                        thumb_name = f"thumb_m_{file_hash}_{datetime.now().timestamp()}.jpg"
                        thumb_path = os.path.join(thumbnail_dir, thumb_name)
                        if get_manga_thumbnail(manga_path=file_path, thumb_path=thumb_path):
                            media.cover_path = thumb_name

                    elif target_type == 'image':
                        metadata = get_image_metadata(file_path)
                        media = models.Media(
                            folder_id=folder.id, title=file, relative_path=rel_path,
                            absolute_path=file_path, media_type='image', extension=ext, file_size=file_size,
                            width=metadata["width"], height=metadata["height"], is_missing=False
                        )
                        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:12]
                        thumb_name = f"thumb_i_{file_hash}_{datetime.now().timestamp()}.jpg"
                        thumb_path = os.path.join(thumbnail_dir, thumb_name)
                        if get_image_thumbnail(file_path, thumb_path):
                            media.cover_path = thumb_name

                    elif target_type == 'audio':
                        media = models.Media(
                            folder_id=folder.id, title=file, relative_path=rel_path,
                            absolute_path=file_path, media_type='audio', extension=ext, file_size=file_size,
                            is_missing=False,
                        )

                    if media:
                        apply_local_dedup_precheck(media, library_title_index, pending_dedup_paths)
                        media_batch.append(media)
                        existing_media[file_path] = media
                        processed_count += 1
                        print(f"  + Added {media.media_type}: {file}")

                    if len(media_batch) >= BATCH_SIZE:
                        db.add_all(media_batch)
                        db.commit()
                        media_batch = []

                except Exception as file_error:
                    print(f"Error processing file {file}: {file_error}")
                    continue

        if media_batch:
            db.add_all(media_batch)
            db.commit()

        for item in existing_media.values():
            if item.absolute_path not in scanned_paths and not os.path.exists(item.absolute_path):
                if not item.is_missing:
                    item.is_missing = True
                    item.missing_since = datetime.now()

        folder.status = "idle"
        folder.last_scanned_at = datetime.now()
        db.commit()

        if pending_dedup_paths:
            checking_ids = [
                row[0]
                for row in db.query(models.Media.id)
                .filter(models.Media.absolute_path.in_(pending_dedup_paths))
                .filter(models.Media.duplicate_status == "checking")
                .all()
            ]
            if checking_ids:
                dedup_worker.enqueue(checking_ids)
                print(f"--- Queued {len(checking_ids)} item(s) for dedup analysis ---")
        print(f"--- Scan completed at {datetime.now()}. Total new items: {processed_count} ---")
        return True
    except Exception as e:
        print(f"Scan error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        if folder:
            folder.status = "error"
            db.commit()
        return False
    finally:
        if db is not None:
            db.close()
        release_folder_scan(folder_id, reservation)
