import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models as he_models


class AssistantModelSwitcherTests(unittest.TestCase):
    def setUp(self):
        self.identity = importlib.import_module("app.assistant.identity")
        self.models = importlib.import_module("app.assistant.models")
        self.config = importlib.import_module("app.assistant.config")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = create_engine("sqlite:///" + str(self.root / "test.db"))
        he_models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(
            he_models.User(
                id=1,
                username="admin",
                password_hash="unused",
                is_admin=True,
                is_active=True,
            )
        )
        self.db.commit()

        self.model_key = "synthetic_deepseek_key_" + ("a" * 30)
        self.model_path = self.root / "assistant/hermes-model.json"
        self.model_path.parent.mkdir(parents=True, mode=0o700)
        self.model_path.write_text(
            json.dumps(
                {
                    "provider": "custom",
                    "model": "deepseek-flash",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": self.model_key,
                    "display_model": "DeepSeek-V4.1-Flash",
                    "extra_body": {"thinking": {"type": "disabled"}},
                }
            )
        )
        self.model_path.chmod(0o600)

        self.env = patch.dict(
            os.environ,
            {
                "HE_ASSISTANT_ENABLED": "1",
                "HE_ASSISTANT_DATA_DIR": str(self.root / "assistant"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.db.close)
        self.addCleanup(self.tmp.cleanup)

        self.profile_root = self.root / "hermes"
        self.identity.prepare_profile(self.db, 1, profile_root=self.profile_root)

    def test_get_summary_returns_presets_without_exposing_api_key(self):
        summary = self.config.get_model_config_summary()
        self.assertEqual(summary["model"], "deepseek-flash")
        self.assertEqual(summary["display_model"], "DeepSeek-V4.1-Flash")
        self.assertTrue(summary["key_configured"])
        self.assertTrue(summary["thinking_disabled"])
        self.assertEqual(
            [p["id"] for p in summary["presets"]],
            ["deepseek-flash", "deepseek-chat", "deepseek-reasoner"],
        )
        self.assertNotIn(self.model_key, json.dumps(summary))

    def test_switch_builtin_preset_and_save_custom_preset_syncs_profile_files(self):
        switched = self.identity.update_model_config(
            self.db,
            1,
            {"preset_id": "deepseek-reasoner"},
            profile_root=self.profile_root,
        )
        self.assertEqual(switched["model"], "deepseek-reasoner")
        self.assertFalse(switched["thinking_disabled"])
        cfg_text = (self.profile_root / "profiles/he-user-1/config.yaml").read_text()
        self.assertIn('default: "deepseek-reasoner"', cfg_text)
        self.assertIn('default_model: "deepseek-reasoner"', cfg_text)
        self.assertNotIn("thinking:\n        type: disabled", cfg_text)

        new_key = "synthetic_custom_key_" + ("b" * 30)
        custom = self.identity.update_model_config(
            self.db,
            1,
            {
                "model": "gpt-4o-mini",
                "display_model": "GPT-4o Mini",
                "base_url": "https://api.openai.com/v1",
                "api_key": new_key,
                "thinking_disabled": False,
                "save_preset": True,
            },
            profile_root=self.profile_root,
        )
        self.assertEqual(custom["model"], "gpt-4o-mini")
        self.assertEqual(custom["base_url"], "https://api.openai.com/v1")
        self.assertNotIn(new_key, json.dumps(custom))
        self.assertTrue(any(p["model"] == "gpt-4o-mini" and p["custom"] for p in custom["presets"]))

        env_text = (self.profile_root / "profiles/he-user-1/.env").read_text()
        self.assertIn("HE_ASSISTANT_MODEL_KEY=" + new_key, env_text)
        cfg_text_2 = (self.profile_root / "profiles/he-user-1/config.yaml").read_text()
        self.assertIn('base_url: "https://api.openai.com/v1"', cfg_text_2)

        # Switch back to DeepSeek preset and delete custom preset
        custom_id = next(p["id"] for p in custom["presets"] if p["custom"])
        self.identity.update_model_config(
            self.db,
            1,
            {
                "model": "deepseek-chat",
                "display_model": "DeepSeek Chat",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": self.model_key,
                "thinking_disabled": True,
            },
            profile_root=self.profile_root,
        )
        after_delete = self.identity.update_model_config(
            self.db,
            1,
            {"delete_preset_id": custom_id},
            profile_root=self.profile_root,
        )
        self.assertFalse(any(p["id"] == custom_id for p in after_delete["presets"]))

    def test_rejects_switch_while_run_is_active(self):
        sid = str(uuid4())
        self.db.add(
            self.models.AssistantSession(
                id=sid,
                user_id=1,
                upstream_session_id="he-" + sid,
                state="active",
                title="Active",
            )
        )
        self.db.add(
            self.models.AssistantRun(
                id=str(uuid4()),
                user_id=1,
                session_id=sid,
                client_request_id=str(uuid4()),
                input_hash="h",
                status="running",
                api_key_generation=1,
                created_at=datetime.utcnow(),
            )
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.identity.update_model_config(
                self.db,
                1,
                {"preset_id": "deepseek-chat"},
                profile_root=self.profile_root,
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail, "assistant_operation_busy")
