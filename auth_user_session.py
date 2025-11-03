from telethon import TelegramClient
from config import API_ID, API_HASH
import asyncio

async def main():
    # Use the same session name as in telethon_client.py
    client = TelegramClient('user_session', API_ID, API_HASH)
    
    print("🔑 Начинаем процесс авторизации для user_session...")
    await client.start()
    
    if await client.is_user_authorized():
        print("✅ Успешная авторизация!")
        me = await client.get_me()
        if hasattr(me, "first_name"):
            username = f"@{me.username}" if hasattr(me, "username") and me.username else "без username"
            print(f"Авторизован как: {me.first_name} {username}")
        else:
            print("Не удалось получить имя пользователя.")
    else:
        print("❌ Ошибка авторизации")
    
    await client.disconnect()
    print("✅ Сессия сохранена в user_session.session")

if __name__ == "__main__":
    asyncio.run(main())
