import os
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, ChannelPrivateError
from config import API_ID, API_HASH, RUN_MODE

SESSION_FILE = "user_session.session"
if RUN_MODE == 'render':
    SESSION_FILE = "/tmp/user_session.session"

# Віддаємо перевагу StringSession з оточення; різні ключі для LOCAL/RENDER
env_used = None
if str(RUN_MODE).lower() == 'render':
    string_session = (
        os.getenv("TELETHON_SESSION")
        or os.getenv("TELETHON_SESSION_RENDER")
        or os.getenv("TELETHON_SESSION_STRING")
    )
    env_used = (
        "TELETHON_SESSION" if os.getenv("TELETHON_SESSION") else
        "TELETHON_SESSION_RENDER" if os.getenv("TELETHON_SESSION_RENDER") else
        "TELETHON_SESSION_STRING" if os.getenv("TELETHON_SESSION_STRING") else None
    )
else:
    string_session = (
        os.getenv("TELETHON_SESSION_LOCAL")
        or os.getenv("TELETHON_SESSION")
        or os.getenv("TELETHON_SESSION_STRING")
    )
    env_used = (
        "TELETHON_SESSION_LOCAL" if os.getenv("TELETHON_SESSION_LOCAL") else
        "TELETHON_SESSION" if os.getenv("TELETHON_SESSION") else
        "TELETHON_SESSION_STRING" if os.getenv("TELETHON_SESSION_STRING") else None
    )

if string_session:
    client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
    logging.info(f"📡 Telethon клієнт створено з StringSession (env: {env_used})")
else:
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    logging.info(f"📡 Telethon клієнт створено з файловою сесією: {SESSION_FILE}")

# --- 2. Допоміжна функція ---
async def ensure_connected():
    """Підключає клієнт тільки якщо потрібно"""
    if not client.is_connected():
        await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("⚠️ Telethon сесія не авторизована. Запусти py auth_telethon.py")
    # Заборонити бот-сесії для читання історії каналів через MTProto
    try:
        me = await client.get_me()
        if getattr(me, 'bot', False):
            raise RuntimeError(
                "🚫 Telethon запущено з bot-сесією. Боти обмежені MTProto і не можуть читати історію каналів. "
                "Застосуй StringSession користувача (через телефон/2FA або QR) у TELETHON_SESSION_LOCAL/RENDER."
            )
    except Exception:
        # Якщо get_me впав — нехай верхній рівень залогує та впорається
        pass

# --- 2. Функція отримання постів ---
async def get_recent_posts(channel_username: str, limit: int = 5):
    """Отримує останні пости з каналу"""
    try:
        await ensure_connected()
        result = []
        async for message in client.iter_messages(channel_username, limit=limit):
            if not message:
                continue
            # Використовуємо raw_text, щоб гарантовано отримати підпис до медіа/повний текст
            text = getattr(message, 'raw_text', None) or getattr(message, 'message', None) or ""
            media_path = None

            # Пропускаємо завантаження медіа на етапі збору (щоб не блокувати дайджест)
            # Можна буде завантажувати точково під час надсилання, якщо потрібно
            media_path = None

            result.append({
                "id": message.id,
                "text": text.strip(),
                "date": message.date,
                "url": f"https://t.me/{channel_username}/{message.id}",
                "media": media_path
            })
        return result

    except FloodWaitError as e:
        logging.warning(f"⏳ FloodWait на {e.seconds} секунд при доступі до {channel_username}")
        await asyncio.sleep(e.seconds)
        return await get_recent_posts(channel_username, limit)
    except ChannelPrivateError:
        logging.error(f"🚫 Канал @{channel_username} приватний або недоступний.")
        return []
    except Exception as e:
        logging.error(f"❌ Помилка отримання постів з @{channel_username}: {e}")
        return []

# --- 3. Автоматично тестуємо ---
if __name__ == "__main__":
    async def test():
        posts = await get_recent_posts("bbcnews", limit=3)
        for p in posts:
            print(f"- {p['url']}: {p['text'][:50]}")
    loop.run_until_complete(test())
