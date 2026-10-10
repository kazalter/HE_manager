#!/usr/bin/env python3
"""H01 runtime conformance checks. Credentials are read locally and never printed."""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

MEDIA_TOOLS = (
    "search_media", "get_media_detail", "get_library_stats", "recommend_media",
    "list_duplicate_candidates", "list_tags", "list_folders",
    "propose_media_update", "propose_scan",
)
REQUIRED_FLAGS = (
    "run_submission", "run_status", "run_events_sse", "run_stop", "session_resources",
)
SESSION_ENDPOINTS = {
    "session_create": {"method": "POST", "path": "/api/sessions"},
    "session": {"method": "GET", "path": "/api/sessions/{session_id}"},
    "session_messages": {"method": "GET", "path": "/api/sessions/{session_id}/messages"},
    "session_delete": {"method": "DELETE", "path": "/api/sessions/{session_id}"},
}


class RuntimeCheckError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def failure_report(error: RuntimeCheckError) -> dict:
    return {"status": "FAIL", "error_code": error.code}


def validate_internal_base(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme != "http" or not parts.hostname or parts.username or parts.password:
            raise ValueError
        if parts.query or parts.fragment or parts.path not in ("", "/"):
            raise ValueError
        host = parts.hostname
        try:
            address = ipaddress.ip_address(host)
            allowed = address.is_private or address.is_loopback
        except ValueError:
            allowed = host in ("localhost", "hermes-agent", "he-hermes-h01")
        if not allowed or parts.port not in range(1, 65536):
            raise ValueError
    except (ValueError, TypeError):
        raise RuntimeCheckError("invalid_internal_base") from None
    return value.rstrip("/")


def load_config(path: Path) -> dict:
    try:
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise RuntimeCheckError("insecure_config")
        with path.open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise RuntimeCheckError("invalid_config")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise RuntimeCheckError("invalid_config")
        return result
    except RuntimeCheckError:
        raise
    except (OSError, ValueError):
        raise RuntimeCheckError("invalid_config") from None


def validate_catalog(capabilities: dict, toolsets: list | dict, *, model_tools: list | None = None) -> dict:
    if (not isinstance(capabilities, dict) or not isinstance(capabilities.get("features"), dict)
            or not isinstance(capabilities.get("endpoints"), dict)):
        raise RuntimeCheckError("invalid_capabilities")
    flags = capabilities.get("features", {})
    if any(flags.get(name) is not True for name in REQUIRED_FLAGS):
        raise RuntimeCheckError("missing_capabilities")
    endpoints = capabilities.get("endpoints", {})
    if any(endpoints.get(name) != expected for name, expected in SESSION_ENDPOINTS.items()):
        raise RuntimeCheckError("missing_session_endpoints")
    if isinstance(toolsets, dict):
        toolsets = toolsets.get("data", [])
    if not isinstance(toolsets, list):
        raise RuntimeCheckError("invalid_toolsets")
    media, memory = set(), set()
    expected = {"mcp__he__" + name for name in MEDIA_TOOLS}
    for group in toolsets:
        if not isinstance(group, dict):
            raise RuntimeCheckError("invalid_toolsets")
        if group.get("enabled") is not True:
            continue
        names = group.get("tools")
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise RuntimeCheckError("invalid_toolsets")
        for name in names:
            if name in expected:
                media.add(name)
            elif name == "memory":
                memory.add(name)
            else:
                raise RuntimeCheckError("unexpected_tools")
    if model_tools is not None:
        if not isinstance(model_tools, list) or any(not isinstance(name, str) for name in model_tools):
            raise RuntimeCheckError("invalid_model_tools")
        actual = set(model_tools)
        if actual - expected - {"memory"}:
            raise RuntimeCheckError("unexpected_tools")
        if actual & expected != expected:
            raise RuntimeCheckError("missing_media_tools")
        # This version's /v1/toolsets enumerates native/plugins only. Captured
        # outbound schemas prove MCP exposure; native dangerous tools still fail.
        media = actual & expected
        memory = actual & {"memory"}
    if media != expected:
        raise RuntimeCheckError("missing_media_tools")
    return {"media_tools": sorted(media), "memory_tools": sorted(memory)}


JSON_LIMIT = 8 * 1024 * 1024
SSE_LIMIT = 128 * 1024


def parse_sse(raw: str) -> list[dict]:
    events, data, size = [], [], 0
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n") + [""]:
        if not line:
            if data:
                try:
                    event = json.loads("\n".join(data))
                except (TypeError, ValueError):
                    raise RuntimeCheckError("invalid_sse_json") from None
                if not isinstance(event, dict):
                    raise RuntimeCheckError("invalid_sse_json")
                events.append(event)
            data, size = [], 0
        elif line.startswith("data:"):
            chunk = line[5:].removeprefix(" ")
            size += len(chunk.encode("utf-8")) + 1
            if size > SSE_LIMIT:
                raise RuntimeCheckError("sse_event_too_large")
            data.append(chunk)
    return events


def read_json_file(path: Path) -> dict:
    try:
        with path.open("rb") as source:
            raw = source.read(JSON_LIMIT + 1)
        if len(raw) > JSON_LIMIT:
            raise RuntimeCheckError("json_too_large")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except RuntimeCheckError:
        raise
    except (OSError, ValueError, TypeError):
        raise RuntimeCheckError("invalid_evidence_file") from None


def validate_budget(budget: dict) -> None:
    try:
        if budget["sse_subscribers"] != 0 or not 175 <= budget["measured_seconds"] <= 220:
            raise ValueError
        if "budget" in budget.get("turn_exit_reason", "") and budget["status"] == "failed":
            return
        watchdog = budget["watchdog"]
        if (watchdog["deadline_seconds"] != 180 or not 180 <= watchdog["stop_requested_age"] <= 182
                or watchdog["stop_ack"].get("status") != "stopping" or budget["status"] != "cancelled"):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RuntimeCheckError("invalid_watchdog_evidence") from None


def validate_evidence(evidence: dict, *, expected_model: str | None = None) -> dict:
    """Validate measured H01 records; missing probes can never become a PASS."""
    try:
        protocol = evidence["protocol"]["checks"]
        required = {"existing_session", "duplicate_session_id", "session_messages", "wrong_profile_key",
                    "default_key_for_named_profile", "cross_profile_session", "cross_profile_run",
                    "idempotent_same_run", "idempotent_conflict", "search_sse_status", "session_id_alias_create",
                    "session_id_alias_get", "delete_session", "deleted_session_missing", "delete_again", "stop_http"}
        if set(protocol) != required or not all(c["passed"] is True and c["actual"] == c["expected"] for c in protocol.values()):
            raise ValueError
        memory = evidence["memory"]
        if memory["he-user-1001"]["memory_markers"] != ["H01_ADMIN_1001_LIKES_RED"]:
            raise ValueError
        if memory["he-user-1002"]["memory_markers"] != ["H01_ADMIN_1002_LIKES_BLUE"]:
            raise ValueError
        limits = evidence["limits"]
        if limits["runs"]["H01 LOOP"]["turn_exit_reason"] != "max_iterations_reached(8/8)":
            raise ValueError
        if limits["runs"]["H01 PROPOSAL"]["status"] != "completed":
            raise ValueError
        model_requests = [c for c in limits["captures"] if c["tool_names"]]
        expected = {"mcp__he__" + name for name in MEDIA_TOOLS} | {"memory"}
        if not model_requests or any(set(c["tool_names"]) != expected or c["max_tokens"] != 2048 for c in model_requests):
            raise ValueError
        for mode, exit_code in (("term", 0), ("kill", 137)):
            restart = evidence["restart_" + mode]
            if restart["old_process_gone"] is not True or restart["old_pid"] == restart["new_pid"]:
                raise ValueError
            if restart["exit_code"] != exit_code or restart["oom_killed"] is not False:
                raise ValueError
            if restart["status"]["status"] != "interrupted" or restart["replay"].get("replayed") is not True:
                raise ValueError
            if restart["status"]["run_id"] != restart["replay"]["run_id"]:
                raise ValueError
        sdk = evidence["sdk"]
        if not sdk["python"].startswith("3.12.") or sdk["mcp"] != "2.0.0" or sdk["httpx2"] != "2.7.0":
            raise ValueError
        if set(sdk["tools"]) != set(MEDIA_TOOLS) or not isinstance(sdk["structured_result"], dict):
            raise ValueError
        budget = evidence["budget"]
        validate_budget(budget)
        external = evidence["external"]
        if external["status"] != "completed" or "mcp__he__search_media" not in external["executed_tools"]:
            raise ValueError
        if not expected_model or external["requested_model"] != expected_model or not external["usage_available"]:
            raise ValueError
        expired = evidence["expired_sse"]
        if expired["age_seconds"] <= 300 or expired["events_http"] != 404 or expired["status"] != "completed":
            raise ValueError
        resource = evidence["resources"]
        if not 0 < resource["addon_peak_bytes"] <= 2 * 1024**3:
            raise ValueError
        if resource["mem_available_bytes"] < 1024**3 or resource["root_free_bytes"] < 5 * 1024**3:
            raise ValueError
        if resource["image_unpacked_bytes"] <= 0 or resource["worker_uid"] != 1000 or resource["worker_gid"] != 1000:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RuntimeCheckError("incomplete_runtime_evidence") from None
    return {"protocol_checks": len(protocol), "model_schema": sorted(expected), "sdk": {
        "python": sdk["python"], "mcp": sdk["mcp"], "httpx2": sdk["httpx2"]}, "resources": resource}


def live_read(base: str, profile: str, key: str, path: str) -> tuple[int, dict]:
    from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
    from urllib.error import HTTPError, URLError
    prefix = "" if profile == "default" else "/p/" + profile
    if not re.fullmatch(r"default|he-user-[0-9]+", profile):
        raise RuntimeCheckError("invalid_profile")
    try:
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            response = opener.open(Request(base + prefix + path, headers={"Authorization": "Bearer " + key}), timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(JSON_LIMIT + 1)
            if len(raw) > JSON_LIMIT:
                raise RuntimeCheckError("json_too_large")
            result = json.loads(raw) if raw else {}
            if not isinstance(result, dict):
                raise ValueError
            return response.status, result
    except RuntimeCheckError:
        raise
    except (OSError, URLError, ValueError, TypeError):
        raise RuntimeCheckError("runtime_transport_error") from None


def check_runtime(config: dict) -> dict:
    base = validate_internal_base(config.get("base_url", ""))
    profiles = config.get("profiles", {})
    if (not isinstance(profiles, dict) or set(profiles) != {"default", "he-user-1001", "he-user-1002"}
            or any(not isinstance(profile, dict) for profile in profiles.values())):
        raise RuntimeCheckError("invalid_probe_profiles")
    if config.get("isolated_h01") is not True:
        raise RuntimeCheckError("isolated_fixture_required")
    evidence = read_json_file(Path(config.get("evidence_file", "")))
    report = validate_evidence(evidence, expected_model=config.get("expected_model"))
    actual_tools = report["model_schema"]
    for name, profile in profiles.items():
        key = profile.get("api_key")
        if not isinstance(key, str) or len(key) < 20:
            raise RuntimeCheckError("invalid_probe_key")
        code, health = live_read(base, name, key, "/health")
        if code != 200 or health.get("version") != "0.21.6":
            raise RuntimeCheckError("runtime_version_mismatch")
        code, capabilities = live_read(base, name, key, "/v1/capabilities")
        if code != 200:
            raise RuntimeCheckError("capabilities_unavailable")
        code, catalog = live_read(base, name, key, "/v1/toolsets")
        if code != 200:
            raise RuntimeCheckError("toolsets_unavailable")
        validate_catalog(capabilities, catalog, model_tools=actual_tools)
    code, _ = live_read(base, "he-user-1001", profiles["default"]["api_key"], "/v1/capabilities")
    if code != 401:
        raise RuntimeCheckError("profile_auth_isolation_failed")
    return {"status": "PASS", "hermes_version": "0.21.6", "profiles_checked": sorted(profiles), **report}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        report = check_runtime(config)
        print(json.dumps(report, sort_keys=True))
        return 0
    except RuntimeCheckError as error:
        print(json.dumps(failure_report(error), sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
