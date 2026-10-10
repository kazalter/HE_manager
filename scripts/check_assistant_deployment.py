#!/usr/bin/env python3
"""Fail closed before Compose starts if the data view can expose extra files.

Compose output is captured in memory, never printed or persisted: it may include
main-app secrets. Mount sources are checked against public empty placeholders.
"""
import argparse
import json
from pathlib import Path
import subprocess


DATABASE_FILES = {"library.db", "library.db-wal", "library.db-shm"}


def validate_inventory(root, masked):
    root = Path(root)
    database = root / "library.db"
    if root.is_symlink() or database.is_symlink() or not database.is_file():
        raise ValueError("assistant_database_view_invalid")
    for entry in root.iterdir():
        if entry.name in DATABASE_FILES:
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("assistant_database_view_invalid")
        elif entry.name not in masked:
            raise ValueError("assistant_unmasked_data_entry")


def validate_compose(root, config):
    root = Path(root).resolve()
    services = config["services"]
    tools = services["assistant-tools"]
    if (
        tools["environment"]["HE_DATABASE_URL"] != "sqlite:////data/library.db"
        or services["backend"]["environment"]["HE_DATABASE_URL"]
        != tools["environment"]["HE_DATABASE_URL"]
    ):
        raise ValueError("assistant_database_view_invalid")
    views = {v["target"]: v for v in tools["volumes"]}
    data = views["/data"]
    if data["type"] != "bind" or data.get("read_only"):
        raise ValueError("assistant_database_view_invalid")
    backend_data = next(
        v for v in services["backend"]["volumes"] if v["target"] == "/data"
    )
    if data["source"] != backend_data["source"]:
        raise ValueError("assistant_database_view_invalid")
    masked = set()
    for target, view in views.items():
        if target == "/data":
            continue
        if target in ("/mnt/hdd", "/data/assistant-logs"):
            expected = Path("/mnt/hdd") if target == "/mnt/hdd" else Path(data["source"]) / "assistant-logs"
            source = Path(view["source"])
            if view["type"] != "bind" or not view.get("read_only") or source.is_symlink() or not source.is_dir() or source.resolve() != expected.resolve():
                raise ValueError("assistant_project_view_invalid")
            if target.startswith("/data/"):
                masked.add(target.removeprefix("/data/"))
            continue
        if (
            not target.startswith("/data/")
            or target.count("/") != 2
            or not view.get("read_only")
            or view["type"] != "bind"
        ):
            raise ValueError("assistant_data_mask_invalid")
        source = Path(view["source"])
        if source.is_symlink() or not source.exists():
            raise ValueError("assistant_data_mask_invalid")
        if target == "/data/huggingface":
            if (
                source.resolve() != Path(data["source"]).resolve() / "huggingface"
                or not source.is_dir()
            ):
                raise ValueError("assistant_data_mask_invalid")
        elif source.resolve() == root / "deploy/hermes/empty-file":
            if source.read_bytes() != b"{}\n":
                raise ValueError("assistant_data_mask_invalid")
        elif source.resolve() == root / "deploy/hermes/empty-dir":
            if sorted(p.name for p in source.iterdir()) != ["README"]:
                raise ValueError("assistant_data_mask_invalid")
        else:
            raise ValueError("assistant_data_mask_invalid")
        masked.add(target.removeprefix("/data/"))
    if not {
        "hermes",
        "assistant",
        "backups",
        "deepseek.json",
        "external_config.json",
        "pawchive_stream.key",
    }.issubset(masked):
        raise ValueError("assistant_data_mask_invalid")
    validate_inventory(Path(data["source"]), masked)
    if tools.get("user") != "1000:1000":
        raise ValueError("assistant_worker_uid_invalid")
    for name in DATABASE_FILES:
        path = Path(data["source"]) / name
        if path.exists() and path.stat().st_uid != 1000:
            raise ValueError("assistant_database_owner_invalid")
    if Path(data["source"]).stat().st_uid != 1000:
        raise ValueError("assistant_database_owner_invalid")
    for name in ("assistant-tools", "assistant-mcp", "hermes-agent"):
        service = services[name]
        if (
            service.get("ports")
            or service.get("privileged")
            or service.get("network_mode") == "host"
            or any(
                "docker.sock" in v.get("source", "") for v in service.get("volumes", [])
            )
        ):
            raise ValueError("assistant_isolation_invalid")
    if (
        set(services["assistant-mcp"]["networks"]) != {"assistant_internal"}
        or services["assistant-mcp"].get("volumes")
        or set(tools["networks"]) != {"assistant_internal"}
        or not config["networks"]["assistant_internal"].get("internal")
    ):
        raise ValueError("assistant_isolation_invalid")
    if any(
        any(word in key.upper() for word in ("SECRET", "TOKEN", "API_KEY"))
        for key in tools["environment"]
    ):
        raise ValueError("assistant_environment_invalid")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--override", action="append", type=Path, default=[])
    args = parser.parse_args()
    try:
        root = args.repo.resolve()
        command = ["docker", "compose", "--project-directory", str(root)]
        for path in [
            root / "docker-compose.yml",
            root / "docker-compose.assistant.yml",
            *args.override,
        ]:
            command.extend(["-f", str(path)])
        command.extend(["config", "--format", "json"])
        result = subprocess.run(command, capture_output=True, check=True)
        validate_compose(root, json.loads(result.stdout))
        print("PASS assistant_deployment_isolation")
        return 0
    except Exception:
        print("FAIL assistant_deployment_isolation")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
