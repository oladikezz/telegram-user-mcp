#!/usr/bin/env python3
"""
Production-ready MCP-сервер (Model Context Protocol) для управления личным аккаунтом
Telegram (Userbot / MTProto) с использованием FastMCP и Telethon.

Запуск через stdio (для Claude Desktop, Cursor, Goose):
    python server.py
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional, TypeVar, Union

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from telethon import TelegramClient, functions, types, utils
from telethon.errors import (
    AuthKeyError,
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    MessageAuthorRequiredError,
    MessageIdInvalidError,
    MessageNotModifiedError,
    PeerIdInvalidError,
    RPCError,
    SessionPasswordNeededError,
    UnauthorizedError,
    UserDeactivatedBanError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import SQLiteSession, StringSession

# ---------------------------------------------------------------------------
# Настройка логирования (СТРОГО в stderr, чтобы не ломать JSON-RPC в stdout)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("telegram-user-mcp")
logging.getLogger("telethon").setLevel(logging.WARNING)

# Загрузка переменных окружения из .env рядом со скриптом
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

MAX_FLOOD_WAIT_SLEEP = int(os.getenv("TELEGRAM_MAX_FLOOD_WAIT_SLEEP", "15"))

T = TypeVar("T")


class TelegramConfigurationError(RuntimeError):
    """Исключение при отсутствии или некорректности настроек/авторизации Telegram."""


class TelegramClientManager:
    """Потокобезопасный (asyncio) менеджер подключения Telethon клиента."""

    def __init__(self) -> None:
        self._client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()
        self._dialogs_cached: bool = False

    def _create_client(self) -> TelegramClient:
        raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        session_string = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
        session_name = os.getenv("TELEGRAM_SESSION_NAME", "telegram_user").strip()

        if not raw_api_id or not raw_api_id.isdigit() or not api_hash:
            raise TelegramConfigurationError(
                "Не заданы TELEGRAM_API_ID или TELEGRAM_API_HASH. "
                "Укажите их в .env или переменных окружения MCP-сервера."
            )

        api_id = int(raw_api_id)

        if session_string:
            session = StringSession(session_string)
            logger.info("Используется авторизация через TELEGRAM_SESSION_STRING.")
        else:
            session_path = BASE_DIR / f"{session_name}.session"
            session = SQLiteSession(str(session_path))
            logger.info("Используется локальный файл сессии: %s", session_path)

        return TelegramClient(
            session,
            api_id,
            api_hash,
            device_model="Telegram-User-MCP",
            system_version="1.0",
            app_version="1.0.0",
            receive_updates=False,  # Оптимизация для request-response режима MCP
        )

    async def get_client(self) -> TelegramClient:
        """Возвращает активный и авторизованный экземпляр TelegramClient."""
        async with self._lock:
            if self._client is None:
                self._client = self._create_client()

            if not self._client.is_connected():
                await self._client.connect()

            if not await self._client.is_user_authorized():
                raise TelegramConfigurationError(
                    "Сессия Telegram не авторизована или устарела. "
                    "Запустите `python auth.py` для генерации новой TELEGRAM_SESSION_STRING."
                )

            return self._client

    async def resolve_entity(self, identifier: Union[int, str]) -> Any:
        """
        Универсальное разрешение идентификатора чата или пользователя:
        поддерживает int ID (-100..., 12345), строковые числа, @username, 'me'/'self'.
        При использовании StringSession автоматически прогревает кэш диалогов при необходимости.
        """
        client = await self.get_client()

        target: Union[int, str]
        if isinstance(identifier, int):
            target = identifier
        elif isinstance(identifier, str):
            cleaned = identifier.strip()
            if not cleaned:
                raise ValueError("Идентификатор чата/пользователя не может быть пустым.")
            if cleaned.lower() in ("me", "self", "saved"):
                target = "me"
            elif cleaned.lstrip("-").isdigit():
                target = int(cleaned)
            else:
                target = cleaned
        else:
            raise ValueError(f"Неподдерживаемый тип идентификатора: {type(identifier).__name__}")

        try:
            return await client.get_entity(target)
        except ValueError:
            # Для StringSession кэш access_hash может быть пуст при первом запросе по int ID
            if not self._dialogs_cached:
                logger.info("Прогрев кэша диалогов Telethon для разрешения ID: %s", target)
                await client.get_dialogs(limit=200)
                self._dialogs_cached = True
                return await client.get_entity(target)
            raise

    async def close(self) -> None:
        """Корректное закрытие соединения с Telegram API."""
        async with self._lock:
            if self._client is not None and self._client.is_connected():
                await self._client.disconnect()
                logger.info("Соединение с Telegram успешно закрыто.")


client_manager = TelegramClientManager()


@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Жизненный цикл MCP-сервера: подключение к Telegram при старте и отключение при выходе."""
    try:
        await client_manager.get_client()
        logger.info("Telegram MCP сервер успешно инициализирован и подключен к MTProto.")
    except Exception as exc:
        # Не роняем процесс при старте, чтобы MCP-клиент получил понятную ошибку при вызове тулов
        logger.warning("Предупреждение при старте Telegram клиента: %s", exc)
    try:
        yield
    finally:
        await client_manager.close()


