from telethon import TelegramClient
from config import API_ID, API_HASH
import asyncio

async def main():
    client = TelegramClient('bot_session', API_ID, API_HASH)
    
    print("Начинаем процесс авторизации...")
    client.start()
    
    if client.is_user_authorized():
        print("✅ Успешная авторизация!")
        me = client.get_me()
        if hasattr(me, "first_name") and hasattr(me, "username"):
            print(f"Авторизован как: {me.first_name} (@{me.username})")
        else:
            print("Не удалось получить имя пользователя.")
    else:
        print("❌ Ошибка авторизации")
    
    client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())