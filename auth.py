#!/usr/bin/env python3
"""
Одноразовый CLI-скрипт для авторизации личного аккаунта Telegram (MTProto)
и генерации TELEGRAM_SESSION_STRING для MCP-сервера.

Использование:
    python auth.py
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

ENV_PATH = Path(__file__).resolve().parent / ".env"


def get_credentials() -> tuple[int, str]:
    """Загружает TELEGRAM_API_ID и TELEGRAM_API_HASH из .env или запрашивает у пользователя."""
    load_dotenv(dotenv_path=ENV_PATH)

    raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

    print("=" * 65)
    print("  Telegram Userbot MCP — Мастер авторизации (Telethon MTProto)")
    print("=" * 65)
    print("Получить API_ID и API_HASH можно на: https://my.telegram.org/apps\n")

    while not raw_api_id or not raw_api_id.isdigit():
        raw_api_id = input("Введите TELEGRAM_API_ID (число): ").strip()
        if not raw_api_id.isdigit():
            print("[!] Ошибка: TELEGRAM_API_ID должен состоять только из цифр.")

    while not api_hash or api_hash == "your_api_hash_here":
        api_hash = input("Введите TELEGRAM_API_HASH (строка): ").strip()
        if not api_hash:
            print("[!] Ошибка: TELEGRAM_API_HASH не может быть пустым.")

    return int(raw_api_id), api_hash


def save_to_env(api_id: int, api_hash: str, session_string: str) -> None:
    """Сохраняет учетные данные и сгенерированную строку сессии в файл .env."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            f"TELEGRAM_API_ID={api_id}\n"
            f"TELEGRAM_API_HASH={api_hash}\n"
            f"TELEGRAM_SESSION_STRING={session_string}\n",
            encoding="utf-8",
        )
    else:
        set_key(str(ENV_PATH), "TELEGRAM_API_ID", str(api_id))
        set_key(str(ENV_PATH), "TELEGRAM_API_HASH", api_hash)
        set_key(str(ENV_PATH), "TELEGRAM_SESSION_STRING", session_string)


async def authenticate() -> None:
    """Интерактивный процесс входа в Telegram и генерации StringSession."""
    api_id, api_hash = get_credentials()

    client = TelegramClient(
        StringSession(),
        api_id,
        api_hash,
        device_model="Telegram-User-MCP",
        system_version="1.0",
        app_version="1.0.0",
    )

    await client.connect()

    try:
        if not await client.is_user_authorized():
            phone = input("\nВведите номер телефона в международном формате (например, +79991234567): ").strip()
            if not phone:
                print("[!] Номер телефона не указан. Завершение работы.")
                return

            try:
                await client.send_code_request(phone)
            except PhoneNumberInvalidError:
                print("[!] Ошибка: Неверный формат номера телефона.")
                return
            except FloodWaitError as e:
                print(f"[!] FloodWaitError: Слишком много попыток. Подождите {e.seconds} сек.")
                return

            print("\nКод подтверждения отправлен в приложение Telegram (или по SMS).")
            code = input("Введите полученный код: ").strip().replace("-", "").replace(" ", "")

            try:
                await client.sign_in(phone=phone, code=code)
            except PhoneCodeInvalidError:
                print("[!] Ошибка: Введен неверный код подтверждения.")
                return
            except PhoneCodeExpiredError:
                print("[!] Ошибка: Срок действия кода истек. Запустите скрипт заново.")
                return
            except SessionPasswordNeededError:
                print("\n[2FA] На аккаунте включена двухфакторная аутентификация (облачный пароль).")
                try:
                    password = getpass.getpass("Введите облачный пароль 2FA (ввод скрыт): ")
                except Exception:
                    password = input("Введите облачный пароль 2FA: ")

                try:
                    await client.sign_in(password=password)
                except PasswordHashInvalidError:
                    print("[!] Ошибка: Неверный пароль двухфакторной аутентификации (2FA).")
                    return

        me = await client.get_me()
        session_string = client.session.save()

        username_str = f" (@{me.username})" if getattr(me, "username", None) else ""
        print("\n" + "=" * 65)
        print(f"Успешная авторизация: {me.first_name or ''} {me.last_name or ''}{username_str} [ID: {me.id}]")
        print("=" * 65)
        print("\nВаш TELEGRAM_SESSION_STRING (никому не передавайте его!):\n")
        print(session_string)
        print("\n" + "=" * 65)

        save_choice = input(f"\nСохранить/обновить данные в файле {ENV_PATH}? [Y/n]: ").strip().lower()
        if save_choice in ("", "y", "yes", "д", "да"):
            save_to_env(api_id, api_hash, session_string)
            print(f"[+] Конфигурация успешно сохранена в {ENV_PATH}")
        else:
            print("[i] Скопируйте TELEGRAM_SESSION_STRING вручную в ваш .env или конфиг MCP.")

    except FloodWaitError as e:
        print(f"\n[!] Ограничение Telegram API (FloodWaitError): подождите {e.seconds} сек.")
    except KeyboardInterrupt:
        print("\n[!] Авторизация прервана пользователем.")
    except Exception as e:
        print(f"\n[!] Непредвиденная ошибка при авторизации: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(authenticate())
    except KeyboardInterrupt:
        sys.exit(0)
