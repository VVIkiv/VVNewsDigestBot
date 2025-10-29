# config.py
import os
from dotenv import load_dotenv

# Завантажує змінні з .env локально (для dev). На Render/Prod використовуються env vars в панелі.
load_dotenv()

# Визначаємо режим роботи
RUN_MODE = os.getenv("RUN_MODE", "local").lower()

# Вибір токена залежно від режиму
if RUN_MODE == "render":
    BOT_TOKEN = os.getenv("RENDER_BOT_TOKEN")
else:
    BOT_TOKEN = os.getenv("LOCAL_BOT_TOKEN")

# Перевірка обов'язкових змінних
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не знайдено у змінних середовища.")

# Логуємо який режим використовується
print(f"🚀 Запуск у режимі: {RUN_MODE.upper()}")
print(f"🤖 Використовується бот: {BOT_TOKEN[:10]}...")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Database configuration
def get_db_path():
    """Get the appropriate database path based on the environment."""
    # On Render, use the /tmp directory which is writable
    if RUN_MODE == "render":
        db_dir = '/tmp'
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, 'channels.db')
    # For local development, use the current directory
    return 'channels.db'

DB_PATH = get_db_path()

# Webhook configuration
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не знайдено у змінних середовища.")

# Log the configuration
print(f"🚀 Конфігурація завантажена. Режим: {RUN_MODE.upper()}")
print(f"📦 База даних: {os.path.abspath(DB_PATH)}")
