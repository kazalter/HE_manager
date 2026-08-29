import os
import cv2
import numpy as np
from PIL import Image

from . import common


def is_valid_frame(frame, max_width=512):
    """
    Checks if a frame is 'valid' for a thumbnail (not black/white, not pure color, not too blurry).
    """
    try:
        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / w
            frame = cv2.resize(frame, (max_width, int(h * scale)))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 1. Brightness check (avoid black or white screens)
        avg_brightness = np.mean(gray)
        if avg_brightness < 20 or avg_brightness > 235:
            return False, avg_brightness, 0, 0

        # 2. Variance check (avoid pure colors or very low detail)
        variance = np.var(gray)
        if variance < 150:
            return False, avg_brightness, variance, 0

        # 3. Sharpness check (Laplacian variance)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        if sharpness < 15:
            return False, avg_brightness, variance, sharpness

        return True, avg_brightness, variance, sharpness
    except Exception:
        return False, 0, 0, 0


def get_video_thumbnail(video_path, thumb_path, semaphore=None, cv2_module=None):
    """
    Generates a thumbnail for a video by finding the first 'valid' frame.
    Returns (success, time_ms, source).
    """
    sampling_ms = [0, 500, 1000, 1500, 2000, 3000, 5000, 8000]
    best_fallback_frame = None
    best_fallback_time = 0
    sem = semaphore if semaphore is not None else common.VIDEO_PREVIEW_SEMAPHORE
    cv2_lib = cv2_module if cv2_module is not None else cv2

    with sem:
        try:
            cap = cv2_lib.VideoCapture(video_path)
            if not cap.isOpened():
                return False, 0, "error"

            total_frames = int(cap.get(cv2_lib.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2_lib.CAP_PROP_FPS)
            duration_ms = (total_frames / fps) * 1000 if fps > 0 else 0

            # Try sampling points
            for t_ms in sampling_ms:
                if duration_ms > 0 and t_ms > duration_ms:
                    break

                cap.set(cv2_lib.CAP_PROP_POS_MSEC, t_ms)
                success, frame = cap.read()
                if not success or frame is None:
                    continue

                valid, brightness, variance, sharpness = is_valid_frame(frame)

                # Keep the first frame we read as initial fallback
                if best_fallback_frame is None:
                    best_fallback_frame = frame.copy()
                    best_fallback_time = t_ms

                if valid:
                    cv2_lib.imwrite(thumb_path, frame)
                    cap.release()
                    return True, int(t_ms), "first_valid_frame"

            # If no valid frame found in 8s, try fallback at 10% duration
            if duration_ms > 0:
                fallback_ms = duration_ms * 0.1
                cap.set(cv2_lib.CAP_PROP_POS_MSEC, fallback_ms)
                success, frame = cap.read()
                if success and frame is not None:
                    cv2_lib.imwrite(thumb_path, frame)
                    cap.release()
                    return True, int(fallback_ms), "fallback_10_percent"

            # Ultimate fallback: use the first frame we encountered
            if best_fallback_frame is not None:
                cv2_lib.imwrite(thumb_path, best_fallback_frame)
                cap.release()
                return True, int(best_fallback_time), "fallback_initial"

            cap.release()
        except Exception as e:
            print(f"Error generating video thumbnail: {e}")

    return False, 0, "failed"


def get_video_metadata(video_path):
    metadata = {"duration": None, "width": None, "height": None}
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps and fps > 0 and total_frames > 0:
            metadata["duration"] = int(total_frames / fps)
        if width > 0:
            metadata["width"] = width
        if height > 0:
            metadata["height"] = height
        cap.release()
    except Exception as e:
        print(f"Error reading video metadata: {e}")
    return metadata


def _generate_sprite_vtt(video_path, base_name, thumbnail_dir, interval=2):
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0 or total_frames <= 0:
            cap.release()
            return False

        duration = total_frames / fps
        if duration < interval:
            cap.release()
            return False

        width = 160
        orig_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        orig_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if orig_w == 0 or orig_h == 0:
            cap.release()
            return False

        height = int(orig_h * (width / orig_w))
        cols = 10
        rows_per_sheet = 10
        sprites_per_sheet = cols * rows_per_sheet

        total_thumbnails = int(duration / interval)
        if total_thumbnails == 0:
            cap.release()
            return False

        vtt_content = ["WEBVTT\n"]
        sheet_index = 0
        current_sheet_img = Image.new('RGB', (cols * width, rows_per_sheet * height))

        def format_time(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds - int(seconds)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

        sheet_dirty = False

        for i in range(total_thumbnails):
            current_time = i * interval
            cap.set(cv2.CAP_PROP_POS_MSEC, current_time * 1000)
            success, frame = cap.read()
            if success:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                img = img.resize((width, height))

                local_i = i % sprites_per_sheet
                col = local_i % cols
                row = local_i // cols
                x = col * width
                y = row * height

                current_sheet_img.paste(img, (x, y))
                sheet_dirty = True

                start_time = format_time(current_time)
                end_time = format_time(min(current_time + interval, duration))

                vtt_content.append(f"\n{start_time} --> {end_time}")
                vtt_content.append(f"{base_name}_{sheet_index}.jpg#xywh={x},{y},{width},{height}")

                if local_i == sprites_per_sheet - 1:
                    sheet_name = f"{base_name}_{sheet_index}.jpg"
                    current_sheet_img.save(os.path.join(thumbnail_dir, sheet_name), "JPEG", quality=80)
                    sheet_index += 1
                    current_sheet_img = Image.new('RGB', (cols * width, rows_per_sheet * height))
                    sheet_dirty = False

        if sheet_dirty:
            sheet_name = f"{base_name}_{sheet_index}.jpg"
            current_sheet_img.save(os.path.join(thumbnail_dir, sheet_name), "JPEG", quality=80)

        vtt_name = f"{base_name}.vtt"
        with open(os.path.join(thumbnail_dir, vtt_name), "w", encoding="utf-8") as f:
            f.write("\n".join(vtt_content))

        cap.release()
        return True
    except Exception as e:
        print(f"Error generating sprite vtt: {e}")
        return False


def generate_sprite_vtt(video_path, base_name, thumbnail_dir, interval=2):
    with common.VIDEO_PREVIEW_SEMAPHORE:
        return _generate_sprite_vtt(video_path, base_name, thumbnail_dir, interval)
