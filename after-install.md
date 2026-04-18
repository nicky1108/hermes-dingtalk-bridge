# Hermes DingTalk Bridge installed

To fully activate the plugin so it starts and stops with `hermes gateway`, run:

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install
hermes gateway restart
```

Quick checks:

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge doctor
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook status
```

If `reply_mode=card`, remember your DingTalk app must have `Card.Instance.Write` permission, otherwise the bridge will fall back to markdown replies.
