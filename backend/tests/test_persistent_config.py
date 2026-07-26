import json
import os
import stat
import tempfile
import unittest

from app import ai_config, database, external_config


@unittest.skipIf(os.name == "nt", "POSIX permission bits are not available on Windows")
class PersistentConfigTest(unittest.TestCase):
    def test_deepseek_config_migrates_and_is_owner_only(self):
        old_path = ai_config.CONFIG_PATH
        old_dir = ai_config.CONFIG_DIR
        old_legacy_path = ai_config.LEGACY_CONFIG_PATH
        old_legacy_dir = ai_config.LEGACY_CONFIG_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                legacy_dir = os.path.join(tmp, "legacy")
                data_dir = os.path.join(tmp, "data")
                os.makedirs(legacy_dir)
                legacy_path = os.path.join(legacy_dir, "deepseek.json")
                target_path = os.path.join(data_dir, "deepseek.json")
                with open(legacy_path, "w", encoding="utf-8") as file:
                    json.dump({"api_key": "sk-migrated", "model": "legacy-model"}, file)

                ai_config.LEGACY_CONFIG_DIR = legacy_dir
                ai_config.LEGACY_CONFIG_PATH = legacy_path
                ai_config.CONFIG_DIR = data_dir
                ai_config.CONFIG_PATH = target_path

                config = ai_config.get_deepseek_config()
                self.assertEqual(config["api_key"], "sk-migrated")
                self.assertTrue(os.path.isfile(target_path))
                self.assertEqual(stat.S_IMODE(os.stat(target_path).st_mode), 0o600)

                ai_config.update_deepseek_config(model="new-model")
                self.assertEqual(stat.S_IMODE(os.stat(target_path).st_mode), 0o600)
        finally:
            ai_config.CONFIG_PATH = old_path
            ai_config.CONFIG_DIR = old_dir
            ai_config.LEGACY_CONFIG_PATH = old_legacy_path
            ai_config.LEGACY_CONFIG_DIR = old_legacy_dir

    def test_external_config_and_database_files_are_owner_only(self):
        old_path = external_config.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = os.path.join(tmp, "library.db")
                ext_path = os.path.join(tmp, "external_config.json")
                deepseek_path = os.path.join(tmp, "deepseek.json")
                for path in (db_path, f"{db_path}-wal", ext_path, deepseek_path):
                    with open(path, "w", encoding="utf-8") as file:
                        file.write("{}")
                    os.chmod(path, 0o644)

                external_config.CONFIG_PATH = ext_path
                external_config.update_global_proxy("http://127.0.0.1:7890")
                self.assertEqual(stat.S_IMODE(os.stat(ext_path).st_mode), 0o600)

                old_ai_path = os.environ.get("HE_AI_CONFIG_PATH")
                os.environ["HE_AI_CONFIG_PATH"] = deepseek_path
                try:
                    database.secure_data_permissions(f"sqlite:///{db_path}")
                finally:
                    if old_ai_path is None:
                        os.environ.pop("HE_AI_CONFIG_PATH", None)
                    else:
                        os.environ["HE_AI_CONFIG_PATH"] = old_ai_path

                self.assertEqual(stat.S_IMODE(os.stat(tmp).st_mode), 0o700)
                for path in (db_path, f"{db_path}-wal", ext_path, deepseek_path):
                    self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        finally:
            external_config.CONFIG_PATH = old_path


if __name__ == "__main__":
    unittest.main()
