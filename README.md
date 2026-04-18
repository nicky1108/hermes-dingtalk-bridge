# Hermes DingTalk Bridge / Hermes 钉钉桥接插件

A Hermes plugin that bridges DingTalk Stream mode into Hermes without modifying Hermes core.  
一个 **不修改 Hermes 核心代码** 的钉钉桥接插件：通过 DingTalk Stream 模式把钉钉消息接入 Hermes。

---

## What this plugin does / 这个插件做什么

**English**
- installs as a normal Hermes plugin
- starts automatically with `hermes gateway`
- stops automatically with `hermes gateway`
- receives DingTalk messages and forwards them to Hermes `/v1/responses`
- shows a native DingTalk ack reaction (`🤔思考中`) while processing
- supports two reply modes:
  - `markdown`
  - `card` (streaming a single `content` field)
- falls back to markdown if card delivery fails

**中文**
- 作为 **普通 Hermes 插件** 安装
- 跟随 `hermes gateway` **一起启动**
- 跟随 `hermes gateway` **一起停止**
- 接收钉钉消息，并转发给 Hermes 的 `/v1/responses`
- 处理中会先贴一个钉钉原生表情 `🤔思考中`
- 支持两种回复模式：
  - `markdown`
  - `card`（按单字段 `content` 流式输出）
- 如果 card 发送失败，会自动回退到 markdown

---

## Architecture / 架构

```text
DingTalk Stream/OpenAPI <-> hermes-dingtalk-bridge <-> Hermes API Server (/v1/responses)
```

**English**
The plugin is loaded by Hermes, then a gateway startup hook starts the bridge **inside the Hermes gateway process**. This is the primary lifecycle integration path.

**中文**
插件由 Hermes 加载，再通过 **gateway 启动 hook** 在 **Hermes gateway 进程内** 启动 bridge。这是当前的主生命周期集成方式。

---

## Repository layout / 仓库结构

```text
plugin.yaml                       # Hermes plugin manifest
__init__.py                       # Hermes plugin entrypoint
after-install.md                  # Post-install guidance
hermes_dingtalk_bridge/           # Bridge runtime implementation
tests/                            # Unit tests
```

---

## Install / 安装

### Recommended one-liner / 推荐一条命令安装

```bash
hermes plugins install nicky1108/hermes-dingtalk-bridge && \
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install && \
hermes gateway restart
```

**English**
This does three things:
1. installs the plugin into `~/.hermes/plugins/`
2. installs the Hermes gateway startup hook
3. restarts Hermes gateway so the bridge is activated immediately

**中文**
这条命令会完成三件事：
1. 把插件安装到 `~/.hermes/plugins/`
2. 安装 Hermes gateway 启动 hook
3. 重启 Hermes gateway，让 bridge 立即生效

---

## Configuration / 配置

Copy the example file first:  
先复制配置样例：

```bash
cp ~/.hermes/plugins/hermes-dingtalk-bridge/dingtalk-bridge.example.yaml ~/.hermes/dingtalk-bridge.yaml
```

### Required environment variables / 必填环境变量

Preferred explicit vars / 优先使用：
- `HERMES_DINGTALK_CLIENT_ID`
- `HERMES_DINGTALK_CLIENT_SECRET`
- `API_SERVER_KEY`

Fallbacks from existing Hermes env / 也兼容你已有的 Hermes 环境变量：
- `DINGTALK_CLIENT_ID`
- `DINGTALK_CLIENT_SECRET`
- `API_SERVER_KEY`

### Main config keys / 主要配置项

```yaml
dingtalk_bridge:
  hermes_api_base: http://127.0.0.1:8642/v1
  hermes_model: hermes-agent
  account_id: default
  conversation_prefix: dingtalk
  store_path: ~/.hermes/dingtalk-bridge.db
  log_level: INFO

  require_mention_in_groups: true
  group_allowlist: []
  dm_allowlist: []

  reply_mode: card            # markdown | card
  card_template_id: your-template-id.schema

  ack_reaction_enabled: true
  ack_reaction_name: "🤔思考中"
```

---

## Card mode / Card 模式

**English**
Card mode now follows the same high-level pattern as soimy's implementation:
1. `createAndDeliver`
2. `card/streaming`
3. stream the reply into the single `content` field

Current template assumption:
- configure your own `card_template_id` in `~/.hermes/dingtalk-bridge.yaml`
- one streamable variable key: `content`

**中文**
Card 模式现在已经按 soimy 的核心思路实现：
1. `createAndDeliver`
2. `card/streaming`
3. 把回复内容流式写入单一字段 `content`

当前按模板约定：
- 模版 ID 请自行配置在 `~/.hermes/dingtalk-bridge.yaml`
- 只有一个流式字段：`content`

If card delivery fails, the bridge falls back to markdown automatically.  
如果 card 发送失败，bridge 会自动回退到 markdown。

---

## Ack reaction / 接收反馈表情

**English**
When a DingTalk message arrives, the bridge first attaches a native DingTalk reaction (`🤔思考中`) to show that the message was received and is being processed. After the final reply is sent, the reaction is recalled.

**中文**
当钉钉消息到达时，bridge 会先贴一个原生表情 `🤔思考中`，提示“已经收到并开始处理”；回复发送完成后，会再把这个表情撤回。

---

## Lifecycle integration / 生命周期集成

