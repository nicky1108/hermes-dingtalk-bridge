# Hermes DingTalk Bridge

Standalone DingTalk bridge for Hermes Agent.

## What this project is

This project avoids modifying Hermes core or Hermes' built-in DingTalk adapter.
It runs as an external bridge:

```text
DingTalk Stream/OpenAPI <-> hermes-dingtalk-bridge <-> Hermes API Server (/v1/responses)
```

The repository is structured as a Hermes plugin. The preferred integration path is a gateway startup hook that autostarts the bridge inside the Hermes gateway process, so the bridge follows the Hermes gateway lifecycle without patching Hermes core.

## Features

- DingTalk Stream inbound bridge to Hermes `/v1/responses`
- Session binding and dedup store in `~/.hermes/dingtalk-bridge.db`
- Direct-message and group-mention access control
- Native DingTalk ack reaction (`🤔思考中`) when a message is received
- Configurable reply mode:
  - `markdown`
  - `card` with `card_template_id`
- Markdown fallback if card delivery fails
- Companion launchd service management for macOS so the bridge can follow Hermes gateway lifecycle

## Layout

- `plugin.yaml` / `__init__.py` — Hermes plugin shell
- `hermes_dingtalk_bridge/` — runtime bridge implementation
- `tests/` — unit tests for config, parser, session store, and service logic

## Running

```bash
cp dingtalk-bridge.example.yaml ~/.hermes/dingtalk-bridge.yaml
python3 -m hermes_dingtalk_bridge run
python3 -m hermes_dingtalk_bridge doctor
python3 -m hermes_dingtalk_bridge status
python3 -m hermes_dingtalk_bridge hook status
```

The repository is also symlink-friendly for Hermes plugin discovery. For example:

```bash
mkdir -p ~/.hermes/plugins
ln -sfn "$PWD" ~/.hermes/plugins/hermes-dingtalk
```

## Required environment

Preferred explicit vars:

- `HERMES_DINGTALK_CLIENT_ID`
- `HERMES_DINGTALK_CLIENT_SECRET`
- `API_SERVER_KEY`

The bridge also falls back to Hermes' existing `~/.hermes/.env` entries:

- `DINGTALK_CLIENT_ID`
- `DINGTALK_CLIENT_SECRET`
- `API_SERVER_KEY`

Optional:

- `HERMES_DINGTALK_HERMES_API_BASE` (default `http://127.0.0.1:8642/v1`)
- `HERMES_DINGTALK_MODEL` (default `hermes-agent`)
- `HERMES_DINGTALK_REQUIRE_MENTION_IN_GROUPS` (default `true`)
- `HERMES_DINGTALK_STORE_PATH`
- `HERMES_DINGTALK_LOG_LEVEL`
- `HERMES_DINGTALK_REPLY_MODE` (`markdown` or `card`)
- `HERMES_DINGTALK_CARD_TEMPLATE_ID`

## Card replies

When `reply_mode=card`, the bridge tries to send the Hermes answer using DingTalk card delivery APIs and the configured `card_template_id`.
If the app is missing DingTalk card permissions or the template mapping does not match, the bridge falls back to a normal markdown reply.

Example config:

```yaml
dingtalk_bridge:
  reply_mode: card
  card_template_id: afe7d987-a565-49e0-96d3-c090e954a7cd.schema
```

## Lifecycle integration with Hermes gateway

The primary integration is a **gateway startup hook** under `~/.hermes/hooks/`. Hermes gateway loads hooks at startup, before any messages are processed, so this is the cleanest no-core-modification way to ensure the bridge starts and stops with the gateway process.

Install the hook after installing the plugin:

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install
```

Check hook status:

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook status
```

Then restart Hermes gateway once so the hook is picked up:

```bash
hermes gateway restart
```

### Shareable one-liner install

After this repo is published, the intended one-liner for other users will be:

```bash
hermes plugins install <owner>/hermes-dingtalk-bridge && \
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install && \
hermes gateway restart
```

## Secondary service tooling

A companion launchd service manager is still included as an experimental fallback on macOS:

```bash
python3 -m hermes_dingtalk_bridge service status
python3 -m hermes_dingtalk_bridge service install
python3 -m hermes_dingtalk_bridge service uninstall
```

## Verification

```bash
python3 -m hermes_dingtalk_bridge doctor
```

The doctor verifies both:

- Hermes API server health
- DingTalk access token retrieval

## Notes

- The bridge uses the official `dingtalk-stream` Python SDK.
- The live `run` command will report a clear diagnostic if the SDK is missing.
- In this session the supplied card template was tested against DingTalk APIs and the app currently lacks the required permission `Card.Instance.Write`, so card sends are expected to fall back to markdown until that scope is granted.

## Current DingTalk permission findings

- Native ack reaction APIs are permitted and working for the current app.
- Card sending with template `afe7d987-a565-49e0-96d3-c090e954a7cd.schema` currently fails because the DingTalk app lacks scope `Card.Instance.Write`. The bridge therefore falls back to markdown replies when `reply_mode=card`.
