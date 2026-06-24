import json
import os
import re
import subprocess
import threading
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models

# ============================================================================
# The BD2 importer stores the asset checkout as Folder.scan_mode='bd2_asset'.
# These endpoints expose a small, path-guarded Spine asset browser for the web
# prototype. BD2 uses Spine (.skel/.atlas/.png), not Live2D Cubism.

BD2_CHARINFO_FILENAME = "CharInfo(Dropped).json"


def _bd2_asset_root(db: Session) -> str:
    configured = (os.getenv("HE_BD2_ASSET_ROOT") or "").strip()
    candidates = []
    if configured:
        candidates.append(configured)

    folders = (
        db.query(models.Folder)
        .filter(models.Folder.scan_mode == "bd2_asset")
        .order_by(models.Folder.id.desc())
        .all()
    )
    candidates.extend(folder.path for folder in folders if folder.path)

    media_rows = (
        db.query(models.Media.absolute_path)
        .filter(models.Media.source_site == "bd2")
        .order_by(models.Media.id.desc())
        .limit(20)
        .all()
    )
    for (path,) in media_rows:
        current = os.path.abspath(path or "")
        for _ in range(8):
            if not current:
                break
            candidates.append(current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent

    for raw in candidates:
        root = os.path.abspath(raw)
        if os.path.isdir(root) and (
            os.path.isdir(os.path.join(root, "spine"))
            or os.path.exists(os.path.join(root, BD2_CHARINFO_FILENAME))
        ):
            return root
    raise HTTPException(status_code=404, detail="BD2 asset root not found")


def _bd2_char_info(root: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Return (costume_meta, spine_to_char).

    ``costume_meta`` maps costume_id → {char_name, costume_name, …} (unchanged).
    ``spine_to_char`` maps every spine directory name (char, cutscene, illust)
    to its owning character name for gender filtering.
    """
    path = os.path.join(root, BD2_CHARINFO_FILENAME)
    empty: dict[str, dict[str, str]] = {}
    empty_map: dict[str, str] = {}
    if not os.path.exists(path):
        return empty, empty_map
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as file:
            text = file.read()
        # Upstream currently has one malformed object missing a comma before
        # "cutscene"; repair that known typo so names still resolve.
        text = re.sub(
            r'("censored_spine"\s*:\s*"[^"]+")\s*("cutscene"\s*:)',
            r"\1,\n        \2",
            text,
        )
        rows = json.loads(text)
    except Exception:
        return empty, empty_map

    out: dict[str, dict[str, str]] = {}
    spine_to_char: dict[str, str] = {}
    for char in rows if isinstance(rows, list) else []:
        char_name = str(char.get("charName") or "").strip()
        for costume in char.get("costumes") or []:
            costume_id = str(costume.get("costumeId") or "").strip()
            if not costume_id:
                continue
            out[costume_id] = {
                "char_name": char_name,
                "costume_name": str(costume.get("costumeName") or "").strip(),
                "release_date": str(costume.get("releaseDate") or "").strip(),
            }
            # Map spine / cutscene / censored_spine → char_name
            for key in ("spine", "cutscene", "censored_spine"):
                spine_id = str(costume.get(key) or "").strip()
                if spine_id:
                    spine_to_char[spine_id] = char_name
        # prestigeSkin
        ps = char.get("prestigeSkin")
        if isinstance(ps, dict):
            ps_spine = str(ps.get("spine") or "").strip()
            if ps_spine:
                spine_to_char[ps_spine] = char_name
        # guest / prestigeSkin interact (illust_datingN, cutscene_…)
        for src in ("guest", "prestigeSkin"):
            obj = char.get(src)
            if not isinstance(obj, dict):
                continue
            interact = obj.get("interact")
            items: list[str] = []
            if isinstance(interact, str):
                items = [interact]
            elif isinstance(interact, list):
                items = [str(i) for i in interact if isinstance(i, str)]
            for item in items:
                item = item.strip()
                if item:
                    spine_to_char[item] = char_name
    return out, spine_to_char


def _bd2_spine_title(
    asset_id: str,
    char_info: dict[str, dict[str, str]],
    *,
    kind: str = "char",
    spine_to_char: dict[str, str] | None = None,
) -> str:
    # illust assets don't follow the charNNNNNN pattern; derive title from
    # the spine_to_char mapping when available.
    if kind == "illust":
        char_name = (spine_to_char or {}).get(asset_id, "")
        if char_name:
            return f"Illust - {char_name} - {asset_id}"
        return f"Illust - {asset_id}"

    clean_id = asset_id.removeprefix("cutscene_")
    match = re.match(r"char(\d{6})(?:_c)?$", clean_id)
    meta = char_info.get(match.group(1) if match else "")
    if not meta:
        return asset_id
    title = f"{meta.get('char_name') or 'Unknown'} - {meta.get('costume_name') or asset_id}"
    if clean_id.endswith("_c"):
        title += " (censored)"
    if kind == "cutscene":
        title = f"Cutscene - {title}"
    return title


def _bd2_spine_dir(root: str, asset_id: str, *, kind: str = "char") -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", asset_id or ""):
        raise HTTPException(status_code=400, detail="Invalid Spine asset id")
    if kind == "cutscene":
        folder = "cutscenes"
    elif kind == "illust":
        folder = "illust"
    else:
        folder = "char"
    base = os.path.realpath(os.path.join(root, "spine", folder))
    target = os.path.realpath(os.path.join(base, asset_id))
    if not (target == base or target.startswith(base + os.sep)):
        raise HTTPException(status_code=400, detail="Invalid Spine asset path")
    if not os.path.isdir(target):
        raise HTTPException(status_code=404, detail="Spine asset not found")
    return target


def _bd2_collect_spine_assets(
    root: str,
    char_info: dict[str, dict[str, str]],
    spine_to_char: dict[str, str],
    *,
    kind: str,
    folder: str,
) -> list[dict]:
    asset_root = os.path.join(root, "spine", folder)
    if not os.path.isdir(asset_root):
        return []

    assets = []
    for name in sorted(os.listdir(asset_root)):
        asset_dir = os.path.join(asset_root, name)
        if not os.path.isdir(asset_dir):
            continue
        # Skip assets belonging to male characters.
        if _bd2_skip_asset(name, spine_to_char):
            continue
        files = sorted(
            filename
            for filename in os.listdir(asset_dir)
            if os.path.isfile(os.path.join(asset_dir, filename))
        )
        skeleton = next((f for f in files if f.lower().endswith(".skel")), None)
        atlas = next((f for f in files if f.lower().endswith(".atlas")), None)
        textures = [f for f in files if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        if not skeleton or not atlas or not textures:
            continue
        if kind == "cutscene":
            url_kind = "cutscene"
        elif kind == "illust":
            url_kind = "illust"
        else:
            url_kind = "char"
        assets.append({
            "id": f"{kind}:{name}",
            "asset_id": name,
            "kind": kind,
            "title": _bd2_spine_title(name, char_info, kind=kind, spine_to_char=spine_to_char),
            "skeleton": skeleton,
            "atlas": atlas,
            "textures": textures,
            "skeleton_url": f"/bd2/spine/{url_kind}/{name}/{skeleton}",
            "atlas_url": f"/bd2/spine/{url_kind}/{name}/{atlas}",
        })
    return assets


def _bd2_spine_signed_byte_mojibake_name(name: str) -> str:
    """Mirror spine-core 4.1's signed-byte binary string bug for atlas aliases."""
    return "".join(
        chr(byte) if byte < 0x80 else chr(0xFF00 + byte)
        for byte in name.encode("utf-8")
    )


def _bd2_atlas_with_spine41_aliases(text: str) -> str:
    lines = text.splitlines(keepends=True)
    names = {line.rstrip("\r\n") for line in lines if line.strip() and ":" not in line}
    out: list[str] = []
    in_page = False
    i = 0
    while i < len(lines):
        line = lines[i]
        name = line.rstrip("\r\n")
        if not name.strip():
            out.append(line)
            in_page = False
            i += 1
            continue
        if ":" in name:
            out.append(line)
            i += 1
            continue
        if not in_page:
            out.append(line)
            in_page = True
            i += 1
            continue

        block: list[str] = []
        j = i + 1
        while j < len(lines):
            next_name = lines[j].rstrip("\r\n")
            if not next_name.strip() or ":" not in next_name:
                break
            block.append(lines[j])
            j += 1
        out.append(line)
        out.extend(block)

        alias = _bd2_spine_signed_byte_mojibake_name(name)
        if alias != name and alias not in names:
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            out.append(f"{alias}{newline}")
            out.extend(block)
            names.add(alias)
        i = j
    return "".join(out)
# Characters to exclude from BD2 Spine asset listing (male / non-target).
_BD2_MALE_CHARACTERS: frozenset[str] = frozenset({
    "Lathel", "Gray", "Olstein", "Alec", "Andrew", "Nartas", "Wiggle", "Kry",
    "Jayden", "Goblin Slayer", "Fred", "Gynt", "Carlson",
})


def _bd2_skip_asset(asset_id: str, spine_to_char: dict[str, str]) -> bool:
    """Return True if *asset_id* belongs to a character in the male list."""
    char_name = spine_to_char.get(asset_id, "")
    return char_name in _BD2_MALE_CHARACTERS
# BD2 Spine download — incremental git clone/pull from GitHub
# ---------------------------------------------------------------------------
# First run:   `git clone --filter=blob:none` (no checkout) into target_dir
#              followed by a `sparse-checkout` for spine/char, spine/cutscenes,
#              spine/illust, CharInfo(Dropped).json — only the directories that
#              contain female characters are pulled, so the on-disk footprint
#              is small (a few hundred MB of texture/atlas, not the full GB
#              zipball).
# Subsequent: `git fetch --prune origin` + `git reset --hard origin/master`
#              re-uses the local pack store; only the deltas come down.
#
# Proxy: 127.0.0.1:7897 (socks5 primary, http fallback).  The proxy is written
# into the *local* repo's .git/config (not the user's global git config), so
# other repositories are untouched.

_BD2_REPO_URL = "https://github.com/myssal/Brown-Dust-2-Asset.git"
_BD2_DOWNLOAD_STATE: dict[str, object] = {}


def _bd2_proxy_url(scheme: str) -> str:
    """Return ``scheme://host:port`` for git proxy config.

    Read from env on every call so operators can change the proxy without
    restarting the backend.  Defaults stay 127.0.0.1:7897.
    """
    host = os.getenv("HE_BD2_PROXY_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("HE_BD2_PROXY_PORT", "7897").strip() or "7897"
    return f"{scheme}://{host}:{port}"


def _bd2_apply_git_proxy(repo_dir: str) -> None:
    """Write proxy settings into the local repo's .git/config.

    socks5 takes priority (DNS leaks to the proxy with socks5h).  If the
    user disables socks5 (e.g. their proxy only speaks http), set
    ``HE_BD2_PROXY_SCHEME=http``.
    """
    scheme = os.getenv("HE_BD2_PROXY_SCHEME", "socks5h").lower()
    if scheme not in {"socks5", "socks5h", "http", "https"}:
        scheme = "socks5h"
    proxy = _bd2_proxy_url(scheme)
    for proto in ("http", "https"):
        # `git config --local --replace-all` so re-runs don't stack up.
        subprocess.run(
            ["git", "config", "--local", f"{proto}.proxy", proxy],
            cwd=repo_dir,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    _BD2_DOWNLOAD_STATE["proxy"] = proxy


def _bd2_git_env() -> dict[str, str]:
    """Env for git subprocesses: force progress to stderr (machine-parseable)."""
    env = os.environ.copy()
    # GIT_TERMINAL_PROGRESS=1 makes git write the same progress lines to
    # stderr even when stderr isn't a TTY (background task).  Without this
    # the progress output is suppressed in non-interactive runs.
    env["GIT_TERMINAL_PROGRESS"] = "1"
    env["GCM_INTERACTIVE"] = "Never"
    # Don't let git ask for credentials — anonymous read-only repo.
    env["GIT_ASKPASS"] = "/bin/true"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


# Regexes for parsing `git --progress` lines.
#   Receiving objects:   45% (1234/2700), 5.00 MiB | 3.50 MiB/s
#   Resolving deltas:    12% (200/1700)
#   Updating files:      80% (160/200)
_BD2_PROGRESS_RE = re.compile(
    r"(\w[\w\s]*?):\s+(\d+)%\s+\(\s*(\d+)\s*/\s*(\d+)\s*\)"
    r"(?:,\s+([0-9.]+)\s*(KiB|MiB|GiB|KB|MB|GB)\s*\|\s*"
    r"([0-9.]+)\s*(KiB|MiB|GiB|KB|MB|GB)/s)?"
)
_BD2_UNIT_BYTES = {
    "B": 1,
    "KiB": 1024, "KB": 1024,
    "MiB": 1024 ** 2, "MB": 1024 ** 2,
    "GiB": 1024 ** 3, "GB": 1024 ** 3,
}


def _bd2_apply_progress_line(line: str) -> None:
    """Parse one stderr line from git --progress and update state.

    We pick the line whose phase gives the best user signal:
      * Receiving objects  → primary progress (most of clone time)
      * Resolving deltas / Updating files → tail of clone
      * Compressing / Counting → small weight
    """
    m = _BD2_PROGRESS_RE.search(line)
    if not m:
        return
    phase, pct, done, total, bytes_v, bytes_u, speed_v, speed_u = m.groups()
    pct_i = int(pct)
    done_i = int(done)
    total_i = int(total)
    bytes_f = float(bytes_v) * _BD2_UNIT_BYTES[bytes_u] if bytes_v else None
    speed_f = float(speed_v) * _BD2_UNIT_BYTES[speed_u] if speed_v else None

    # Only overwrite mb/speed when "Receiving objects" reports them —
    # that's the actual transfer phase.  Other phases don't carry throughput.
    if bytes_f is not None:
        _BD2_DOWNLOAD_STATE["mb"] = round(bytes_f / (1 << 20), 1)
    if speed_f is not None:
        _BD2_DOWNLOAD_STATE["speed_mb_s"] = round(speed_f / (1 << 20), 2)
    _BD2_DOWNLOAD_STATE["pct"] = pct_i
    _BD2_DOWNLOAD_STATE["objects_done"] = done_i
    _BD2_DOWNLOAD_STATE["objects_total"] = total_i
    _BD2_DOWNLOAD_STATE["phase"] = phase.strip()


def _bd2_stream_git(args: list[str], cwd: str) -> int:
    """Run a git command streaming stderr/stdout into progress state.

    Returns the process exit code.  Raises nothing on non-zero exit — the
    caller reads the return code and the captured stderr from
    ``_BD2_DOWNLOAD_STATE["stderr_tail"]`` for the error message.
    """
    env = _bd2_git_env()
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    _BD2_DOWNLOAD_STATE["proc"] = proc
    stderr_tail: list[str] = []

    def _drain(stream, *, is_err: bool) -> None:
        for raw in iter(stream.readline, ""):
            line = raw.rstrip()
            if is_err:
                _bd2_apply_progress_line(line)
                stderr_tail.append(line)
                if len(stderr_tail) > 20:
                    stderr_tail.pop(0)

    t_out = threading.Thread(target=_drain, args=(proc.stdout, False), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, True), daemon=True)
    t_out.start()
    t_err.start()

    rc = proc.wait()
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    _BD2_DOWNLOAD_STATE.pop("proc", None)
    _BD2_DOWNLOAD_STATE["stderr_tail"] = stderr_tail[-5:]
    return rc


def _bd2_run_git_with_cancel(args: list[str], cwd: str) -> int:
    """Run git, polling the cancel flag so terminate() fires promptly."""
    # _bd2_stream_git already stores `proc` on the state dict.  Cancel
    # endpoint will call .terminate() on it.  We just wait here.
    return _bd2_stream_git(args, cwd)


def _bd2_female_spine_dirs(char_info_json_text: str) -> list[str]:
    """Parse CharInfo.json and return the list of female spine directories."""
    import json as _json

    text = char_info_json_text
    text = re.sub(
        r'("censored_spine"\s*:\s*"[^"]+")\s*("cutscene"\s*:)',
        r"\1,\n        \2",
        text,
    )
    rows = _json.loads(text)
    dirs: list[str] = []

    def _add(name: object) -> None:
        if isinstance(name, str) and name.strip():
            dirs.append(name.strip())

    for char in rows if isinstance(rows, list) else []:
        char_name = str(char.get("charName") or "").strip()
        if char_name in _BD2_MALE_CHARACTERS:
            continue
        for costume in char.get("costumes") or []:
            for key in ("spine", "cutscene", "censored_spine"):
                _add(costume.get(key))
        ps = char.get("prestigeSkin")
        if isinstance(ps, dict):
            _add(ps.get("spine"))
        for src in ("guest", "prestigeSkin"):
            obj = char.get(src)
            if not isinstance(obj, dict):
                continue
            interact = obj.get("interact")
            if isinstance(interact, str):
                _add(interact)
            elif isinstance(interact, list):
                for item in interact:
                    _add(item)
    return dirs


def _bd2_sparse_paths(female_dirs: list[str]) -> list[str]:
    """Build the sparse-checkout include list from the female directory names.

    Mapping mirrors the original zipball filter logic so the on-disk result
    is identical.
    """
    paths: set[str] = set()
    for d in female_dirs:
        if d.startswith("cutscene_"):
            paths.add(f"spine/cutscenes/{d}")
        elif d.startswith("illust_"):
            paths.add(f"spine/illust/{d}")
        elif d.startswith("char"):
            paths.add(f"spine/char/{d}")
    paths.add(BD2_CHARINFO_FILENAME)
    return sorted(paths)


def _bd2_init_sparse_repo(target_dir: str, female_dirs: list[str]) -> None:
    """Configure sparse-checkout cone mode with the female-only paths."""
    paths = _bd2_sparse_paths(female_dirs)
    cfg = subprocess.run(
        ["git", "config", "--local", "core.sparseCheckout", "true"],
        cwd=target_dir,
        capture_output=True,
        text=True,
    )
    if cfg.returncode != 0:
        raise RuntimeError(f"git config sparseCheckout failed: {cfg.stderr.strip()}")
    # Write the include list (one pattern per line).
    info_dir = os.path.join(target_dir, ".git", "info")
    os.makedirs(info_dir, exist_ok=True)
    sparse_file = os.path.join(info_dir, "sparse-checkout")
    with open(sparse_file, "w", encoding="utf-8") as fh:
        # Cone-mode prefixes (trailing slash = directory) cover the dir tree.
        for p in paths:
            if "/" in p:
                fh.write(f"/{p.rsplit('/', 1)[0]}/\n")
            else:
                fh.write(f"/{p}\n")
    _BD2_DOWNLOAD_STATE["sparse_paths"] = paths


def _bd2_clear_git_locks(repo_dir: str) -> None:
    """Remove stale .git/*.lock files left by a killed git process."""
    git_dir = os.path.join(repo_dir, ".git")
    if not os.path.isdir(git_dir):
        return
    for entry in os.listdir(git_dir):
        if entry.endswith(".lock"):
            try:
                os.remove(os.path.join(git_dir, entry))
            except OSError:
                pass


def _bd2_run_download(target_dir: str) -> None:
    """Background task: incremental git sync of female BD2 Spine assets.

    First call   → ``git clone --filter=blob:none --no-checkout`` then
                   ``git sparse-checkout set`` to pull only the female
                   character directories plus CharInfo.
    Later calls  → ``git fetch --prune origin`` + ``git reset --hard origin/master``
                   (re-uses local packs, only the deltas come down).
    """
    # Reset state for this run.  We keep the same dict object so any in-flight
    # status poll sees a consistent shape.
    _BD2_DOWNLOAD_STATE.clear()
    _BD2_DOWNLOAD_STATE.update({
        "status": "checking",
        "step": "checking",
        "target": target_dir,
        "mode": None,        # filled in once we know: "clone" or "pull"
        "pct": 0,
        "mb": 0.0,
        "speed_mb_s": 0.0,
        "objects_done": 0,
        "objects_total": 0,
        "phase": "",
        "stderr_tail": [],
        "error": None,
        "started_at": time.time(),
    })

    # --- preflight: target_dir must be inside HE_BD2_ALLOWED_ROOTS or unset ---
    real_target = os.path.realpath(target_dir)
    allowed_roots_env = os.getenv("HE_BD2_ALLOWED_ROOTS", "").strip()
    if allowed_roots_env:
        allowed = [os.path.realpath(p) for p in allowed_roots_env.split(os.pathsep) if p.strip()]
        if not any(real_target == root or real_target.startswith(root + os.sep) for root in allowed):
            _BD2_DOWNLOAD_STATE["status"] = "error"
            _BD2_DOWNLOAD_STATE["error"] = (
                f"target_dir '{target_dir}' is outside HE_BD2_ALLOWED_ROOTS"
            )
            return

    # Cancel before we even start.
    if _BD2_DOWNLOAD_STATE.get("cancel_requested"):
        _BD2_DOWNLOAD_STATE["status"] = "cancelled"
        return

    repo_dir = real_target
    is_existing = os.path.isdir(os.path.join(repo_dir, ".git"))

    try:
        if is_existing:
            _bd2_run_pull(repo_dir)
        else:
            _bd2_run_clone(repo_dir)
    except Exception as exc:
        _BD2_DOWNLOAD_STATE["status"] = "error"
        _BD2_DOWNLOAD_STATE["error"] = str(exc)
        # Drop any zombie lock files so the next retry can run immediately.
        _bd2_clear_git_locks(repo_dir)
        return

    # If a cancel arrived mid-flight, _bd2_run_pull/_bd2_run_clone will have
    # set status='cancelled' itself.  Only continue with post-sync work when
    # we actually finished.
    if _BD2_DOWNLOAD_STATE.get("status") == "cancelled":
        _bd2_clear_git_locks(repo_dir)
        return

    # --- post-sync: ensure DB has a Folder row pointing at repo_dir so the
    # web preview picks it up via _bd2_asset_root() without manual setup. ---
    try:
        _bd2_register_folder(repo_dir)
    except Exception as exc:
        # Non-fatal — sync succeeded, just registration failed.
        _BD2_DOWNLOAD_STATE["register_error"] = str(exc)

    _BD2_DOWNLOAD_STATE["status"] = "done"
    _BD2_DOWNLOAD_STATE["finished_at"] = time.time()


def _bd2_run_clone(repo_dir: str) -> None:
    """First-time clone: minimal blob filter, then sparse-checkout init."""
    parent = os.path.dirname(repo_dir) or "."
    leaf = os.path.basename(repo_dir) or "Brown-Dust-2-Asset"
    os.makedirs(parent, exist_ok=True)

    _BD2_DOWNLOAD_STATE["status"] = "cloning"
    _BD2_DOWNLOAD_STATE["mode"] = "clone"
    _BD2_DOWNLOAD_STATE["step"] = "cloning"
    _BD2_DOWNLOAD_STATE["pct"] = 0

    # `--filter=blob:none` keeps the commit graph but skips blob download on
    # the initial fetch; we then `sparse-checkout init` and `set` the
    # female-only paths so only the wanted blobs ever come down.
    rc = _bd2_run_git_with_cancel(
        [
            "git", "clone",
            "--filter=blob:none",
            "--no-checkout",
            "--progress",
            _BD2_REPO_URL,
            leaf,
        ],
        cwd=parent,
    )
    if rc != 0:
        if _BD2_DOWNLOAD_STATE.get("cancel_requested"):
            _BD2_DOWNLOAD_STATE["status"] = "cancelled"
            return
        raise RuntimeError(
            f"git clone failed (rc={rc}): "
            + " | ".join(_BD2_DOWNLOAD_STATE.get("stderr_tail", []))
        )

    if _BD2_DOWNLOAD_STATE.get("cancel_requested"):
        # Move the partial repo out of the way so the next run starts clean.
        _BD2_DOWNLOAD_STATE["status"] = "cancelled"
        return

    # Apply proxy to the freshly-created repo before any subsequent fetch.
    _bd2_apply_git_proxy(repo_dir)

    # Read CharInfo to figure out which paths to checkout.
    ci_text = _bd2_read_charinfo(repo_dir)
    if not ci_text:
        # No CharInfo → fall back to a full checkout so the repo is at least
        # usable, but warn the user.
        _BD2_DOWNLOAD_STATE["step"] = "checking_out_all"
        rc = _bd2_run_git_with_cancel(
            ["git", "checkout", "--progress", "origin/HEAD"],
            cwd=repo_dir,
        )
        if rc != 0 and not _BD2_DOWNLOAD_STATE.get("cancel_requested"):
            raise RuntimeError(
                f"git checkout failed (rc={rc}): "
                + " | ".join(_BD2_DOWNLOAD_STATE.get("stderr_tail", []))
            )
        _BD2_DOWNLOAD_STATE["status"] = "done"
        return

    female_dirs = _bd2_female_spine_dirs(ci_text)
    _BD2_DOWNLOAD_STATE["female_dirs"] = len(female_dirs)
    if not female_dirs:
        raise RuntimeError("No female spine directories found in CharInfo")

    # Now init sparse-checkout, then read-tree to populate working tree.
    _BD2_DOWNLOAD_STATE["step"] = "sparse_checkout"
    _bd2_init_sparse_repo(repo_dir, female_dirs)

    rc = _bd2_run_git_with_cancel(
        ["git", "sparse-checkout", "init", "--cone"],
        cwd=repo_dir,
    )
    if rc != 0 and not _BD2_DOWNLOAD_STATE.get("cancel_requested"):
        raise RuntimeError(
            f"git sparse-checkout init failed (rc={rc}): "
            + " | ".join(_BD2_DOWNLOAD_STATE.get("stderr_tail", []))
        )

    # `read-tree` materialises the working tree for the configured sparse set.
    _BD2_DOWNLOAD_STATE["step"] = "checking_out"
    rc = _bd2_run_git_with_cancel(
        ["git", "read-tree", "-mu", "--reset", "HEAD"],
        cwd=repo_dir,
    )
    if rc != 0 and not _BD2_DOWNLOAD_STATE.get("cancel_requested"):
        raise RuntimeError(
            f"git read-tree failed (rc={rc}): "
            + " | ".join(_BD2_DOWNLOAD_STATE.get("stderr_tail", []))
        )


def _bd2_run_pull(repo_dir: str) -> None:
    """Subsequent runs: fetch only, then reset to origin/master."""
    _bd2_apply_git_proxy(repo_dir)

    _BD2_DOWNLOAD_STATE["status"] = "pulling"
    _BD2_DOWNLOAD_STATE["mode"] = "pull"
    _BD2_DOWNLOAD_STATE["step"] = "fetching"

    rc = _bd2_run_git_with_cancel(
        [
            "git", "fetch", "--prune", "--progress", "origin",
        ],
        cwd=repo_dir,
    )
    if rc != 0:
        if _BD2_DOWNLOAD_STATE.get("cancel_requested"):
            _BD2_DOWNLOAD_STATE["status"] = "cancelled"
            return
        raise RuntimeError(
            f"git fetch failed (rc={rc}): "
            + " | ".join(_BD2_DOWNLOAD_STATE.get("stderr_tail", []))
        )

    if _BD2_DOWNLOAD_STATE.get("cancel_requested"):
        _BD2_DOWNLOAD_STATE["status"] = "cancelled"
        return

    # Determine the upstream branch tip; default to origin/master.
    _BD2_DOWNLOAD_STATE["step"] = "merging"
    head_ref = "origin/master"
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/HEAD"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    if probe.returncode == 0:
        head_ref = "origin/HEAD"

    rc = _bd2_run_git_with_cancel(
        ["git", "reset", "--hard", "--progress", head_ref],
        cwd=repo_dir,
    )
    if rc != 0 and not _BD2_DOWNLOAD_STATE.get("cancel_requested"):
        raise RuntimeError(
            f"git reset failed (rc={rc}): "
            + " | ".join(_BD2_DOWNLOAD_STATE.get("stderr_tail", []))
        )

    # Re-read CharInfo post-pull — the female set may have changed upstream.
    ci_text = _bd2_read_charinfo(repo_dir)
    if ci_text:
        female_dirs = _bd2_female_spine_dirs(ci_text)
        _BD2_DOWNLOAD_STATE["female_dirs"] = len(female_dirs)
        # Refresh sparse-checkout if upstream added/removed entries.
        _bd2_init_sparse_repo(repo_dir, female_dirs)
        rc = _bd2_run_git_with_cancel(
            ["git", "read-tree", "-mu", "--reset", "HEAD"],
            cwd=repo_dir,
        )
        if rc != 0 and not _BD2_DOWNLOAD_STATE.get("cancel_requested"):
            raise RuntimeError(
                f"git read-tree (post-pull) failed (rc={rc}): "
                + " | ".join(_BD2_DOWNLOAD_STATE.get("stderr_tail", []))
            )


def _bd2_read_charinfo(repo_dir: str) -> str | None:
    """Return the working-tree CharInfo text, or None if not yet checked out."""
    path = os.path.join(repo_dir, BD2_CHARINFO_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError:
        return None


def _bd2_register_folder(target_dir: str) -> None:
    """Upsert a Folder(scan_mode='bd2_asset') row pointing at *target_dir*.

    Mirrors what the legacy importer used to do, so /bd2/spine/ picks up the
    new location without an environment-variable restart.
    """
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(models.Folder).filter(models.Folder.path == target_dir).first()
        if existing:
            existing.scan_mode = "bd2_asset"
            db.commit()
            return
        folder = models.Folder(
            path=target_dir,
            scan_mode="bd2_asset",
            thumbnail_enabled=False,
        )
        db.add(folder)
        db.commit()
    finally:
        db.close()