mcp = FastMCP(
    "telegram-user-mcp",
    lifespan=server_lifespan,
)


# ---------------------------------------------------------------------------
# Вспомогательные функции сериализации и обработки ошибок
# ---------------------------------------------------------------------------
def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _detect_chat_type(entity: Any) -> str:
    if isinstance(entity, types.User):
        if getattr(entity, "is_self", False):
            return "saved_messages"
        if getattr(entity, "bot", False):
            return "bot"
        return "private"
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel):
        if getattr(entity, "megagroup", False):
            return "supergroup"
        return "channel"
    return "unknown"


def _detect_media_info(msg: types.Message) -> tuple[bool, Optional[str]]:
    if not msg or not getattr(msg, "media", None):
        return False, None

    media = msg.media
    if isinstance(media, types.MessageMediaPhoto):
        return True, "photo"
    if isinstance(media, types.MessageMediaDocument):
        if getattr(msg, "voice", False):
            return True, "voice"
        if getattr(msg, "video_note", False):
            return True, "video_note"
        if getattr(msg, "video", False):
            return True, "video"
        if getattr(msg, "audio", False):
            return True, "audio"
        if getattr(msg, "sticker", False):
            return True, "sticker"
        if getattr(msg, "gif", False):
            return True, "gif"
        return True, "document"
    if isinstance(media, types.MessageMediaPoll):
        return True, "poll"
    if isinstance(media, types.MessageMediaGeo) or isinstance(media, types.MessageMediaGeoLive):
        return True, "location"
    if isinstance(media, types.MessageMediaContact):
        return True, "contact"
    if isinstance(media, types.MessageMediaWebPage):
        return True, "webpage"
    return True, type(media).__name__


def _format_sender_name(sender: Any) -> tuple[str, Optional[str]]:
    if sender is None:
        return "Unknown", None
    username = getattr(sender, "username", None)
    if isinstance(sender, types.User):
        parts = [p for p in (sender.first_name, sender.last_name) if p]
        name = " ".join(parts) if parts else (username or f"User {sender.id}")
        return name, username
    title = getattr(sender, "title", None)
    return title or username or f"Peer {getattr(sender, 'id', '')}", username


def _format_user_status(status: Any, is_bot: bool = False) -> str:
    if is_bot:
        return "bot"
    if status is None:
        return "hidden_or_unknown"
    if isinstance(status, types.UserStatusOnline):
        return "online"
    if isinstance(status, types.UserStatusOffline):
        was_online = _format_datetime(status.was_online)
        return f"offline (last_seen: {was_online})" if was_online else "offline"
    if isinstance(status, types.UserStatusRecently):
        return "recently"
    if isinstance(status, types.UserStatusLastWeek):
        return "within_week"
    if isinstance(status, types.UserStatusLastMonth):
        return "within_month"
    if isinstance(status, types.UserStatusEmpty):
        return "long_time_ago"
    return type(status).__name__


