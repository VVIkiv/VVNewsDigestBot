import os
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, ChannelPrivateError
from config import API_ID, API_HASH, RUN_MODE

# Ім'я сесії можна задати через змінну середовища,
# щоб локальне та серверне оточення мали різні файли/ключі
SESSION_NAME = os.getenv("TELETHON_SESSION_NAME", "user_session")

# Шлях до файлу сесії залежить від середовища
if RUN_MODE == 'render':
    SESSION_FILE = f"/tmp/{SESSION_NAME}.session"
else:
    SESSION_FILE = f"{SESSION_NAME}.session"

# Віддаємо перевагу StringSession з TELETHON_SESSION
string_session = os.getenv("TELETHON_SESSION")
if string_session:
    client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
    logging.info("📡 Telethon клієнт створено з StringSession (env)")
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
                "media": media_path,
                "channel": channel_username
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
    asyncio.run(test())
