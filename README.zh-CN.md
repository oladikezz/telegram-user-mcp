<div align="center">

# ✈️ Telegram User MCP

**基于 Telethon 与 FastMCP 构建的生产级 Telegram 个人账号 (Userbot / MTProto) Model Context Protocol (MCP) 服务器**

[🇺🇸 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇨🇳 中文](README.zh-CN.md)

<br/>

[![Release](https://img.shields.io/badge/Release-v1.0.0-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://github.com/oladikezz/telegram-user-mcp)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![MCP SDK](https://img.shields.io/badge/FastMCP-Stdio_Protocol-8B5CF6?style=for-the-badge&logo=anthropic&logoColor=white)](https://modelcontextprotocol.io/)
[![Telethon](https://img.shields.io/badge/Telethon-MTProto_1.38%2B-0088CC?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.telethon.dev/)
[![Claude & Cursor](https://img.shields.io/badge/Clients-Claude_%7C_Cursor_%7C_Goose-10B981?style=for-the-badge)](https://claude.ai/download)
[![License](https://img.shields.io/badge/License-MIT-10B981?style=for-the-badge)](LICENSE)

</div>

---

**Telegram User MCP** 是一个使用 Python（**FastMCP** + **Telethon**）构建的高性能异步 **Model Context Protocol (MCP)** 服务器。与受限于机器人权限的普通 Bot API 不同，本项目直接通过 Telegram 原生 **MTProto 协议**以个人用户身份（Userbot）进行连接。

它使 **Claude Desktop**、**Cursor**、**Goose** 等 AI 助手能够通过本地 `stdio` 安全访问您的私聊、群组、频道、收藏夹消息（Saved Messages）、全局搜索及消息管理。

---

## ✨ 核心特性

- 🔐 **原生 MTProto 个人账号控制：** 支持访问所有私聊、群组、超级群组、频道、归档文件夹以及收藏夹（`me`）。
- 🛡️ **零 Stdio 污染：** 所有服务器日志均严格输出到 `sys.stderr`，确保 `stdout` 上的 `JSON-RPC 2.0` 通信 100% 纯净可靠。
- ⚡ **智能 `StringSession` 实体解析：** 支持数字 ID（`-100...`、`12345678`）、字符串 ID、`@username` 和 `'me'`，并在缓存未命中时自动预热对话列表缓存。
- ⏱️ **自适应 `FloodWaitError` 容错处理：** 短时间限流自动等待并重试（默认最高 `15` 秒），长时间限流返回结构化 JSON 提示，服务器永不崩溃。
- 🔑 **交互式 2FA 授权向导 (`auth.py`)：** 支持短信/Telegram 验证码与两步验证（2FA）密码，自动生成 `TELEGRAM_SESSION_STRING` 并写入 `.env`。

---

## 🧰 MCP 工具列表 (Tools)

| 工具名称 | 参数签名 | 功能说明 |
| :--- | :--- | :--- |
| **`list_dialogs`** | `limit: int = 20, folder: Optional[int] = None` | 获取活跃聊天、群组与频道列表（ID、名称、用户名、类型、未读数、最新消息预览）。 |
| **`get_chat_history`** | `chat_id: int \| str, limit: int = 30, offset_id: int = 0` | 获取指定聊天的历史消息（消息 ID、发送者、时间、文本、媒体类型、回复引用 ID）。 |
| **`search_messages`** | `query: str, chat_id: Optional[int \| str] = None, limit: int = 20` | 全局搜索所有对话（`chat_id=None`）或在指定聊天内搜索消息。 |
| **`send_message`** | `chat_id: int \| str, text: str, reply_to_msg_id: Optional[int] = None` | 发送文本消息或回复指定消息。 |
| **`edit_message`** | `chat_id: int \| str, message_id: int, new_text: str` | 编辑已发送的消息文本。 |
| **`mark_as_read`** | `chat_id: int \| str, max_id: Optional[int] = None` | 将指定聊天中的未读消息、提及和回应标记为已读。 |
| **`get_user_info`** | `user_id: int \| str` | 获取用户完整资料（ID、简介 Bio、用户名、在线状态、电话、共同群组数等）。 |

---

## 🚀 快速开始

```bash
git clone https://github.com/oladikezz/telegram-user-mcp.git
cd telegram-user-mcp

pip install -r requirements.txt
python auth.py
```