def _serialize_message(msg: types.Message) -> dict[str, Any]:
    has_media, media_type = _detect_media_info(msg)
    sender_name, sender_username = _format_sender_name(getattr(msg, "sender", None))

    reply_to_msg_id: Optional[int] = None
    if getattr(msg, "reply_to", None) and hasattr(msg.reply_to, "reply_to_msg_id"):
        reply_to_msg_id = msg.reply_to.reply_to_msg_id

    return {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "sender_name": sender_name,
        "sender_username": sender_username,
        "is_outgoing": bool(msg.out),
        "date": _format_datetime(msg.date),
        "text": msg.message or "",
        "has_media": has_media,
        "media_type": media_type,
        "reply_to": reply_to_msg_id,
        "reply_to_msg_id": reply_to_msg_id,
        "edit_date": _format_datetime(getattr(msg, "edit_date", None)),
        "views": getattr(msg, "views", None),
        "forwards": getattr(msg, "forwards", None),
    }


async def _execute_safely(
    operation: Callable[[], Coroutine[Any, Any, dict[str, Any]]],
) -> dict[str, Any]:
    """
    Обертка для безопасного выполнения запросов к Telegram API:
    - Автоматически пережидает короткий FloodWaitError (до MAX_FLOOD_WAIT_SLEEP сек.)
    - Перехватывает ошибки авторизации, доступа и валидации без падения MCP-сервера.
    """
    for attempt in range(2):
        try:
            return await operation()
        except FloodWaitError as e:
            if attempt == 0 and e.seconds <= MAX_FLOOD_WAIT_SLEEP:
                logger.warning(
                    "FloodWaitError (%s сек <= %s сек). Ожидание и повтор запроса...",
                    e.seconds,
                    MAX_FLOOD_WAIT_SLEEP,
                )
                await asyncio.sleep(e.seconds + 1)
                continue
            return {
                "ok": False,
                "error_type": "FloodWaitError",
                "retry_after_seconds": e.seconds,
                "message": (
                    f"Превышен лимит запросов Telegram API (FloodWait). "
                    f"Повторите попытку через {e.seconds} секунд."
                ),
            }
        except (
            TelegramConfigurationError,
            AuthKeyUnregisteredError,
            AuthKeyError,
            UserDeactivatedBanError,
            SessionPasswordNeededError,
            UnauthorizedError,
        ) as e:
            return {
                "ok": False,
                "error_type": type(e).__name__,
                "message": (
                    f"Ошибка авторизации Telegram: {e}. "
                    "Проверьте .env или сгенерируйте новую сессию через `python auth.py`."
                ),
            }
        except (UsernameNotOccupiedError, UsernameInvalidError, PeerIdInvalidError) as e:
            return {
                "ok": False,
                "error_type": type(e).__name__,
                "message": f"Чат или пользователь не найден / некорректный идентификатор: {e}",
            }
        except (ChatWriteForbiddenError, ChatAdminRequiredError, ChannelPrivateError) as e:
            return {
                "ok": False,
                "error_type": type(e).__name__,
                "message": f"Недостаточно прав или доступ к чату/каналу ограничен: {e}",
            }
        except MessageNotModifiedError:
            return {
                "ok": True,
                "warning": "MessageNotModifiedError",
                "message": "Текст сообщения не изменился (совпадает с текущим).",
            }
        except (MessageAuthorRequiredError, MessageIdInvalidError) as e:
            return {
                "ok": False,
                "error_type": type(e).__name__,
                "message": f"Невозможно изменить сообщение (неверный ID или вы не автор): {e}",
            }
        except ValueError as e:
            return {
                "ok": False,
                "error_type": "ValidationError",
                "message": str(e),
            }
        except RPCError as e:
            return {
                "ok": False,
                "error_type": type(e).__name__,
                "rpc_code": getattr(e, "code", None),
                "message": f"Ошибка Telegram RPC: {e}",
            }
        except Exception as e:
            logger.exception("Непредвиденная ошибка при выполнении MCP-инструмента")
            return {
                "ok": False,
                "error_type": type(e).__name__,
                "message": f"Внутренняя ошибка сервера: {e}",
            }

    return {"ok": False, "error_type": "UnknownError", "message": "Не удалось выполнить запрос."}


