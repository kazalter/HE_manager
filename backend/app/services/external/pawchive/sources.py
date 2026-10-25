"""Allowlisted original-file locations from Pawchive's public metadata."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlsplit

FILE_PATH = re.compile(r"^/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}\.[a-z0-9]{2,5}$")
NODE_HOSTS = {2: "n2.pawchive.pw"}
TEMP_HOST = "t1.pawchive.pw"


def validate_source(url: str) -> tuple[str, str]:
    """Return a fixed host and request target; never accept an arbitrary URL."""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
        raise ValueError("invalid Pawchive file URL")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc not in {*NODE_HOSTS.values(), TEMP_HOST}
            or parsed.fragment):
        raise ValueError("invalid Pawchive file host")
    if parsed.netloc in NODE_HOSTS.values():
        if not parsed.path.startswith("/data/") or not FILE_PATH.fullmatch(parsed.path[5:]) or parsed.query:
            raise ValueError("invalid Pawchive node path")
    else:
        match = re.fullmatch(r"/f/[0-9a-f]{16}/([^/]+)", parsed.path)
        filename = unquote(match[1]) if match else ""
        if (not filename or filename in {".", ".."} or any(c in filename for c in "/\\")
                or any(ord(c) < 32 or ord(c) == 127 for c in filename)):
            raise ValueError("invalid Pawchive temporary path")
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        params = dict(pairs)
        if (len(pairs) != 2 or set(params) != {"e", "s"}
                or not re.fullmatch(r"[0-9]{1,12}", params["e"])
                or not re.fullmatch(r"[0-9a-f]{32}", params["s"])):
            raise ValueError("invalid Pawchive temporary signature")
    return parsed.netloc, parsed.path + ("?" + parsed.query if parsed.query else "")


def original_source(file: dict) -> str | None:
    temporary = file.get("temp_url")
    if temporary:
        validate_source(temporary)
        return temporary
    node = file.get("node")
    if type(node) is int and node in NODE_HOSTS:
        url = f"https://{NODE_HOSTS[node]}/data{file.get('path', '')}"
        validate_source(url)
        return url
    return None


def original_path(path: str, source_url: str | None) -> str:
    """The preview hash remains the identity; originals may have another suffix."""
    return unquote(urlsplit(source_url).path) if source_url else path
