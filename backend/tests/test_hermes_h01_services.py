"""The fake provider is deterministic and cannot access HE data."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parent / "fixtures/hermes/h01_services.py"


class H01ServicesTests(unittest.TestCase):
    def setUp(self):
        if not MODULE.exists():
            self.fail("H01 synthetic service has not been implemented")
        spec = importlib.util.spec_from_file_location("h01_services", MODULE)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_search_requests_exact_registered_tool(self):
        body = {"model": "h01-model", "messages": [{"role": "user", "content": "H01 SEARCH"}],
                "tools": [{"type": "function", "function": {"name": "mcp__he__search_media"}}]}
        reply = self.mod.make_completion(body)
        call = reply["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "mcp__he__search_media")
        self.assertEqual(call["function"]["arguments"], '{"query": "fixture"}')

    def test_tool_result_causes_final_answer_instead_of_another_call(self):
        reply = self.mod.make_completion({"model": "h01-model", "messages": [
            {"role": "user", "content": "H01 SEARCH"}, {"role": "tool", "content": "fixed synthetic data"}]})
        self.assertEqual(reply["choices"][0]["finish_reason"], "stop")
        self.assertEqual(reply["choices"][0]["message"]["content"], "H01 synthetic operation completed.")

    def test_loop_fixture_keeps_requesting_tools_after_previous_result(self):
        reply = self.mod.make_completion({"messages": [{"role": "user", "content": "H01 LOOP"},
            {"role": "tool", "content": "fixed"}], "tools": [{"function": {"name": "mcp__he__search_media"}}]})
        self.assertEqual(reply["choices"][0]["finish_reason"], "tool_calls")

    def test_proposal_fixture_calls_write_annotated_tool(self):
        reply = self.mod.make_completion({"messages": [{"role": "user", "content": "H01 PROPOSAL"}],
            "tools": [{"function": {"name": "mcp__he__propose_scan"}}]})
        self.assertEqual(reply["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "mcp__he__propose_scan")

    def test_capture_omits_prompts_and_credentials(self):
        capture = self.mod.catalog_snapshot({"messages": [{"role": "user", "content": "DO_NOT_CAPTURE_SECRET"}],
            "tools": [{"function": {"name": "memory"}}], "max_tokens": 2048, "model": "h01-model"})
        self.assertEqual(capture["tool_names"], ["memory"])
        self.assertEqual(capture["max_tokens"], 2048)
        self.assertNotIn("DO_NOT_CAPTURE_SECRET", str(capture))


if __name__ == "__main__":
    unittest.main()
