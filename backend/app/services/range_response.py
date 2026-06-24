import mimetypes
import os
import re

from fastapi import Request
from fastapi.responses import StreamingResponse


def get_ranged_file_response(request: Request, file_path: str):
    file_size = os.stat(file_path).st_size
    range_header = request.headers.get("range")
    media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": media_type,
    }

    if not range_header:
        def file_iterator():
            with open(file_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        return StreamingResponse(file_iterator(), headers=headers, media_type=media_type)

    try:
        range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        start = int(range_match.group(1))
        end = range_match.group(2)
        end = int(end) if end else file_size - 1
    except Exception:
        start = 0
        end = file_size - 1

    start = max(0, start)
    end = min(file_size - 1, end)
    content_length = end - start + 1

    headers["Content-Length"] = str(content_length)
    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    def ranged_file_iterator():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_to_read = content_length
            chunk_size = 1024 * 1024
            while bytes_to_read > 0:
                chunk = f.read(min(chunk_size, bytes_to_read))
                if not chunk:
                    break
                bytes_to_read -= len(chunk)
                yield chunk

    return StreamingResponse(
        ranged_file_iterator(),
        status_code=206,
        headers=headers,
        media_type=media_type,
    )
