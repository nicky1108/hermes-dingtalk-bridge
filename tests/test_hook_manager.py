import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes_dingtalk_bridge import hook_manager


class HookManagerTests(unittest.TestCase):
    def test_install_and_uninstall_hook(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with mock.patch('hermes_dingtalk_bridge.hook_manager.get_hermes_home', return_value=fake_home):
                status = hook_manager.install_hook(interactive=False)
                self.assertTrue(status.installed)
                self.assertTrue(status.details['setup_pending'])
                hook_dir = fake_home / 'hooks' / hook_manager.HOOK_NAME
                self.assertTrue((hook_dir / 'HOOK.yaml').exists())
                self.assertTrue((hook_dir / 'handler.py').exists())
                removed = hook_manager.uninstall_hook()
                self.assertFalse(removed.installed)

    def test_install_hook_bootstraps_missing_credentials_and_card_config(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with mock.patch('hermes_dingtalk_bridge.hook_manager.get_hermes_home', return_value=fake_home), \
                 mock.patch('builtins.input', side_effect=['client-id', 'card', 'tpl.schema']), \
                 mock.patch('getpass.getpass', side_effect=['client-secret', 'api-key']):
                status = hook_manager.install_hook(interactive=True)
                self.assertTrue(status.installed)
                self.assertFalse(status.details['setup_pending'])
                self.assertEqual(
                    status.details['prompted_fields'],
                    ['client_id', 'client_secret', 'api_server_key', 'reply_mode', 'card_template_id'],
                )
                env_text = (fake_home / '.env').read_text(encoding='utf-8')
                self.assertIn('HERMES_DINGTALK_CLIENT_ID=client-id', env_text)
                self.assertIn('HERMES_DINGTALK_CLIENT_SECRET=client-secret', env_text)
                self.assertIn('API_SERVER_KEY=api-key', env_text)
                config_text = (fake_home / 'dingtalk-bridge.yaml').read_text(encoding='utf-8')
                self.assertIn('reply_mode: card', config_text)
                self.assertIn('card_template_id: tpl.schema', config_text)

    def test_uninstall_hook_removes_pycache_directory(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with mock.patch('hermes_dingtalk_bridge.hook_manager.get_hermes_home', return_value=fake_home):
                status = hook_manager.install_hook(interactive=False)
                self.assertTrue(status.installed)
                pycache = fake_home / 'hooks' / hook_manager.HOOK_NAME / '__pycache__'
                pycache.mkdir(parents=True, exist_ok=True)
                (pycache / 'handler.cpython-311.pyc').write_bytes(b'compiled')
                removed = hook_manager.uninstall_hook()
                self.assertFalse(removed.installed)
                self.assertFalse((fake_home / 'hooks' / hook_manager.HOOK_NAME).exists())