### Primary path: Hermes gateway startup hook / 主路径：Hermes gateway 启动 hook

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install
```

Check hook status / 查看 hook 状态：

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook status
```

**English**
The hook is the main solution. When Hermes gateway starts, the hook starts the bridge **inside the gateway process**. This means the bridge follows gateway start/stop/restart without patching Hermes core.

**中文**
Hook 是主方案。Hermes gateway 启动时，hook 会在 **gateway 进程内** 启动 bridge，因此 bridge 可以跟随 gateway 的启动 / 停止 / 重启，而不需要修改 Hermes 核心代码。

### Secondary path: companion service / 次路径：伴随服务

The repository still contains companion-service tooling as a fallback/diagnostic path, but it is **not** the primary recommended lifecycle integration anymore.  
仓库里仍保留了 companion service 相关工具，作为备用/诊断路径，但它已经 **不是首选的生命周期方案**。

---

## Verification / 验证

### Doctor / 诊断

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge doctor
```

Checks / 会检查：
- Hermes API server health
- DingTalk access token retrieval
- resolved runtime config

### Runtime status / 运行状态

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge status
```

Runtime marker file / 运行状态文件：
- `~/.hermes/dingtalk-bridge.status.json`

This file is useful for checking whether the bridge was started by gateway lifecycle integration.  
这个文件可以用于确认 bridge 是否是被 gateway 生命周期拉起来的。

---

## Real-world behavior verified in this workspace / 当前工作区已验证行为

**Verified / 已验证**
- DingTalk inbound message receive / 能接收钉钉消息
- Hermes `/v1/responses` reply path / Hermes 回复链路正常
- DingTalk native ack reaction attach + recall / 原生表情贴上与撤回正常
- markdown reply / markdown 回复正常
- card reply using `content` field / 基于 `content` 字段的 card 回复正常
- automatic markdown fallback on card failure / card 异常时自动回退 markdown
- gateway stop -> bridge stops / gateway 停止后 bridge 跟随停止
- gateway restart -> bridge autostarts again via hook / gateway 重启后 bridge 通过 hook 再次启动

**Caveat / 注意**
- If you already have old manually started `python -m hermes_dingtalk_bridge run` processes, they can confuse lifecycle verification. Kill them before testing clean gateway-managed behavior.  
  如果你机器里残留了以前手工启动的 `python -m hermes_dingtalk_bridge run` 进程，会干扰生命周期验证。做正式验证前请先清掉这些旧进程。

---


## Configuration reference / 配置项速查

| Key | Meaning (EN) | 含义（中文） |
|---|---|---|
| `reply_mode` | `markdown` or `card` | 回复模式：普通消息或卡片 |
| `card_template_id` | DingTalk card template id used in card mode | card 模式下使用的钉钉卡片模板 ID |
| `ack_reaction_enabled` | enable/disable native thinking reaction | 是否启用原生“思考中”表情反馈 |
| `ack_reaction_name` | reaction text to attach | 要贴的表情/文本 |
| `require_mention_in_groups` | require @mention in group chats | 群聊里是否必须 @ 机器人 |
| `dm_allowlist` | allowed direct-message users | 允许私聊的用户列表 |
| `group_allowlist` | allowed group conversation ids | 允许处理的群会话 ID 列表 |
| `hermes_api_base` | Hermes API base URL | Hermes API 地址 |
| `store_path` | sqlite/session/status storage path | sqlite / 会话状态存储路径 |

## Troubleshooting / 常见问题

### The bridge does not start with `hermes gateway`

**EN**
Check these commands:

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook status
python3 -m hermes_dingtalk_bridge status
cat ~/.hermes/dingtalk-bridge.status.json
```

If the hook is not installed, install it again and restart gateway:

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install
hermes gateway restart
```

**中文**
如果 bridge 没有跟随 `hermes gateway` 自动启动，请检查：

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook status
python3 -m hermes_dingtalk_bridge status
cat ~/.hermes/dingtalk-bridge.status.json
```

如果 hook 没装好，重新安装后再重启 gateway：

```bash
PYTHONPATH="$HOME/.hermes/plugins/hermes-dingtalk-bridge" python3 -m hermes_dingtalk_bridge hook install
hermes gateway restart
```

### Card replies fail / card 回复失败

**EN**
Check:
- `reply_mode=card`
- `card_template_id` is configured locally
- the template has a streamable `content` variable
- the DingTalk app has the required card permissions

The bridge will automatically fall back to markdown if card send fails.

**中文**
请检查：
- `reply_mode=card`
- 本地已经配置 `card_template_id`
- 模版里存在可流式写入的 `content` 字段
- 钉钉应用已经开通 card 相关权限

如果 card 发送失败，bridge 会自动回退到 markdown。

### Too many old bridge processes / 看到很多旧 bridge 进程

**EN**
That usually comes from previous manual test runs like `python -m hermes_dingtalk_bridge run`. The supported production path is the **gateway startup hook**, not long-lived standalone manual processes.

**中文**
如果你看到很多旧的 bridge 进程，通常是以前手工跑过 `python -m hermes_dingtalk_bridge run` 留下的。正式使用时推荐走 **gateway startup hook**，而不是长期手工起独立进程。

## Development / 开发

Run tests / 跑测试：

```bash
cd hermes-dingtalk-bridge
python3 -m unittest discover -s tests -v
```

---

## License / 许可

Add your preferred license before public release.  
在正式公开发布前，请补充你希望使用的开源许可证。
