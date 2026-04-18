from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import signal
from typing import Optional

from .config import load_config
from .gateway_runtime import autostart_bridge_if_gateway
from .hook_manager import install_hook, status as hook_status, uninstall_hook
from .logging_utils import configure_logging
from .service import BridgeService
from .service_manager import install_service, service_status, uninstall_service


async def _run_bridge(args) -> int:
    config = load_config(args.config)
    logger = configure_logging(config.log_level)
    service = BridgeService(config)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop(*_):
        logger.info("Stopping Hermes DingTalk bridge")
        service.shutdown()
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    runner = asyncio.create_task(service.run())
    waiter = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait({runner, waiter}, return_when=asyncio.FIRST_COMPLETED)
    if waiter in done and not runner.done():
        runner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runner
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if runner in done:
        exc = runner.exception()
        if exc:
            raise exc
    return 0


def _cmd_run(args) -> int:
    return asyncio.run(_run_bridge(args))


def _cmd_doctor(args) -> int:
    config = load_config(args.config)
    configure_logging(config.log_level)
    service = BridgeService(config)
    try:
        result = service.doctor()
        print(json.dumps({"ok": result.ok, "message": result.message, "details": result.details}, indent=2, ensure_ascii=False))
        return 0 if result.ok else 1
    finally:
        service.store.close()


