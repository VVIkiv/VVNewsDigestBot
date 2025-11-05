import os
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, ChannelPrivateError
from config import API_ID, API_HASH, RUN_MODE

# Ініціалізуємо цикл подій
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

SESSION_FILE = "user_session.session"
if RUN_MODE == 'render':
    SESSION_FILE = "/tmp/user_session.session"

# Віддаємо перевагу StringSession з TELETHON_SESSION
string_session = os.getenv("TELETHON_SESSION")
if string_session:
    client = TelegramClient(StringSession(string_session), API_ID, API_HASH, loop=loop)
    logging.info("📡 Telethon клієнт створено з StringSession (env)")
else:
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH, loop=loop)
    logging.info(f"📡 Telethon клієнт створено з файловою сесією: {SESSION_FILE}")

# --- 2. Допоміжна функція ---
async def ensure_connected():
    """Підключає клієнт тільки якщо потрібно"""
    if not client.is_connected():
        await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("⚠️ Сесія не авторизована. Запусти py auth_telethon.py")

# --- 2. Функція отримання постів ---
async def get_recent_posts(channel_username: str, limit: int = 5):
    """Отримує останні пости з каналу"""
    try:
        await ensure_connected()
        result = []
        async for message in client.iter_messages(channel_username, limit=limit):
            if not message:
                continue
            text = message.text or ""
            media_path = None

            # Якщо є медіа — зберігаємо в папку media/
            if message.media:
                os.makedirs("media", exist_ok=True)
                file_path = await message.download_media(file="media/")
                media_path = file_path if file_path and os.path.exists(file_path) else None

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
