import mimetypes
import os
import re

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)
_CHUNK_SIZE = 1024 * 1024


def _parse_single_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse one RFC 7233 byte range; return ``None`` when unsatisfiable.

    Multipart ranges are intentionally unsupported because the media clients use
    one range at a time. They receive 416 rather than a malformed partial body.
    """
    match = _RANGE_RE.fullmatch(range_header.strip())
    if not match or file_size <= 0:
        return None

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return None

    if not start_text:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            return None
        start = max(0, file_size - suffix_length)
        return start, file_size - 1

    start = int(start_text)
    if start >= file_size:
        return None

    if not end_text:
        return start, file_size - 1

    end = int(end_text)
    if end < start:
        return None
    return start, min(end, file_size - 1)


def _file_iterator(file_path: str, start: int, content_length: int):
    with open(file_path, "rb") as file:
        file.seek(start)
        remaining = content_length
        while remaining > 0:
            chunk = file.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def get_ranged_file_response(request: Request, file_path: str):
    file_size = os.stat(file_path).st_size
    range_header = request.headers.get("range")
    media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    base_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
    }

    if not range_header:
        headers = {**base_headers, "Content-Length": str(file_size)}
        return StreamingResponse(
            _file_iterator(file_path, 0, file_size),
            headers=headers,
            media_type=media_type,
        )

    byte_range = _parse_single_range(range_header, file_size)
    if byte_range is None:
        return Response(
            status_code=416,
            headers={
                **base_headers,
                "Content-Length": "0",
                "Content-Range": f"bytes */{file_size}",
            },
            media_type=media_type,
        )

    start, end = byte_range
    content_length = end - start + 1
    headers = {
        **base_headers,
        "Content-Length": str(content_length),
        "Content-Range": f"bytes {start}-{end}/{file_size}",
    }
    return StreamingResponse(
        _file_iterator(file_path, start, content_length),
        status_code=206,
        headers=headers,
        media_type=media_type,
    )
