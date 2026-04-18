import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes_dingtalk_bridge.config import load_config


class ConfigTests(unittest.TestCase):
    def test_env_overrides_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            config_path = Path(td) / "bridge.yaml"
            config_path.write_text(
                "client_id: yaml-id\nclient_secret: yaml-secret\nhermes_api_key: yaml-key\n",
                encoding="utf-8",
            )
            os.environ["HERMES_DINGTALK_CLIENT_ID"] = "env-id"
            os.environ["HERMES_DINGTALK_CLIENT_SECRET"] = "env-secret"
            os.environ["API_SERVER_KEY"] = "env-key"
            try:
                cfg = load_config(config_path)
            finally:
                os.environ.pop("HERMES_DINGTALK_CLIENT_ID", None)
                os.environ.pop("HERMES_DINGTALK_CLIENT_SECRET", None)
                os.environ.pop("API_SERVER_KEY", None)
            self.assertEqual(cfg.client_id, "env-id")
            self.assertEqual(cfg.client_secret, "env-secret")
            self.assertEqual(cfg.hermes_api_key, "env-key")

    def test_dotenv_fallbacks_to_existing_hermes_names(self):
        with tempfile.TemporaryDirectory() as td:
            config_path = Path(td) / "bridge.yaml"
            config_path.write_text("{}", encoding="utf-8")
            dotenv_path = Path(td) / ".env"
            dotenv_path.write_text(
                "DINGTALK_CLIENT_ID=legacy-id\nDINGTALK_CLIENT_SECRET=legacy-secret\nAPI_SERVER_KEY=api-key\n",
                encoding="utf-8",
            )
            with mock.patch("hermes_dingtalk_bridge.config.DEFAULT_ENV_PATH", dotenv_path):
                cfg = load_config(config_path)
            self.assertEqual(cfg.client_id, "legacy-id")
            self.assertEqual(cfg.client_secret, "legacy-secret")
            self.assertEqual(cfg.hermes_api_key, "api-key")

    def test_reads_stream_read_timeout_from_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            config_path = Path(td) / "bridge.yaml"
            config_path.write_text(
                "stream_read_timeout_seconds: 240\n",
                encoding="utf-8",
            )
            cfg = load_config(config_path)
            self.assertEqual(cfg.stream_read_timeout_seconds, 240)