def _cmd_status(args) -> int:
    config = load_config(args.config)
    result = {
        "config_path": str(config.config_path),
        "store_path": str(config.store_path),
        "account_id": config.account_id,
        "conversation_prefix": config.conversation_prefix,
        "require_mention_in_groups": config.require_mention_in_groups,
        "group_allowlist": list(config.group_allowlist),
        "dm_allowlist": list(config.dm_allowlist),
        "hermes_api_base": config.hermes_api_base,
        "reply_mode": config.reply_mode,
        "card_template_id": config.card_template_id,
        "ack_reaction_enabled": config.ack_reaction_enabled,
        "ack_reaction_name": config.ack_reaction_name,
        "runtime_status_path": str(config.store_path.with_suffix('.status.json')),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_service_install(args) -> int:
    config = load_config(args.config)
    status = install_service(config)
    print(json.dumps(status.__dict__, indent=2, ensure_ascii=False))
    return 0


def _cmd_service_uninstall(args) -> int:
    status = uninstall_service()
    print(json.dumps(status.__dict__, indent=2, ensure_ascii=False))
    return 0


def _cmd_service_status(args) -> int:
    status = service_status()
    print(json.dumps(status.__dict__, indent=2, ensure_ascii=False))
    return 0




def _cmd_hook_install(args) -> int:
    status = install_hook()
    print(json.dumps(status.__dict__, indent=2, ensure_ascii=False))
    return 0


def _cmd_hook_uninstall(args) -> int:
    status = uninstall_hook()
    print(json.dumps(status.__dict__, indent=2, ensure_ascii=False))
    return 0


def _cmd_hook_status(args) -> int:
    status = hook_status()
    print(json.dumps(status.__dict__, indent=2, ensure_ascii=False))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-dingtalk-bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the DingTalk bridge")
    run_parser.add_argument("--config", help="Path to dingtalk bridge yaml config")
    run_parser.set_defaults(func=_cmd_run)

    doctor_parser = sub.add_parser("doctor", help="Validate config and Hermes connectivity")
    doctor_parser.add_argument("--config", help="Path to dingtalk bridge yaml config")
    doctor_parser.set_defaults(func=_cmd_doctor)

    status_parser = sub.add_parser("status", help="Print the resolved bridge configuration")
    status_parser.add_argument("--config", help="Path to dingtalk bridge yaml config")
    status_parser.set_defaults(func=_cmd_status)

    service_parser = sub.add_parser("service", help="Manage the companion launchd bridge service")
    service_sub = service_parser.add_subparsers(dest="service_command", required=True)
    service_install = service_sub.add_parser("install", help="Install/load the companion bridge launchd job")
    service_install.add_argument("--config", help="Path to dingtalk bridge yaml config")
    service_install.set_defaults(func=_cmd_service_install)
    service_uninstall = service_sub.add_parser("uninstall", help="Unload/remove the companion bridge launchd job")
    service_uninstall.set_defaults(func=_cmd_service_uninstall)
    service_status = service_sub.add_parser("status", help="Show companion bridge launchd job status")
    service_status.set_defaults(func=_cmd_service_status)

    hook_parser = sub.add_parser("hook", help="Manage the startup hook that autostarts the bridge inside Hermes gateway")
    hook_sub = hook_parser.add_subparsers(dest="hook_command", required=True)
    hook_install = hook_sub.add_parser("install", help="Install the gateway startup hook")
    hook_install.set_defaults(func=_cmd_hook_install)
    hook_uninstall = hook_sub.add_parser("uninstall", help="Remove the gateway startup hook")
    hook_uninstall.set_defaults(func=_cmd_hook_uninstall)
    hook_status = hook_sub.add_parser("status", help="Show gateway startup hook status")
    hook_status.set_defaults(func=_cmd_hook_status)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _slash_command(raw_args: str) -> str:
    command = raw_args.strip().split(maxsplit=1)[0] if raw_args.strip() else "status"
    if command == "doctor":
        exit_code = _cmd_doctor(argparse.Namespace(config=None))
        return "hermes-dingtalk doctor passed" if exit_code == 0 else "hermes-dingtalk doctor failed"
    if command == "status":
        return "Use `python3 -m hermes_dingtalk_bridge status` for full status output."
    if command == "run":
        return "Use `python3 -m hermes_dingtalk_bridge run` to start the bridge process."
    if command == "service":
        return "Use `python3 -m hermes_dingtalk_bridge service status` to inspect the companion launchd job."
    if command == "hook":
        return "Use `python3 -m hermes_dingtalk_bridge hook status` to inspect the gateway startup hook."
    return "Usage: /dingtalk-bridge [status|doctor|run|service|hook]"


def register(ctx) -> None:
    autostart_bridge_if_gateway()
    ctx.register_command(
        name="dingtalk-bridge",
        handler=_slash_command,
        description="Show Hermes DingTalk bridge help/status hints.",
    )
    try:
        ctx.register_cli_command(
            name="dingtalk",
            help="Manage the Hermes DingTalk bridge",
            setup_fn=_register_cli,
            description="Start, inspect, and validate the standalone DingTalk bridge.",
        )
    except Exception:
        pass


def _register_cli(parser) -> None:
    sub = parser.add_subparsers(dest="dingtalk_command", required=True)
    run_parser = sub.add_parser("run", help="Run the DingTalk bridge")
    run_parser.add_argument("--config", help="Path to dingtalk bridge yaml config")
    run_parser.set_defaults(func=_cmd_run)
    doctor_parser = sub.add_parser("doctor", help="Validate config and Hermes connectivity")
    doctor_parser.add_argument("--config", help="Path to dingtalk bridge yaml config")
    doctor_parser.set_defaults(func=_cmd_doctor)
    status_parser = sub.add_parser("status", help="Print the resolved bridge configuration")
    status_parser.add_argument("--config", help="Path to dingtalk bridge yaml config")
    status_parser.set_defaults(func=_cmd_status)
    service_parser = sub.add_parser("service", help="Manage companion launchd service")
    service_sub = service_parser.add_subparsers(dest="service_command", required=True)
    install_parser = service_sub.add_parser("install", help="Install/load companion bridge service")
    install_parser.add_argument("--config", help="Path to dingtalk bridge yaml config")
    install_parser.set_defaults(func=_cmd_service_install)
    uninstall_parser = service_sub.add_parser("uninstall", help="Unload/remove companion bridge service")
    uninstall_parser.set_defaults(func=_cmd_service_uninstall)
    status_service_parser = service_sub.add_parser("status", help="Show companion bridge service status")
    status_service_parser.set_defaults(func=_cmd_service_status)
    hook_parser = sub.add_parser("hook", help="Manage gateway startup hook")
    hook_sub = hook_parser.add_subparsers(dest="hook_command", required=True)
    install_hook_parser = hook_sub.add_parser("install", help="Install the gateway startup hook")
    install_hook_parser.set_defaults(func=_cmd_hook_install)
    uninstall_hook_parser = hook_sub.add_parser("uninstall", help="Remove the gateway startup hook")
    uninstall_hook_parser.set_defaults(func=_cmd_hook_uninstall)
    status_hook_parser = hook_sub.add_parser("status", help="Show gateway startup hook status")
    status_hook_parser.set_defaults(func=_cmd_hook_status)
