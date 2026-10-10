"""Behavior contracts for the H01 checker; only synthetic metadata is used."""
from pathlib import Path
import importlib.util
import json
import os
import tempfile
import unittest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/check_hermes_runtime.py"
NINE = [
    "search_media", "get_media_detail", "get_library_stats", "recommend_media",
    "list_duplicate_candidates", "list_tags", "list_folders",
    "propose_media_update", "propose_scan",
]
FLAGS = ["run_submission", "run_status", "run_events_sse", "run_stop", "session_resources"]
ENDPOINTS = {
    "session_create": {"method": "POST", "path": "/api/sessions"},
    "session": {"method": "GET", "path": "/api/sessions/{session_id}"},
    "session_messages": {"method": "GET", "path": "/api/sessions/{session_id}/messages"},
    "session_delete": {"method": "DELETE", "path": "/api/sessions/{session_id}"},
}


class HermesRuntimeCheckTests(unittest.TestCase):
    def setUp(self):
        if not CHECKER.is_file():
            self.fail("H01 runtime checker is not implemented")
        spec = importlib.util.spec_from_file_location("hermes_runtime_checker", CHECKER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.capabilities = {"features": dict.fromkeys(FLAGS, True),
                             "endpoints": {key: dict(value) for key, value in ENDPOINTS.items()}}
        self.toolsets = [{"name": "he", "enabled": True,
                         "tools": ["mcp__he__" + n for n in NINE]}]

    def test_catalog_accepts_only_the_nine_media_tools_and_scoped_memory(self):
        self.toolsets.append({"name": "memory", "enabled": True, "tools": ["memory"]})
        result = self.module.validate_catalog(self.capabilities, self.toolsets)
        self.assertEqual(len(result["media_tools"]), 9)
        self.assertEqual(result["memory_tools"], ["memory"])

    def test_terminal_hidden_in_an_enabled_toolset_fails_closed(self):
        self.toolsets.append({"name": "core", "enabled": True, "tools": ["terminal"]})
        with self.assertRaises(self.module.RuntimeCheckError) as caught:
            self.module.validate_catalog(self.capabilities, self.toolsets)
        self.assertEqual(caught.exception.code, "unexpected_tools")

    def test_disabled_toolset_does_not_expand_the_live_allowlist(self):
        self.toolsets.append({"name": "core", "enabled": False, "tools": ["terminal"]})
        self.assertEqual(len(self.module.validate_catalog(self.capabilities, self.toolsets)["media_tools"]), 9)

    def test_missing_stop_capability_is_not_reported_as_supported(self):
        self.capabilities["features"]["run_stop"] = False
        with self.assertRaises(self.module.RuntimeCheckError) as caught:
            self.module.validate_catalog(self.capabilities, self.toolsets)
        self.assertEqual(caught.exception.code, "missing_capabilities")

    def test_missing_one_media_tool_is_not_a_successful_catalog(self):
        self.toolsets[0]["tools"].pop()
        with self.assertRaises(self.module.RuntimeCheckError) as caught:
            self.module.validate_catalog(self.capabilities, self.toolsets)
        self.assertEqual(caught.exception.code, "missing_media_tools")

    def test_real_session_resource_contract_uses_endpoints_not_invented_flags(self):
        capabilities = {
            "features": {
                "run_submission": True, "run_status": True,
                "run_events_sse": True, "run_stop": True, "session_resources": True,
            },
            "endpoints": {
                "session_create": {"method": "POST", "path": "/api/sessions"},
                "session": {"method": "GET", "path": "/api/sessions/{session_id}"},
                "session_messages": {"method": "GET", "path": "/api/sessions/{session_id}/messages"},
                "session_delete": {"method": "DELETE", "path": "/api/sessions/{session_id}"},
            },
        }
        try:
            result = self.module.validate_catalog(capabilities, self.toolsets)
        except self.module.RuntimeCheckError as error:
            self.fail("Valid session_resources/endpoints rejected: " + error.code)
        self.assertEqual(len(result["media_tools"]), 9)

    def test_session_endpoint_with_wrong_method_is_not_supported(self):
        self.capabilities["endpoints"]["session_delete"]["method"] = "GET"
        with self.assertRaises(self.module.RuntimeCheckError) as caught:
            self.module.validate_catalog(self.capabilities, self.toolsets)
        self.assertEqual(caught.exception.code, "missing_session_endpoints")

    def test_pinned_mcp_wire_names_use_double_underscore_boundaries(self):
        actual_tools = {"data": [{"name": "he", "enabled": True, "tools": [
            "mcp__he__search_media", "mcp__he__get_media_detail", "mcp__he__get_library_stats",
            "mcp__he__recommend_media", "mcp__he__list_duplicate_candidates", "mcp__he__list_tags",
            "mcp__he__list_folders", "mcp__he__propose_media_update", "mcp__he__propose_scan",
        ]}]}
        try:
            result = self.module.validate_catalog(self.capabilities, actual_tools)
        except self.module.RuntimeCheckError as error:
            self.fail("Pinned MCP wire names rejected: " + error.code)
        self.assertEqual(result["media_tools"][0], "mcp__he__get_library_stats")

    def test_native_catalog_omits_mcp_but_model_capture_proves_exact_tools(self):
        native = {"data": [{"name": "memory", "enabled": True, "tools": ["memory"]}]}
        actual = ["mcp__he__" + name for name in NINE] + ["memory"]
        try:
            result = self.module.validate_catalog(self.capabilities, native, model_tools=actual)
        except (TypeError, self.module.RuntimeCheckError) as error:
            self.fail("Actual native catalog and model schema rejected: " + str(error))
        self.assertEqual(len(result["media_tools"]), 9)

    def test_extra_model_schema_tool_is_rejected_even_if_native_catalog_is_safe(self):
        actual = ["mcp__he__" + name for name in NINE] + ["terminal"]
        try:
            self.module.validate_catalog(self.capabilities, self.toolsets, model_tools=actual)
        except self.module.RuntimeCheckError as error:
            self.assertEqual(error.code, "unexpected_tools")
        except TypeError:
            self.fail("Model schema evidence is not validated")
        else:
            self.fail("Unsafe actual model tool accepted")

    def test_measured_external_model_is_validated_against_protected_configuration(self):
        fixture = Path(__file__).parent / "fixtures/hermes/h01-evidence.json"
        evidence = json.loads(fixture.read_text())
        evidence["external"]["requested_model"] = "DeepSeek-V4.1-Flash"
        try:
            self.module.validate_evidence(evidence, expected_model="DeepSeek-V4.1-Flash")
        except (TypeError, self.module.RuntimeCheckError) as error:
            self.fail("Replacement model evidence was rejected: " + str(error))
        with self.assertRaises(self.module.RuntimeCheckError):
            self.module.validate_evidence(evidence, expected_model="minimax-m3")

    def test_empty_evidence_cannot_produce_total_pass(self):
        validator = getattr(self.module, "validate_evidence", None)
        self.assertIsNotNone(validator, "Evidence gate has not been implemented")
        with self.assertRaises(self.module.RuntimeCheckError) as caught:
            validator({})
        self.assertEqual(caught.exception.code, "incomplete_runtime_evidence")

    def test_sse_event_name_comes_from_json_and_unicode_is_preserved(self):
        parser = getattr(self.module, "parse_sse", None)
        self.assertIsNotNone(parser, "SSE parser has not been implemented")
        result = parser(': open\n\nid: 3\ndata: {"event":"message.delta",\ndata: "delta":"中文","seq":3}\n\n')
        self.assertEqual(result[0]["event"], "message.delta")
        self.assertEqual(result[0]["delta"], "中文")

    def test_oversize_sse_event_is_rejected_before_json_parse(self):
        parser = getattr(self.module, "parse_sse", None)
        self.assertIsNotNone(parser, "SSE parser has not been implemented")
        with self.assertRaises(self.module.RuntimeCheckError) as caught:
            parser('data: ' + 'a' * (128 * 1024 + 1) + '\n\n')
        self.assertEqual(caught.exception.code, "sse_event_too_large")

    def test_watchdog_exit_is_accepted_only_with_timed_stop_and_cancelled_result(self):
        validator = getattr(self.module, "validate_budget", None)
        self.assertIsNotNone(validator, "Watchdog evidence validator is missing")
        evidence = {"status": "cancelled", "turn_exit_reason": "interrupted_during_api_call",
                    "measured_seconds": 182, "sse_subscribers": 0,
                    "watchdog": {"deadline_seconds": 180, "stop_requested_age": 180.4,
                                 "stop_ack": {"status": "stopping"}}}
        validator(evidence)
        evidence["watchdog"]["stop_requested_age"] = 195
        with self.assertRaises(self.module.RuntimeCheckError):
            validator(evidence)

    def test_internal_authentication_is_never_forwarded_to_redirect_target(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        class Redirect(BaseHTTPRequestHandler):
            seen = []
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.seen.append(self.path)
                if self.path == "/health":
                    self.send_response(302)
                    self.send_header("Location", "/collector")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
        server = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            code, _ = self.module.live_read("http://127.0.0.1:" + str(server.server_port), "default", "SYNTHETIC_KEY_1234567890", "/health")
            self.assertEqual(code, 302)
            self.assertEqual(Redirect.seen, ["/health"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_malformed_catalog_yields_safe_error_code(self):
        for capabilities in (None, {"features": None}, {"features": [], "endpoints": {}}):
            try:
                self.module.validate_catalog(capabilities, self.toolsets)
            except self.module.RuntimeCheckError as error:
                self.assertEqual(error.code, "invalid_capabilities")
            except (AttributeError, TypeError) as error:
                self.fail("Raw malformed-data exception: " + type(error).__name__)
            else:
                self.fail("Malformed capabilities accepted")

    def test_null_profiles_yields_safe_error_before_evidence_or_network(self):
        try:
            self.module.check_runtime({"base_url": "http://127.0.0.1:8642", "profiles": None})
        except self.module.RuntimeCheckError as error:
            self.assertEqual(error.code, "invalid_probe_profiles")
        except TypeError:
            self.fail("Null profiles produces a raw exception")
        else:
            self.fail("Invalid profile data accepted")

    @unittest.skipIf(os.name == "nt", "POSIX credential mode check")
    def test_world_readable_config_is_rejected_before_network_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.json"
            config.write_text(json.dumps({"key": "TEST_SECRET_NEVER_PRINT"}))
            config.chmod(0o644)
            with self.assertRaises(self.module.RuntimeCheckError) as caught:
                self.module.load_config(config)
            self.assertEqual(caught.exception.code, "insecure_config")
            self.assertNotIn("TEST_SECRET_NEVER_PRINT", str(caught.exception))

    def test_arbitrary_public_tool_api_address_is_rejected(self):
        with self.assertRaises(self.module.RuntimeCheckError) as caught:
            self.module.validate_internal_base("https://evil.example/api")
        self.assertEqual(caught.exception.code, "invalid_internal_base")

    def test_report_contains_check_codes_and_never_raw_exceptions(self):
        error = self.module.RuntimeCheckError("unexpected_tools")
        report = self.module.failure_report(error)
        serialized = json.dumps(report)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["error_code"], "unexpected_tools")
        self.assertNotIn("traceback", serialized.lower())


if __name__ == "__main__":
    unittest.main()