# ---------------------------------------------------------------------------
# MCP TOOLS (Инструменты)
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_dialogs(
    limit: int = 20,
    folder: Optional[int] = None,
) -> dict[str, Any]:
    """
    Возвращает список активных чатов, личных диалогов, групп и каналов аккаунта Telegram.

    Args:
        limit: Максимальное количество возвращаемых диалогов (от 1 до 200, по умолчанию 20).
        folder: Фильтр по папке диалогов:
            - None: все диалоги (по умолчанию)
            - 0: только основной список чатов (не в архиве)
            - 1: только архивные чаты (Archived Chats)

    Returns:
        Словарь со списком диалогов (id, название, username, тип чата, количество непрочитанных и превью).
    """
    async def _op() -> dict[str, Any]:
        if not (1 <= limit <= 200):
            raise ValueError("Параметр `limit` должен быть в диапазоне от 1 до 200.")
        if folder not in (None, 0, 1):
            raise ValueError("Параметр `folder` может принимать только значения None, 0 (основные) или 1 (архив).")

        client = await client_manager.get_client()
        dialogs = await client.get_dialogs(limit=limit, folder=folder)

        items: list[dict[str, Any]] = []
        for d in dialogs:
            entity = d.entity
            peer_id = utils.get_peer_id(entity)
            username = getattr(entity, "username", None)
            chat_type = _detect_chat_type(entity)

            last_msg_text = ""
            if d.message:
                last_msg_text = d.message.message or (
                    f"[{_detect_media_info(d.message)[1] or 'media'}]" if d.message.media else ""
                )

            items.append(
                {
                    "id": peer_id,
                    "name": d.name or getattr(entity, "title", None) or f"Chat {peer_id}",
                    "username": f"@{username}" if username else None,
                    "type": chat_type,
                    "unread_count": d.unread_count,
                    "unread_mentions_count": d.unread_mentions_count,
                    "pinned": bool(d.pinned),
                    "archived": bool(d.archived),
                    "last_message_date": _format_datetime(d.date),
                    "last_message_preview": last_msg_text[:200] if last_msg_text else None,
                }
            )

        return {
            "ok": True,
            "count": len(items),
            "folder": folder,
            "dialogs": items,
        }

    return await _execute_safely(_op)


@mcp.tool()
async def get_chat_history(
    chat_id: Union[int, str],
    limit: int = 30,
    offset_id: int = 0,
) -> dict[str, Any]:
    """
    Получает последние сообщения из конкретного чата, группы или канала.

    Args:
        chat_id: Числовой ID чата (например, -1001234567890 или 12345678), @username или 'me'.
        limit: Количество сообщений для загрузки (от 1 до 100, по умолчанию 30).
        offset_id: ID сообщения, начиная с которого (более старые) нужно загружать историю (0 — самые новые).

    Returns:
        Словарь с метаданными чата и списком сообщений (id, отправитель, дата, текст, флаг медиа, reply_to).
    """
    async def _op() -> dict[str, Any]:
        if not (1 <= limit <= 100):
            raise ValueError("Параметр `limit` должен быть в диапазоне от 1 до 100.")
        if offset_id < 0:
            raise ValueError("Параметр `offset_id` не может быть отрицательным.")

        client = await client_manager.get_client()
        entity = await client_manager.resolve_entity(chat_id)
        peer_id = utils.get_peer_id(entity)
        chat_name, chat_username = _format_sender_name(entity)

        messages = await client.get_messages(entity, limit=limit, offset_id=offset_id)
        serialized = [_serialize_message(m) for m in messages if isinstance(m, types.Message)]

        return {
            "ok": True,
            "chat": {
                "id": peer_id,
                "name": chat_name,
                "username": f"@{chat_username}" if chat_username else None,
                "type": _detect_chat_type(entity),
            },
            "count": len(serialized),
            "offset_id": offset_id,
            "messages": serialized,
        }

    return await _execute_safely(_op)


