<div align="center">

# ✈️ Telegram User MCP

**Production-ready MCP-сервер (Model Context Protocol) для полного управления личным аккаунтом Telegram (Userbot / MTProto) через Telethon и FastMCP**

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

**Telegram User MCP** — это высокопроизводительный асинхронный сервер **Model Context Protocol (MCP)** на Python с использованием **FastMCP** и **Telethon**. В отличие от обычных ботов (Bot API), этот сервер подключается напрямую к нативному протоколу **Telegram MTProto** от имени вашего личного аккаунта (Userbot).

Это позволяет ИИ-ассистентам (**Claude Desktop**, **Cursor**, **Goose**, **Windsurf**) читать личные диалоги, закрытые группы и каналы, искать сообщения по всему аккаунту, отправлять и редактировать сообщения, а также получать подробные профили пользователей локально через `stdio`.

---

## ✨ Основные возможности

- 🔐 **Прямое подключение по MTProto (Userbot):** Полный доступ к личным чатам, папкам, архиву, приватным группам, каналам и «Избранному» (`me`).
- 🛡️ **Чистый `stdio` транспорт:** Все системные логи сервера и `Telethon` изолированы в `sys.stderr`, что гарантирует 100% валидный поток `JSON-RPC 2.0` в `stdout`.
- ⚡ **Умное разрешение сущностей (`StringSession`):** Поддержка числовых ID (`-100...`, `12345678`), строковых ID, `@username` и `'me'` с автоматическим прогревом кэша диалогов при старте.
- ⏱️ **Защита от `FloodWaitError`:** Автоматическое ожидание (`asyncio.sleep`) при коротких лимитах Telegram API (до `15` сек.) и возврат структурированного ответа без падения сервера при длительных ограничениях.
- 🔑 **Интерактивный CLI-мастер авторизации (`auth.py`):** Поддержка входа по коду из Telegram/SMS и облачному паролю двухфакторной аутентификации (**2FA**) с автоматическим сохранением `TELEGRAM_SESSION_STRING` в `.env`.

---

## 🧰 Доступные MCP Инструменты (Tools)

| Инструмент | Параметры | Описание |
| :--- | :--- | :--- |
| **`list_dialogs`** | `limit: int = 20, folder: Optional[int] = None` | Возвращает список активных чатов, групп и каналов (`id`, название, `@username`, тип чата, кол-во непрочитанных, превью). |
| **`get_chat_history`** | `chat_id: int \| str, limit: int = 30, offset_id: int = 0` | Получает последние сообщения из чата (`id`, отправитель, дата, текст, наличие и тип медиа, `reply_to`). |
| **`search_messages`** | `query: str, chat_id: Optional[int \| str] = None, limit: int = 20` | Глобальный поиск по всем чатам (`chat_id=None`) или поиск внутри конкретного диалога. |
| **`send_message`** | `chat_id: int \| str, text: str, reply_to_msg_id: Optional[int] = None` | Отправка текстового сообщения или ответа (`reply`) на конкретное сообщение. |
| **`edit_message`** | `chat_id: int \| str, message_id: int, new_text: str` | Редактирование ранее отправленного собственного сообщения. |
| **`mark_as_read`** | `chat_id: int \| str, max_id: Optional[int] = None` | Отмечает сообщения, упоминания и реакции в чате как прочитанные. |
| **`get_user_info`** | `user_id: int \| str` | Возвращает полный профиль пользователя (`id`, `bio`, `username`, `status`, телефон, Premium, общие чаты). |

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
git clone https://github.com/oladikezz/telegram-user-mcp.git
cd telegram-user-mcp

# Через uv (рекомендуется)
uv venv
uv pip install -r requirements.txt

# Или через стандартный pip
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Генерация сессии (`auth.py`)

1. Получите `API_ID` и `API_HASH` на [https://my.telegram.org/apps](https://my.telegram.org/apps).
2. Запустите мастер авторизации:
   ```bash
   python auth.py
   ```
3. Введите номер телефона, код подтверждения и (при наличии) пароль 2FA. Скрипт сгенерирует `TELEGRAM_SESSION_STRING` и автоматически сохранит его в `.env`.

---

## ⚙️ Подключение в Claude Desktop / Cursor / Goose

Добавьте блок в `claude_desktop_config.json` (или `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "telegram-user": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:/Users/user/Desktop/telegram-user-mcp",
        "--with",
        "mcp[cli]",
        "--with",
        "telethon",
        "--with",
        "python-dotenv",
        "python",
        "server.py"
      ],
      "env": {
        "TELEGRAM_API_ID": "12345678",
        "TELEGRAM_API_HASH": "your_api_hash_here",
        "TELEGRAM_SESSION_STRING": "your_session_string_from_auth_py"
      }
    }
  }
}
```
