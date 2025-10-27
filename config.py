# config.py
import os
from dotenv import load_dotenv

# Завантажує змінні з .env локально (для dev). На Render/Prod використовуються env vars в панелі.
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не знайдено у змінних середовища.")