@mcp.tool()
async def search_messages(
    query: str,
    chat_id: Optional[Union[int, str]] = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Выполняет глобальный поиск по всем чатам или поиск внутри конкретного чата по текстовому запросу.

    Args:
        query: Поисковый запрос (непустая строка).
        chat_id: Опциональный ID чата или @username. Если None — выполняется глобальный поиск по всем чатам.
        limit: Максимальное число найденных сообщений (от 1 до 100, по умолчанию 20).

    Returns:
        Словарь со списком найденных сообщений и информацией о чатах, где они были найдены.
    """
    async def _op() -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("Поисковый запрос `query` не может быть пустым.")
        if not (1 <= limit <= 100):
            raise ValueError("Параметр `limit` должен быть в диапазоне от 1 до 100.")

        client = await client_manager.get_client()
        entity = await client_manager.resolve_entity(chat_id) if chat_id is not None else None

        results: list[dict[str, Any]] = []
        async for msg in client.iter_messages(entity, search=cleaned_query, limit=limit):
            if not isinstance(msg, types.Message):
                continue

            item = _serialize_message(msg)
            chat_obj = getattr(msg, "chat", None)
            if chat_obj is not None:
                c_name, c_username = _format_sender_name(chat_obj)
                item["chat_id"] = utils.get_peer_id(chat_obj)
                item["chat_name"] = c_name
                item["chat_username"] = f"@{c_username}" if c_username else None
            elif msg.peer_id is not None:
                item["chat_id"] = utils.get_peer_id(msg.peer_id)

            results.append(item)

        return {
            "ok": True,
            "query": cleaned_query,
            "scope": str(chat_id) if chat_id is not None else "global",
            "count": len(results),
            "messages": results,
        }

    return await _execute_safely(_op)


@mcp.tool()
async def send_message(
    chat_id: Union[int, str],
    text: str,
    reply_to_msg_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Отправляет текстовое сообщение в указанный чат, группу, канал или пользователю.

    Args:
        chat_id: Числовой ID чата (например, -1001234567890 или 12345678), @username или 'me'.
        text: Текст отправляемого сообщения (поддерживается стандартная разметка).
        reply_to_msg_id: Опциональный ID сообщения, на которое нужно ответить (reply).

    Returns:
        Словарь с данными об отправленном сообщении (message_id, chat_id, дата, текст).
    """
    async def _op() -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("Текст сообщения `text` не может быть пустым.")
        if reply_to_msg_id is not None and reply_to_msg_id <= 0:
            raise ValueError("Параметр `reply_to_msg_id` должен быть положительным целым числом.")

        client = await client_manager.get_client()
        entity = await client_manager.resolve_entity(chat_id)

        sent_msg = await client.send_message(
            entity=entity,
            message=text,
            reply_to=reply_to_msg_id,
        )

        return {
            "ok": True,
            "chat_id": utils.get_peer_id(entity),
            "message": _serialize_message(sent_msg),
        }

    return await _execute_safely(_op)


@mcp.tool()
async def edit_message(
    chat_id: Union[int, str],
    message_id: int,
    new_text: str,
) -> dict[str, Any]:
    """
    Редактирует ранее отправленное сообщение в указанном чате.

    Args:
        chat_id: Числовой ID чата, @username или 'me'.
        message_id: Числовой ID редактируемого сообщения (должен быть > 0).
        new_text: Новый текст сообщения.

    Returns:
        Словарь с подтверждением редактирования и обновленными данными сообщения.
    """
    async def _op() -> dict[str, Any]:
        if message_id <= 0:
            raise ValueError("Параметр `message_id` должен быть положительным числом.")
        if not new_text or not new_text.strip():
            raise ValueError("Параметр `new_text` не может быть пустым.")

        client = await client_manager.get_client()
        entity = await client_manager.resolve_entity(chat_id)

        edited_msg = await client.edit_message(
            entity=entity,
            message=message_id,
            text=new_text,
        )

        return {
            "ok": True,
            "chat_id": utils.get_peer_id(entity),
            "message": _serialize_message(edited_msg),
        }

    return await _execute_safely(_op)


@mcp.tool()
async def mark_as_read(
    chat_id: Union[int, str],
    max_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Отмечает сообщения в указанном чате как прочитанные.

    Args:
        chat_id: Числовой ID чата, @username или 'me'.
        max_id: Опциональный ID сообщения, до которого включительно пометить сообщения прочитанными.
            Если None — прочитываются все непрочитанные сообщения в чате.

    Returns:
        Словарь с подтверждением статуса прочтения.
    """
    async def _op() -> dict[str, Any]:
        if max_id is not None and max_id <= 0:
            raise ValueError("Параметр `max_id` должен быть положительным числом.")

        client = await client_manager.get_client()
        entity = await client_manager.resolve_entity(chat_id)

        await client.send_read_acknowledge(
            entity=entity,
            max_id=max_id,
            clear_mentions=True,
            clear_reactions=True,
        )

        return {
            "ok": True,
            "chat_id": utils.get_peer_id(entity),
            "max_id": max_id,
            "status": "marked_as_read",
        }

    return await _execute_safely(_op)


@mcp.tool()
async def get_user_info(
    user_id: Union[int, str],
) -> dict[str, Any]:
    """
    Получает подробную информацию о профиле пользователя Telegram (ID, имя, username, bio, статус онлайн, флаги).

    Args:
        user_id: Числовой ID пользователя (например, 123456789), @username или 'me'.

    Returns:
        Словарь с полным профилем пользователя (id, bio, username, статус, телефон, общие чаты и др.).
    """
    async def _op() -> dict[str, Any]:
        client = await client_manager.get_client()
        entity = await client_manager.resolve_entity(user_id)

        if not isinstance(entity, types.User):
            raise ValueError(
                f"Указанный идентификатор `{user_id}` принадлежит чату/каналу ({type(entity).__name__}), "
                "а не пользователю."
            )

        full_result = await client(functions.users.GetFullUserRequest(id=entity))
        full_user = full_result.full_user
        user_obj: types.User = (
            full_result.users[0] if getattr(full_result, "users", None) else entity
        )

        # Сбор всех дополнительных (collectible/Fragment) юзернеймов, если имеются
        extra_usernames: list[str] = []
        if getattr(user_obj, "usernames", None):
            extra_usernames = [
                f"@{u.username}" for u in user_obj.usernames if getattr(u, "active", False)
            ]

        parts = [p for p in (user_obj.first_name, user_obj.last_name) if p]
        full_name = " ".join(parts) if parts else ""

        return {
            "ok": True,
            "user": {
                "id": user_obj.id,
                "first_name": user_obj.first_name,
                "last_name": user_obj.last_name,
                "full_name": full_name,
                "username": f"@{user_obj.username}" if user_obj.username else None,
                "active_usernames": extra_usernames,
                "phone": f"+{user_obj.phone}" if getattr(user_obj, "phone", None) else None,
                "bio": getattr(full_user, "about", None),
                "status": _format_user_status(
                    getattr(user_obj, "status", None),
                    is_bot=bool(getattr(user_obj, "bot", False)),
                ),
                "is_self": bool(getattr(user_obj, "is_self", False)),
                "is_bot": bool(getattr(user_obj, "bot", False)),
                "is_verified": bool(getattr(user_obj, "verified", False)),
                "is_premium": bool(getattr(user_obj, "premium", False)),
                "is_scam": bool(getattr(user_obj, "scam", False)),
                "is_fake": bool(getattr(user_obj, "fake", False)),
                "is_contact": bool(getattr(user_obj, "contact", False)),
                "is_mutual_contact": bool(getattr(user_obj, "mutual_contact", False)),
                "common_chats_count": getattr(full_user, "common_chats_count", 0),
                "bot_info_description": getattr(
                    getattr(full_user, "bot_info", None), "description", None
                ),
            },
        }

    return await _execute_safely(_op)


if __name__ == "__main__":
    mcp.run(transport="stdio")
