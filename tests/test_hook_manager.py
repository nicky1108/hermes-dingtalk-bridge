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
                status = hook_manager.install_hook()
                self.assertTrue(status.installed)
                hook_dir = fake_home / 'hooks' / hook_manager.HOOK_NAME
                self.assertTrue((hook_dir / 'HOOK.yaml').exists())
                self.assertTrue((hook_dir / 'handler.py').exists())
                removed = hook_manager.uninstall_hook()
                self.assertFalse(removed.installed)
