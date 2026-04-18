# Hermes DingTalk Bridge installed / Hermes 钉钉桥接插件已安装

## Activate now / 立即激活

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install
hermes gateway restart
```

## Quick checks / 快速检查

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge doctor
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook status
```

## Notes / 说明

- The recommended lifecycle path is the **gateway startup hook**, not the companion service.  
  推荐的生命周期集成方式是 **gateway startup hook**，不是 companion service。
- If `reply_mode=card`, configure your own `card_template_id` locally and the card content will stream through the `content` field.  
  如果 `reply_mode=card`，请在本地配置自己的 `card_template_id`，卡片内容会通过 `content` 字段流式输出。
- If card delivery fails, the bridge automatically falls back to markdown replies.  
  如果 card 发送失败，bridge 会自动回退到 markdown。
