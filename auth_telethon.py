import asyncio
import os
from telethon import TelegramClient
from config import API_ID, API_HASH

async def main():
    print("⚙️  Environment: LOCAL (auto-detected)")
    print("📁 Current directory:", os.getcwd())
    print("📄 .env exists:", os.path.exists(".env"))
    print("🔍 Render detected:", "/opt/render" in os.getcwd())

    # Ім'я файлу сесії (збережеться після авторизації)
    session_name = "user_session"
    client = TelegramClient(session_name, API_ID, API_HASH)

    await client.start()
    print("✅ Успішна авторизація!")

    me = await client.get_me()
    if me:
        print(f"👤 Авторизовано як: {me.first_name} ({me.username or 'без username'})")
    else:
        print("⚠️ Не вдалося отримати інформацію про користувача")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
+380673612329