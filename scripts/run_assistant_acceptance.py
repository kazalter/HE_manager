#!/usr/bin/env python3
"""Repeatable offline acceptance and real HE→Hermes→MCP read-only smoke.

Credentials belong only in a bounded owner-only JSON file. No raw server body,
LLM output or token is printed. Live checks create and clear their own sessions.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from uuid import uuid4


class AcceptanceError(ValueError):
    pass


def load_config(path):
    path = Path(path)
    if path.is_symlink() or (os.name != "nt" and path.stat().st_mode & 0o077):
        raise ValueError("acceptance_config_permissions")
    with path.open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ValueError("acceptance_config_too_large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("acceptance_config_invalid")
    if value.get("mode") == "offline":
        if set(value) != {"mode"}:
            raise ValueError("acceptance_config_invalid")
    elif value.get("mode") == "live":
        if set(value) != {"mode", "api_url", "tokens", "query", "expected_media_id"}:
            raise ValueError("acceptance_config_invalid")
        url = urlsplit(value["api_url"])
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("acceptance_config_invalid")
        tokens = value["tokens"]
        if (
            not isinstance(tokens, list)
            or len(tokens) != 2
            or len(set(tokens)) != 2
            or any(
                not isinstance(t, str)
                or not 32 <= len(t) <= 1000
                or not t.isascii()
                or any(c.isspace() for c in t)
                for t in tokens
            )
        ):
            raise ValueError("acceptance_config_invalid")
        if not isinstance(value["query"], str) or not 1 <= len(value["query"]) <= 200:
            raise ValueError("acceptance_config_invalid")
        if (
            type(value["expected_media_id"]) is not int
            or value["expected_media_id"] <= 0
        ):
            raise ValueError("acceptance_config_invalid")
    else:
        raise ValueError("acceptance_config_invalid")
    return value


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HEClient:
    def __init__(self, base, token):
        self.base, self.token = base.rstrip("/"), token
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def request(self, path, method="GET", body=None, expected=200):
        data = None if body is None else json.dumps(body).encode()
        request = Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.status != expected:
                    raise AcceptanceError("acceptance_http_status")
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise AcceptanceError("acceptance_response_too_large")
                return json.loads(raw)
        except HTTPError as error:
            if error.code == expected:
                return None
            raise AcceptanceError("acceptance_http_status") from None


def run_live(config):
    clients = [HEClient(config["api_url"], token) for token in config["tokens"]]
    checked = []
    for client in clients:
        own_sid = None
        rid = None
        try:
            status = client.request("/assistant/status")
            if not status.get("enabled") or status.get("busy"):
                raise AcceptanceError("acceptance_not_ready")
            own_sid = client.request(
                "/assistant/sessions", "POST", {"title": "隔离链路验收"}
            )["id"]
            prompt = (
                "调用 search_media 搜索 "
                + json.dumps(config["query"], ensure_ascii=False)
                + "，limit=5；必须调用工具，简短说明查询结果。只读查询，不创建建议，不写记忆。"
            )
            rid = client.request(
                "/assistant/sessions/" + own_sid + "/runs",
                "POST",
                {"input": prompt, "client_request_id": str(uuid4())},
            )["id"]
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                run = client.request("/assistant/runs/" + rid)
                if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                    break
                time.sleep(1)
            else:
                raise AcceptanceError("acceptance_run_timeout")
            if run["status"] != "completed" or not run.get("output"):
                raise AcceptanceError("acceptance_run_incomplete")
            results = client.request("/assistant/runs/" + rid + "/results")["items"]
            searches = [item for item in results if item["tool_name"] == "search_media"]
            if not searches or not any(
                item.get("id") == config["expected_media_id"]
                for call in searches
                for item in call["result"].get("items", [])
            ):
                raise AcceptanceError("acceptance_real_tool_not_observed")
            proposals = client.request("/assistant/sessions/" + own_sid + "/proposals")
            if proposals["total"]:
                raise AcceptanceError("acceptance_unexpected_proposal")
            peer = clients[1] if client is clients[0] else clients[0]
            peer.request("/assistant/runs/" + rid, expected=404)
            peer.request("/assistant/sessions/" + own_sid + "/messages", expected=404)
            checked.append(
                {
                    "status": run["status"],
                    "search_calls": len(searches),
                    "usage_available": isinstance(run.get("usage"), dict),
                }
            )
        finally:
            if rid:
                client.request("/assistant/runs/" + rid + "/stop", "POST")
            if own_sid:
                clear = client.request("/assistant/sessions/" + own_sid, "DELETE")
                if clear["state"] != "cleared":
                    raise AcceptanceError("acceptance_clear_unsettled")
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if config["mode"] == "offline":
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_assistant_acceptance.py",
                    "-q",
                    "-o",
                    "addopts=",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=root / "backend",
                capture_output=True,
                text=True,
            )
            if result.returncode:
                print("FAIL assistant_offline_acceptance")
                return 1
            print("PASS assistant_offline_acceptance")
        else:
            checks = run_live(config)
            print("PASS assistant_live_acceptance " + json.dumps(checks))
        return 0
    except Exception:
        print("FAIL assistant_acceptance_unavailable")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
