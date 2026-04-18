from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BridgeConfig

BRIDGE_LABEL = "ai.hermes.dingtalk-bridge"
HERMES_GATEWAY_LABEL = "ai.hermes.gateway"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
BRIDGE_PLIST_PATH = LAUNCH_AGENTS_DIR / f"{BRIDGE_LABEL}.plist"
HERMES_GATEWAY_PLIST = LAUNCH_AGENTS_DIR / f"{HERMES_GATEWAY_LABEL}.plist"


@dataclass
class ServiceStatus:
    installed: bool
    loaded: bool
    plist_path: str
    details: dict[str, Any]


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], text=True, capture_output=True)


def _read_gateway_env() -> dict[str, str]:
    if not HERMES_GATEWAY_PLIST.exists():
        return {}
    with HERMES_GATEWAY_PLIST.open("rb") as fh:
        plist = plistlib.load(fh)
    env = plist.get("EnvironmentVariables") or {}
    return {str(k): str(v) for k, v in env.items()}


def build_launchd_plist(config: BridgeConfig) -> dict[str, Any]:
    env = _read_gateway_env()
    env.setdefault("PATH", os.environ.get("PATH", ""))
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return {
        "Label": BRIDGE_LABEL,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "hermes_dingtalk_bridge",
            "run",
        ],
        "WorkingDirectory": str(Path(__file__).resolve().parents[1]),
        "EnvironmentVariables": env,
        "RunAtLoad": True,
        "KeepAlive": {
            "OtherJobEnabled": {HERMES_GATEWAY_LABEL: True},
            "SuccessfulExit": False,
        },
        "StandardOutPath": str(Path.home() / ".hermes" / "logs" / "dingtalk-bridge.log"),
        "StandardErrorPath": str(Path.home() / ".hermes" / "logs" / "dingtalk-bridge.error.log"),
    }


def install_service(config: BridgeConfig) -> ServiceStatus:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    (Path.home() / ".hermes" / "logs").mkdir(parents=True, exist_ok=True)
    plist = build_launchd_plist(config)
    with BRIDGE_PLIST_PATH.open("wb") as fh:
        plistlib.dump(plist, fh)
    uid = str(os.getuid())
    _launchctl("bootout", f"gui/{uid}", str(BRIDGE_PLIST_PATH))
    _launchctl("bootstrap", f"gui/{uid}", str(BRIDGE_PLIST_PATH))
    gateway_loaded = service_status().details.get("gateway_loaded", False)
    if gateway_loaded:
        _launchctl("kickstart", "-k", f"gui/{uid}/{BRIDGE_LABEL}")
    return service_status()


def uninstall_service() -> ServiceStatus:
    uid = str(os.getuid())
    _launchctl("bootout", f"gui/{uid}", str(BRIDGE_PLIST_PATH))
    if BRIDGE_PLIST_PATH.exists():
        BRIDGE_PLIST_PATH.unlink()
    return service_status()


def service_status() -> ServiceStatus:
    uid = str(os.getuid())
    bridge_print = _launchctl("print", f"gui/{uid}/{BRIDGE_LABEL}")
    gateway_print = _launchctl("print", f"gui/{uid}/{HERMES_GATEWAY_LABEL}")
    return ServiceStatus(
        installed=BRIDGE_PLIST_PATH.exists(),
        loaded=bridge_print.returncode == 0,
        plist_path=str(BRIDGE_PLIST_PATH),
        details={
            "bridge_stdout": bridge_print.stdout[:500],
            "bridge_stderr": bridge_print.stderr[:500],
            "gateway_loaded": gateway_print.returncode == 0,
            "gateway_stdout": gateway_print.stdout[:300],
            "gateway_stderr": gateway_print.stderr[:300],
        },
    )
