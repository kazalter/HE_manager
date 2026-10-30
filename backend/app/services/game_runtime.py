"""Run one isolated Linux/Wine game session for browser streaming.

The game daemon is deliberately separate from HE Manager's Docker daemon.
It must be explicitly configured and uses the user's dedicated HDD mount.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any
from urllib.parse import quote

import httpx

from .. import models
from .game_workspace import GameWorkspaceError, prepare_game_copy

logger = logging.getLogger(__name__)

_API_VERSION = "v1.41"
_CONTAINER_NAME = "he-game-session"
_STREAM_COOKIE = "he_game_stream"
_lock = threading.RLock()


class GameRuntimeError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class GameSession:
    container_id: str
    session_id: str
    media_id: int
    title: str
    launcher: str
    stream_token: str


_active: GameSession | None = None


def stream_cookie_name() -> str:
    return _STREAM_COOKIE


def set_stream_cookie(response: Any, token: str, *, request: Any) -> None:
    _set_cookie(response, token, request=request)


def _settings() -> dict[str, str]:
    return {
        "socket": os.getenv("HE_GAME_DOCKER_SOCKET", "").strip(),
        "storage": os.getenv("HE_GAME_STORAGE_MOUNT", "").strip(),
        "workspace": os.getenv("HE_GAME_WORKSPACE_ROOT", "").strip(),
        "config": os.getenv("HE_GAME_CONFIG_ROOT", "").strip(),
        "prefix": os.getenv("HE_GAME_WINEPREFIX", "prefix8b").strip(),
        "image": os.getenv("HE_GAME_RUNTIME_IMAGE", "he-game-runtime:wine8").strip(),
        "device": os.getenv("HE_GAME_DRI_DEVICE", "/dev/dri/renderD128").strip(),
        "render_gid": os.getenv("HE_GAME_RENDER_GID", "993").strip(),
        "stream_dir": os.getenv("HE_GAME_STREAM_SOCKET_DIR", "").strip(),
        "wine": os.getenv("HE_GAME_WINE_BINARY", "/usr/lib/wine/wine").strip(),
    }


def _configured() -> dict[str, str]:
    settings = _settings()
    required = ("socket", "storage", "workspace", "config", "stream_dir")
    if any(not settings[key] for key in required):
        raise GameRuntimeError("Linux 游戏运行服务尚未配置")
    if not Path(settings["socket"]).is_socket():
        raise GameRuntimeError("专用游戏 Docker 服务不可用")
    return settings


def _docker(method: str, path: str, *, body: dict[str, Any] | None = None,
            params: dict[str, str] | None = None, missing_ok: bool = False) -> Any:
    settings = _settings()
    socket_path = settings["socket"]
    if not socket_path or not Path(socket_path).is_socket():
        raise GameRuntimeError("专用游戏 Docker 服务不可用")
    url = f"http://docker/{_API_VERSION}{path}"
    try:
        transport = httpx.HTTPTransport(uds=socket_path)
        with httpx.Client(transport=transport, timeout=httpx.Timeout(35.0, connect=4.0)) as client:
            response = client.request(method, url, json=body, params=params)
    except httpx.HTTPError as exc:
        logger.warning("Game Docker API unavailable: %s", type(exc).__name__)
        raise GameRuntimeError("无法连接专用游戏 Docker 服务") from exc
    if missing_ok and response.status_code == 404:
        return None
    if not 200 <= response.status_code < 300:
        detail = ""
        try:
            detail = str(response.json().get("message", ""))[:240]
        except (ValueError, AttributeError):
            pass
        logger.warning("Game Docker API returned %s: %s", response.status_code, detail)
        status_code = 409 if response.status_code in (409, 304) else 503
        raise GameRuntimeError("游戏容器操作失败，请检查 Linux 运行环境", status_code)
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _container() -> dict[str, Any] | None:
    container = _docker("GET", f"/containers/{quote(_CONTAINER_NAME, safe='')}/json", missing_ok=True)
    labels = (container or {}).get("Config", {}).get("Labels") or {}
    if container and labels.get("he-manager.game-session") != "true":
        raise GameRuntimeError("游戏容器名称冲突，请先检查专用 Docker 服务", 409)
    return container


def _set_cookie(response: Any, token: str, *, request: Any, max_age: int = 4 * 60 * 60) -> None:
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    response.set_cookie(
        _STREAM_COOKIE,
        token,
        max_age=max_age,
        path="/games/session/",
        secure=request.url.scheme == "https" or forwarded == "https",
        httponly=True,
        samesite="strict",
    )


def status(request: Any, response: Any) -> dict[str, Any]:
    with _lock:
        if _active is not None:
            container = _docker("GET", f"/containers/{_active.container_id}/json", missing_ok=True)
            if not container or not container.get("State", {}).get("Running"):
                _clear_active()
            else:
                _set_cookie(response, _active.stream_token, request=request)
                return {
                    "active": True,
                    "recoverable": True,
                    "id": _active.session_id,
                    "media_id": _active.media_id,
                    "title": _active.title,
                    "launcher": _active.launcher,
                }
        settings = _settings()
        if not settings["socket"] or not Path(settings["socket"]).is_socket():
            return {"active": False, "configured": False}
        orphan = _container()
        if orphan and orphan.get("State", {}).get("Running"):
            return {"active": True, "recoverable": False, "title": "已有游戏会话", "launcher": "", "configured": True}
        return {"active": False, "configured": True}


def _clear_active() -> None:
    global _active
    stream_dir = _settings().get("stream_dir", "")
    if stream_dir:
        try:
            (Path(stream_dir) / "active.sock").unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove stale game stream socket")
    _active = None


def _validate_host_path(path: str, storage: Path, *, must_exist: bool = True) -> Path:
    candidate = Path(path).resolve(strict=must_exist)
    root = storage.resolve(strict=True)
    if candidate == root or root not in candidate.parents:
        raise GameRuntimeError("游戏运行目录必须位于专用游戏磁盘内")
    return candidate


def _exec(container_id: str, command: list[str], *, working_dir: str = "/") -> None:
    result = _docker("POST", f"/containers/{container_id}/exec", body={
        "AttachStdin": False,
        "AttachStdout": False,
        "AttachStderr": False,
        "Detach": False,
        "Tty": False,
        "User": "root",
        "WorkingDir": working_dir,
        "Env": ["DISPLAY=:1", "WINEDEBUG=-all"],
        "Cmd": command,
    })
    exec_id = (result or {}).get("Id")
    if not exec_id:
        raise GameRuntimeError("无法启动游戏画面转发服务")
    _docker("POST", f"/exec/{exec_id}/start", body={"Detach": True, "Tty": False})


def _run_launcher(container_id: str, launcher: str, wine: str, prefix: str) -> None:
    prefix_path = Path(prefix)
    if prefix_path.is_absolute() or ".." in prefix_path.parts:
        raise GameRuntimeError("Wine 环境名称无效")
    result = _docker("POST", f"/containers/{container_id}/exec", body={
        "AttachStdin": False,
        "AttachStdout": False,
        "AttachStderr": False,
        "Detach": True,
        "Tty": False,
        "User": "root",
        "WorkingDir": "/games/dohnadohna",
        "Env": ["DISPLAY=:1", "WINEDEBUG=-all", f"WINEPREFIX=/config/{prefix_path.as_posix()}"],
        "Cmd": ["/bin/sh", "-c", "sleep 6; exec \"$1\" \"$2\"", "he-game-launcher", wine, launcher],
    })
    exec_id = (result or {}).get("Id")
    if not exec_id:
        raise GameRuntimeError("无法启动游戏")
    _docker("POST", f"/exec/{exec_id}/start", body={"Detach": True, "Tty": False})


def _wait_for_desktop(container_id: str) -> None:
    probe = "\n".join((
        "import socket, sys, time",
        "deadline = time.monotonic() + 24",
        "while time.monotonic() < deadline:",
        "    try:",
        "        with socket.create_connection(('127.0.0.1', 3000), timeout=0.4):",
        "            sys.exit(0)",
        "    except OSError:",
        "        time.sleep(0.4)",
        "sys.exit(1)",
    ))
    result = _docker("POST", f"/containers/{container_id}/exec", body={
        "AttachStdin": False,
        "AttachStdout": True,
        "AttachStderr": True,
        "Tty": False,
        "User": "root",
        "Cmd": ["/lsiopy/bin/python3", "-c", probe],
    })
    exec_id = (result or {}).get("Id")
    if not exec_id:
        raise GameRuntimeError("无法检查游戏桌面是否就绪")
    _docker("POST", f"/exec/{exec_id}/start", body={"Detach": False, "Tty": False})
    inspected = _docker("GET", f"/exec/{exec_id}/json")
    if (inspected or {}).get("ExitCode") != 0:
        raise GameRuntimeError("游戏桌面启动超时，请停止会话后重试")


def start(media: models.Media, launcher: str, launchers: list[str]) -> tuple[dict[str, Any], str]:
    global _active
    with _lock:
        current = status(_NullRequest(), _NullResponse())
        if current["active"]:
            if current.get("recoverable") and current.get("media_id") == media.id and current.get("launcher") == launcher:
                assert _active is not None
                return current, _active.stream_token
            raise GameRuntimeError("已有游戏会话正在运行，请先停止后再启动", 409)
        if Path(launcher).name != launcher or launcher not in launchers or not launcher.lower().endswith(".exe"):
            raise GameRuntimeError("启动程序无效，请刷新游戏信息后重试", 400)

        settings = _configured()
        try:
            storage = Path(settings["storage"]).resolve(strict=True)
        except OSError as exc:
            raise GameRuntimeError("HDD2 游戏磁盘暂时不可用") from exc
        if not os.path.ismount(storage):
            raise GameRuntimeError("HDD2 游戏磁盘未挂载")
        try:
            config_root = _validate_host_path(settings["config"], storage)
            prefix = _validate_host_path(str(config_root / settings["prefix"]), storage)
        except (FileNotFoundError, OSError) as exc:
            raise GameRuntimeError("已授权的 Wine 环境不存在") from exc
        if not prefix.is_dir():
            raise GameRuntimeError("已授权的 Wine 环境不存在")
        prefix_relative = Path(settings["prefix"])
        if not settings["prefix"] or prefix_relative.is_absolute() or ".." in prefix_relative.parts:
            raise GameRuntimeError("Wine 环境名称无效")
        workspace_root = _validate_host_path(settings["workspace"], storage, must_exist=False)
        stream_dir = _validate_host_path(settings["stream_dir"], storage, must_exist=False)

        try:
            source = Path(media.absolute_path)
            game_copy = prepare_game_copy(
                Path(media.folder.path), source, storage, workspace_root,
            )
        except GameWorkspaceError as exc:
            raise GameRuntimeError(str(exc), 409) from exc
        except (OSError, RuntimeError) as exc:
            logger.warning("Could not prepare game workspace: %s", type(exc).__name__)
            raise GameRuntimeError("无法准备游戏工作副本") from exc

        game_copy = _validate_host_path(str(game_copy), storage)
        image = settings["image"]
        image_ref = quote(image, safe="")
        if _docker("GET", f"/images/{image_ref}/json", missing_ok=True) is None:
            raise GameRuntimeError("Linux 游戏运行镜像尚未安装")

        config_root = _validate_host_path(str(config_root), storage)
        stream_dir.mkdir(parents=True, exist_ok=True, mode=0o777)
        os.chmod(stream_dir, 0o777)
        socket_file = stream_dir / "active.sock"
        socket_file.unlink(missing_ok=True)
        stale = _container()
        if stale:
            if stale.get("State", {}).get("Running"):
                raise GameRuntimeError("已有游戏容器仍在运行，请先停止后再启动", 409)
            _docker("DELETE", f"/containers/{stale['Id']}", params={"force": "true"})

        session_id = secrets.token_urlsafe(18)
        subfolder = f"/games/session/{session_id}/"
        env = [
            "DISPLAY=:1",
            "SUBFOLDER=" + subfolder,
            "SELKIES_DESKTOP=true",
            "SELKIES_VIDEO_STREAMING_MODE=false",
            "SELKIES_ENABLE_BASIC_AUTH=false",
            "SELKIES_MANUAL_WIDTH=1280",
            "SELKIES_MANUAL_HEIGHT=720",
            "SELKIES_FRAMERATE=30-30",
            "SELKIES_ENCODER=h264enc,h265enc,vp8enc,vp9enc,av1enc,jpeg",
        ]
        name = f"he-game-session"
        payload = {
            "Image": image,
            "Env": env,
            "Labels": {"he-manager.game-session": "true", "he-manager.session-id": session_id},
            "HostConfig": {
                "NetworkMode": "none",
                "Binds": [
                    f"{config_root}:/config:rw",
                    f"{game_copy}:/games/dohnadohna:rw",
                    f"{stream_dir}:/run/he-game-stream:rw",
                ],
                "Devices": [{
                    "PathOnHost": settings["device"],
                    "PathInContainer": settings["device"],
                    "CgroupPermissions": "rwm",
                }] if settings["device"] else [],
                "GroupAdd": [settings["render_gid"]] if settings["device"] and settings["render_gid"] else [],
                "Memory": 3 * 1024**3,
                "NanoCpus": 3_000_000_000,
                "ShmSize": 1024**3,
                "PidsLimit": 512,
                "SecurityOpt": ["no-new-privileges:true"],
                "RestartPolicy": {"Name": "no"},
            },
        }
        created = _docker("POST", "/containers/create", body=payload, params={"name": name})
        container_id = created["Id"]
        try:
            _docker("POST", f"/containers/{container_id}/start")
            _exec(container_id, ["/lsiopy/bin/python3", "/usr/local/bin/he-game-stream-relay",
                                 "--socket", "/run/he-game-stream/active.sock", "--port", "3000"])
            _wait_for_desktop(container_id)
            _run_launcher(container_id, launcher, settings["wine"], settings["prefix"])
        except Exception:
            try:
                _docker("POST", f"/containers/{container_id}/stop", params={"t": "5"})
            except GameRuntimeError:
                logger.warning("Unable to stop a failed game launch")
            try:
                _docker("DELETE", f"/containers/{container_id}", params={"force": "true"})
            except GameRuntimeError:
                logger.exception("Unable to remove a failed game launch")
            socket_file.unlink(missing_ok=True)
            raise

        token = secrets.token_urlsafe(32)
        _active = GameSession(
            container_id=container_id,
            session_id=session_id,
            media_id=media.id,
            title=media.title,
            launcher=launcher,
            stream_token=token,
        )
        return {
            "active": True,
            "recoverable": True,
            "id": session_id,
            "media_id": media.id,
            "title": media.title,
            "launcher": launcher,
        }, token


class _NullRequest:
    headers: dict[str, str] = {}
    url = type("URL", (), {"scheme": "http"})()


class _NullResponse:
    def set_cookie(self, *args: Any, **kwargs: Any) -> None:
        pass


def stop() -> dict[str, Any]:
    global _active
    with _lock:
        container = _container()
        if container:
            if container.get("State", {}).get("Running"):
                _docker("POST", f"/containers/{container['Id']}/stop", params={"t": "8"})
            _docker("DELETE", f"/containers/{container['Id']}", params={"force": "true"})
        _clear_active()
        return {"active": False}


def authorize_stream(request: Any) -> bool:
    with _lock:
        if _active is None:
            return False
        original_uri = request.headers.get("x-original-uri", "")
        if not original_uri.startswith(f"/games/session/{_active.session_id}/"):
            return False
        candidate = request.cookies.get(_STREAM_COOKIE, "")
        return bool(candidate) and hmac.compare_digest(candidate, _active.stream_token)
