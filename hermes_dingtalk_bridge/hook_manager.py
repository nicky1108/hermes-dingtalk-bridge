from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from hermes_constants import get_hermes_home
except Exception:  # pragma: no cover - fallback outside Hermes runtime
    def get_hermes_home():
        return Path.home() / ".hermes"


HOOK_NAME = 'hermes-dingtalk-bridge'


@dataclass
class HookStatus:
    installed: bool
    hook_dir: str
    details: dict[str, Any]


def _hooks_root() -> Path:
    root = get_hermes_home() / 'hooks'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _hook_dir() -> Path:
    return _hooks_root() / HOOK_NAME


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def install_hook() -> HookStatus:
    hook_dir = _hook_dir()
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_yaml = {
        'name': HOOK_NAME,
        'description': 'Autostart Hermes DingTalk bridge when gateway starts',
        'events': ['gateway:startup'],
    }
    (hook_dir / 'HOOK.yaml').write_text(
        'name: hermes-dingtalk-bridge\n'
        'description: Autostart Hermes DingTalk bridge when gateway starts\n'
        'events:\n  - gateway:startup\n',
        encoding='utf-8',
    )
    handler = f'''from __future__ import annotations\n\nimport sys\nfrom pathlib import Path\n\n_PLUGIN_ROOT = Path({str(_repo_root())!r})\nif str(_PLUGIN_ROOT) not in sys.path:\n    sys.path.insert(0, str(_PLUGIN_ROOT))\n\nfrom hermes_dingtalk_bridge.gateway_runtime import autostart_bridge_from_gateway_hook\n\n\nasync def handle(event_type, context):\n    autostart_bridge_from_gateway_hook()\n'''
    (hook_dir / 'handler.py').write_text(handler, encoding='utf-8')
    return status()


def uninstall_hook() -> HookStatus:
    hook_dir = _hook_dir()
    if hook_dir.exists():
        for child in hook_dir.iterdir():
            child.unlink()
        hook_dir.rmdir()
    return status()


def status() -> HookStatus:
    hook_dir = _hook_dir()
    return HookStatus(
        installed=(hook_dir / 'HOOK.yaml').exists() and (hook_dir / 'handler.py').exists(),
        hook_dir=str(hook_dir),
        details={
            'hook_yaml_exists': (hook_dir / 'HOOK.yaml').exists(),
            'handler_exists': (hook_dir / 'handler.py').exists(),
            'repo_root': str(_repo_root()),
        },
    )
