from __future__ import annotations

import getpass
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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


def _config_path() -> Path:
    return get_hermes_home() / 'dingtalk-bridge.yaml'


def _env_path() -> Path:
    return get_hermes_home() / '.env'


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    return data if isinstance(data, dict) else {}


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _bridge_section_for_write(doc: dict[str, Any]) -> dict[str, Any]:
    current = doc.get('dingtalk_bridge')
    if isinstance(current, dict):
        return current
    plugins = doc.get('plugins')
    if isinstance(plugins, dict):
        nested = plugins.get('hermes_dingtalk')
        if isinstance(nested, dict):
            return nested
    section: dict[str, Any] = {}
    doc['dingtalk_bridge'] = section
    return section


def _resolved_value(config: dict[str, Any], dotenv: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value:
            return str(value).strip()
        value = dotenv.get(key)
        if value:
            return str(value).strip()
    for key in keys:
        value = config.get(key)
        if value:
            return str(value).strip()
    return ''


def _can_prompt() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _prompt_nonempty(label: str, *, secret: bool = False) -> str:
    while True:
        value = getpass.getpass(f'{label}: ') if secret else input(f'{label}: ')
        value = value.strip()
        if value:
            return value
        print(f'{label} is required.')


def _prompt_reply_mode() -> str:
    while True:
        value = input('Reply mode [markdown/card] (default: markdown): ').strip().lower()
        if not value:
            return 'markdown'
        if value in {'markdown', 'card'}:
            return value
        if value in {'1', 'm'}:
            return 'markdown'
        if value in {'2', 'c'}:
            return 'card'
        print('Please enter markdown or card.')


def _write_dotenv(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    remaining = dict(updates)
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            out_lines.append(line)
            continue
        key, _ = line.split('=', 1)
        key = key.strip()
        if key in remaining:
            out_lines.append(f'{key}={remaining.pop(key)}')
        else:
            out_lines.append(line)
    if remaining:
        if out_lines and out_lines[-1].strip():
            out_lines.append('')
        for key, value in remaining.items():
            out_lines.append(f'{key}={value}')
    path.write_text('\n'.join(out_lines).rstrip() + '\n', encoding='utf-8')


def _write_bridge_config(path: Path, reply_mode: str, card_template_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _load_yaml(path)
    section = _bridge_section_for_write(doc)
    section['reply_mode'] = reply_mode
    section['card_template_id'] = card_template_id if reply_mode == 'card' else ''
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding='utf-8')


def _ensure_runtime_setup(*, interactive: bool) -> dict[str, Any]:
    config_path = _config_path()
    env_path = _env_path()
    raw_doc = _load_yaml(config_path)
    bridge_config = _bridge_section_for_write(raw_doc)
    dotenv = _load_dotenv(env_path)

    current_client_id = _resolved_value(
        bridge_config,
        dotenv,
        'HERMES_DINGTALK_CLIENT_ID',
        'DINGTALK_CLIENT_ID',
        'client_id',
    )
    current_client_secret = _resolved_value(
        bridge_config,
        dotenv,
        'HERMES_DINGTALK_CLIENT_SECRET',
        'DINGTALK_CLIENT_SECRET',
        'client_secret',
    )
    current_reply_mode = _resolved_value(
        bridge_config,
        dotenv,
        'HERMES_DINGTALK_REPLY_MODE',
        'reply_mode',
    )
    current_card_template_id = _resolved_value(
        bridge_config,
        dotenv,
        'HERMES_DINGTALK_CARD_TEMPLATE_ID',
        'card_template_id',
    )

    prompted_fields: list[str] = []
    env_updates: dict[str, str] = {}
    reply_mode = current_reply_mode or 'markdown'
    card_template_id = current_card_template_id
    needs_prompt = False

    if not current_client_id:
        if interactive:
            env_updates['HERMES_DINGTALK_CLIENT_ID'] = _prompt_nonempty('DingTalk Client ID')
            prompted_fields.append('client_id')
        else:
            needs_prompt = True
    if not current_client_secret:
        if interactive:
            env_updates['HERMES_DINGTALK_CLIENT_SECRET'] = _prompt_nonempty('DingTalk Client Secret', secret=True)
            prompted_fields.append('client_secret')
        else:
            needs_prompt = True
    if not current_reply_mode:
        if interactive:
            reply_mode = _prompt_reply_mode()
            prompted_fields.append('reply_mode')
        else:
            needs_prompt = True
    if reply_mode == 'card' and not current_card_template_id:
        if interactive:
            card_template_id = _prompt_nonempty('DingTalk Card Template ID')
            prompted_fields.append('card_template_id')
        else:
            needs_prompt = True

    if env_updates:
        _write_dotenv(env_path, env_updates)
    if interactive and ('reply_mode' in prompted_fields or 'card_template_id' in prompted_fields):
        _write_bridge_config(config_path, reply_mode, card_template_id)

    return {
        'interactive_setup_ran': bool(prompted_fields),
        'prompted_fields': prompted_fields,
        'setup_pending': needs_prompt,
        'config_path': str(config_path),
        'env_path': str(env_path),
        'reply_mode': reply_mode,
        'card_template_id_configured': bool(card_template_id),
    }


def install_hook(*, interactive: bool | None = None) -> HookStatus:
    setup_details = _ensure_runtime_setup(interactive=_can_prompt() if interactive is None else interactive)
    hook_dir = _hook_dir()
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / 'HOOK.yaml').write_text(
        'name: hermes-dingtalk-bridge\n'
        'description: Autostart Hermes DingTalk bridge when gateway starts\n'
        'events:\n  - gateway:startup\n',
        encoding='utf-8',
    )
    handler = (
        "from __future__ import annotations\n\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        f"_PLUGIN_ROOT = Path({str(_repo_root())!r})\n"
        "if str(_PLUGIN_ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(_PLUGIN_ROOT))\n\n"
        "from hermes_dingtalk_bridge.gateway_runtime import autostart_bridge_from_gateway_hook\n\n\n"
        "async def handle(event_type, context):\n"
        "    autostart_bridge_from_gateway_hook()\n"
    )
    (hook_dir / 'handler.py').write_text(handler, encoding='utf-8')
    result = status()
    result.details.update(setup_details)
    return result


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
