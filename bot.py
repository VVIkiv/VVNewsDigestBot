# --- ЗМІСТ ФАЙЛУ (TOC) ---
# 1. Очищення папки media
# 2. Імпорти, ініціалізація, логування
# 3. Допоміжні функції (escape_markdown, escape_markdown_v2, create_post_hash, is_similar_news тощо)
# 4. Обробники команд (start, help, addchannel, listchannels, deletechannel, addcategory, delcategory)
# 5. Клавіатури та меню (InlineKeyboardButton, InlineKeyboardMarkup)
# 6. FSM для редагування категорій
# 7. Групування та фільтрація новин
# 8. Основна логіка дайджесту (send_digest_to_user, send_digest_to_all_users)
# 9. Планувальник, очищення історії, медіа
# 10. Запуск бота (main, if __name__ == "__main__")
# --- Кінець змісту ---

# 2. Імпорти, ініціалізація, логування
import os
import sys
import logging
import asyncio
import sqlite3
import html
import threading
import http.server
import socketserver
import re
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from apscheduler.triggers.interval import IntervalTrigger
from html import escape 

# Set console encoding to UTF-8
if sys.platform == 'win32':
    import io
    import _io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='ignore')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='ignore')
from datetime import datetime, timedelta
import hashlib

# 1. Очищення папки media

def cleanup_media_folder(folder_path="media", max_age_hours=48):
    """Видаляє файли з папки media, яким більше max_age_hours годин."""
    now = datetime.now().timestamp()
    removed = 0
    if not os.path.exists(folder_path):
        return 0
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            try:
                mtime = os.path.getmtime(file_path)
                age_hours = (now - mtime) / 3600
                if age_hours > max_age_hours:
                    os.remove(file_path)
                    removed += 1
            except Exception as e:
                logging.error(f"Не вдалося видалити файл {file_path}: {e}")
    if removed > 0:
        logging.info(f"Очищено {removed} старих файлів з папки media")
    return removed
from typing import Optional, List, Dict, Any, Union
from aiogram import Bot, Dispatcher, F
from config import BOT_TOKEN, RUN_MODE, DB_PATH, PORT, WEBHOOK_URL
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile,
    InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio,
    BufferedInputFile
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# === 4️⃣ Логування ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logger.info(f"🚀 VVNewsDigestBot запущено у режимі: {RUN_MODE.upper()}")
logger.info(f"📦 Використовується база: {os.path.abspath(DB_PATH)}")

import os
import asyncio
import logging
from telethon_client import get_recent_posts, client as telethon_client

# Використовуємо спільний Telethon клієнт і функції з telethon_client.py

# === 5️⃣ Ініціалізація бази даних ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            category TEXT
        )
    """)
    conn.commit()
    conn.close()

try:
    from db import init_db, seed_db_from_file
    init_db()
    logger.info("✅ База даних успішно ініціалізована.")
    # Якщо це Render, спробуємо одноразово імпортувати стартові дані з локального файлу
    if RUN_MODE == 'render':
        try:
            seed_file = os.path.join(os.path.dirname(__file__), 'channels.db')
            inserted = seed_db_from_file(seed_file)
            if inserted > 0:
                logger.info(f"🌱 Імпортовано {inserted} записів із стартового channels.db у {DB_PATH}")
        except Exception as e:
            logger.warning(f"Не вдалося виконати початкове завантаження каналів: {e}")
except Exception as e:
    logger.error(f"❌ Помилка ініціалізації бази даних: {e}")
    raise

# === 6️⃣ Імпорт решти модулів ===
from db import (
    add_channel, get_user_channels, delete_channel,
    set_user_digest_settings, get_user_digest_settings,
    add_sent_post, is_post_sent, get_categories, get_channels,
    get_channels_by_category, update_channel_category, update_db_structure,
    cleanup_old_posts, update_category_name,
    add_category, delete_category, seed_db_from_file
)

from telethon_client import get_recent_posts, client as telethon_client

# === 7️⃣ Ініціалізація Telegram-бота ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize scheduler
scheduler = AsyncIOScheduler()

# Add cleanup job
scheduler.add_job(
    cleanup_old_posts,
    'interval',
    hours=1,
    id='cleanup_job',
    replace_existing=True,
    next_run_time=datetime.now() + timedelta(seconds=10)  # Run first cleanup 10 seconds after start
)

# Add cleanup for old scheduled digests
def cleanup_old_digests():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sent_posts WHERE sent_at < datetime('now', '-1 day')")
        conn.commit()
        conn.close()
        logging.info("Очищено застарілі пости з бази даних")
    except Exception as e:
        logging.error(f"Помилка при очищенні застарілих постів: {e}")

scheduler.add_job(
    cleanup_old_digests,
    'interval',
    days=1,  # Run daily
    id='cleanup_old_digests',
    replace_existing=True
)

def escape_markdown(text):
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

def escape_markdown_v2(text):
    if not text:
        return ""
    # Экранируем все специальные символы для MarkdownV2
    chars = '_*[]()~`>#+-=|{}.!'
    result = text
    for char in chars:
        result = result.replace(char, f'\\{char}')
    return result

# 4. Обробники команд (start, help, addchannel, listchannels, deletechannel, addcategory, delcategory)

# 4. Обробники команд (start, help, addchannel, listchannels, deletechannel, addcategory, delcategory)

@dp.message(CommandStart())
async def start_handler(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ Додати канал"),
                KeyboardButton(text="📋 Список каналів")
            ],
            [
                KeyboardButton(text="📰 Дайджест"),
                KeyboardButton(text="⚙️ Налаштування")
            ],
            [
                KeyboardButton(text="❓ Допомога")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть дію…"
    )
    bottom_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Меню")]],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Натисніть \"🏠 Меню\" для відкриття меню"
    )
    await message.answer(
        "Привіт! Я бот, який збиратиме новини з каналів і стискатиме їх до суті.",
        reply_markup=bottom_keyboard
    )
    # Додаємо також інлайн-меню, щоб кнопки були видимі в повідомленні
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати канал", callback_data="add_channel"),
         InlineKeyboardButton(text="📋 Список каналів", callback_data="list_channels")],
        [InlineKeyboardButton(text="📰 Дайджест", callback_data="digest"),
         InlineKeyboardButton(text="⚙️ Налаштування", callback_data="settings")],
        [InlineKeyboardButton(text="❓ Допомога", callback_data="help")]
    ])
    await message.answer("Оберіть дію з меню нижче:", reply_markup=inline_keyboard)

@dp.message(Command("menu"))
async def menu_handler(message: Message):
    await start_handler(message)

@dp.message(F.text == "🏠 Меню")
async def home_menu_button(message: Message):
    await menu_handler(message)

# Показувати головне меню при будь-якому тексті у приватному чаті, якщо це не наші кнопки/команди
MAIN_BUTTONS = {
    "➕ Додати канал",
    "📋 Список каналів",
    "📰 Дайджест",
    "⚙️ Налаштування",
    "❓ Допомога",
}

@dp.message(F.chat.type == "private")
async def fallback_show_menu(message: Message):
    # Ігноруємо команди та наші службові кнопки
    if message.text and (message.text.startswith("/") or message.text in MAIN_BUTTONS):
        return
    await start_handler(message)

@dp.message(F.text == "❓ Допомога")
async def kb_help(message: Message):
    await help_handler(message)

@dp.message(F.text == "📋 Список каналів")
async def kb_list_channels(message: Message):
    await list_channels_handler(message)

@dp.message(F.text == "➕ Додати канал")
async def kb_add_channel(message: Message, state: FSMContext):
    # Переходимо у стан очікування введення каналу і категорії
    if message.from_user is None:
        await message.answer("❌ Не вдалося визначити користувача.")
        return
    await message.answer(
        "Введіть канал і категорію у форматі:\n@назва_каналу номер_категорії\n\nПриклад: @example 1\n\nСписок категорій буде показано нижче."
    )
    try:
        categories = get_categories()
        if categories:
            text = "Доступні категорії:\n\n" + "\n".join([f"{cid} - {cname}" for cid, cname in categories])
            await message.answer(text)
    except Exception:
        pass
    await state.set_state(AddChannelStates.waiting_channel)

@dp.message(F.text == "📰 Дайджест")
async def kb_digest(message: Message):
    if not message.from_user:
        await message.answer("❌ Не вдалося визначити користувача.")
        return
    try:
        categories = get_categories()
    except Exception as e:
        categories = []
        logging.error(f"Не вдалося отримати категорії: {e}")

    buttons = []
    for cid, cname in categories:
        buttons.append([InlineKeyboardButton(text=f"🗂 {cname}", callback_data=f"digest_cat_{cid}")])
    buttons.append([InlineKeyboardButton(text="📚 Всі категорії", callback_data="digest_all")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Виберіть категорію для дайджесту:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data and c.data.startswith("digest_cat_"))
async def on_digest_category(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    try:
        cat_id_str = cb.data.split("digest_cat_")[-1]
        category_id = int(cat_id_str)
    except Exception:
        await cb.answer("Невірна категорія", show_alert=False)
        return
    await cb.answer("Формую дайджест…", show_alert=False)
    await send_digest_to_user(cb.from_user.id, category_id=category_id)

@dp.callback_query(lambda c: c.data == "digest_all")
async def on_digest_all(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    await cb.answer("Формую повний дайджест…", show_alert=False)
    await send_digest_to_user(cb.from_user.id)

@dp.message(F.text == "⚙️ Налаштування")
async def kb_settings(message: Message):
    if not message.from_user:
        await message.answer("❌ Не вдалося визначити користувача.")
        return
    settings = get_user_digest_settings(message.from_user.id)
    text = (
        "⚙️ Налаштування дайджесту\n\n"
        f"Статус: {'Увімкнено' if settings.get('enabled') else 'Вимкнено'}\n"
        f"Інтервал: {settings.get('interval_hours', 2)} год\n"
        f"Медіа: {'файлами' if settings.get('media_as_file') else 'як фото/відео'}\n"
        f"Email: {'Увімкнено' if settings.get('email_enabled') else 'Вимкнено'}"
        + (f" ({settings.get('email_to')})" if settings.get('email_to') else "")
        + "\n"
    )
    keyboard = build_settings_keyboard(settings)
    await message.answer(text, reply_markup=keyboard)

def build_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=("🟢 Автодайджест увімкнено" if settings.get('enabled') else "🔴 Автодайджест вимкнено"),
            callback_data="settings_toggle_enabled"
        )],
        [InlineKeyboardButton(
            text=f"⏱ Інтервал: {settings.get('interval_hours', 2)} год",
            callback_data="settings_interval_menu"
        )],
        [InlineKeyboardButton(
            text=("📎 Надсилати як файли" if settings.get('media_as_file') else "🖼 Надсилати як фото/відео"),
            callback_data="settings_media_toggle"
        )],
        [InlineKeyboardButton(
            text=("📧 Email розсилка: увімкнено" if settings.get('email_enabled') else "📧 Email розсилка: вимкнено"),
            callback_data="settings_email_toggle"
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.callback_query(lambda c: c.data == "settings_toggle_enabled")
async def cb_settings_toggle_enabled(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    current = get_user_digest_settings(cb.from_user.id)
    try:
        set_user_digest_settings(cb.from_user.id, enabled=not current.get('enabled', False))
        updated = get_user_digest_settings(cb.from_user.id)
        text = (
            "⚙️ Налаштування дайджесту\n\n"
            f"Статус: {'Увімкнено' if updated.get('enabled') else 'Вимкнено'}\n"
            f"Інтервал: {updated.get('interval_hours', 2)} год\n"
            f"Медіа: {'файлами' if updated.get('media_as_file') else 'як фото/відео'}\n"
            f"Email: {'Увімкнено' if updated.get('email_enabled') else 'Вимкнено'}"
            + (f" ({updated.get('email_to')})" if updated.get('email_to') else "")
            + "\n"
        )
        await cb.message.edit_text(text, reply_markup=build_settings_keyboard(updated))
        await cb.answer("Збережено")
    except Exception as e:
        await cb.answer(f"Помилка: {e}", show_alert=True)

@dp.callback_query(lambda c: c.data == "settings_media_toggle")
async def cb_settings_media_toggle(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    current = get_user_digest_settings(cb.from_user.id)
    try:
        set_user_digest_settings(cb.from_user.id, media_as_file=not current.get('media_as_file', False))
        updated = get_user_digest_settings(cb.from_user.id)
        text = (
            "⚙️ Налаштування дайджесту\n\n"
            f"Статус: {'Увімкнено' if updated.get('enabled') else 'Вимкнено'}\n"
            f"Інтервал: {updated.get('interval_hours', 2)} год\n"
            f"Медіа: {'файлами' if updated.get('media_as_file') else 'як фото/відео'}\n"
        )
        await cb.message.edit_text(text, reply_markup=build_settings_keyboard(updated))
        await cb.answer("Збережено")
    except Exception as e:
        await cb.answer(f"Помилка: {e}", show_alert=True)

@dp.callback_query(lambda c: c.data == "settings_interval_menu")
async def cb_settings_interval_menu(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    current = get_user_digest_settings(cb.from_user.id)
    buttons = [
        [InlineKeyboardButton(text="1 год", callback_data="settings_interval_1"),
         InlineKeyboardButton(text="2 год", callback_data="settings_interval_2"),
         InlineKeyboardButton(text="3 год", callback_data="settings_interval_3")],
        [InlineKeyboardButton(text="6 год", callback_data="settings_interval_6"),
         InlineKeyboardButton(text="12 год", callback_data="settings_interval_12"),
         InlineKeyboardButton(text="24 год", callback_data="settings_interval_24")],
        [InlineKeyboardButton(text="« Назад", callback_data="settings_back")]
    ]
    text = (
        "⏱ Виберіть інтервал розсилки\n\n"
        f"Поточний: {current.get('interval_hours', 2)} год"
    )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("settings_interval_"))
async def cb_settings_set_interval(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    try:
        hours = int(cb.data.split("settings_interval_")[-1])
        set_user_digest_settings(cb.from_user.id, interval_hours=hours)
        updated = get_user_digest_settings(cb.from_user.id)
        text = (
            "⚙️ Налаштування дайджесту\n\n"
            f"Статус: {'Увімкнено' if updated.get('enabled') else 'Вимкнено'}\n"
            f"Інтервал: {updated.get('interval_hours', 2)} год\n"
            f"Медіа: {'файлами' if updated.get('media_as_file') else 'як фото/відео'}\n"
        )
        await cb.message.edit_text(text, reply_markup=build_settings_keyboard(updated))
        await cb.answer("Інтервал збережено")
    except Exception as e:
        await cb.answer(f"Помилка: {e}", show_alert=True)

@dp.callback_query(lambda c: c.data == "settings_back")
async def cb_settings_back(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    updated = get_user_digest_settings(cb.from_user.id)
    text = (
        "⚙️ Налаштування дайджесту\n\n"
        f"Статус: {'Увімкнено' if updated.get('enabled') else 'Вимкнено'}\n"
        f"Інтервал: {updated.get('interval_hours', 2)} год\n"
        f"Медіа: {'файлами' if updated.get('media_as_file') else 'як фото/відео'}\n"
        f"Email: {'Увімкнено' if updated.get('email_enabled') else 'Вимкнено'}"
        + (f" ({updated.get('email_to')})" if updated.get('email_to') else "")
        + "\n"
    )
    await cb.message.edit_text(text, reply_markup=build_settings_keyboard(updated))
    await cb.answer()

@dp.callback_query(lambda c: c.data == "settings_email_toggle")
async def cb_settings_email_toggle(cb: CallbackQuery):
    if not cb.from_user:
        await cb.answer()
        return
    current = get_user_digest_settings(cb.from_user.id)
    try:
        set_user_digest_settings(cb.from_user.id, email_enabled=not current.get('email_enabled', False))
        updated = get_user_digest_settings(cb.from_user.id)
        text = (
            "⚙️ Налаштування дайджесту\n\n"
            f"Статус: {'Увімкнено' if updated.get('enabled') else 'Вимкнено'}\n"
            f"Інтервал: {updated.get('interval_hours', 2)} год\n"
            f"Медіа: {'файлами' if updated.get('media_as_file') else 'як фото/відео'}\n"
            f"Email: {'Увімкнено' if updated.get('email_enabled') else 'Вимкнено'}"
            + (f" ({updated.get('email_to')})" if updated.get('email_to') else "")
            + "\n"
        )
        await cb.message.edit_text(text, reply_markup=build_settings_keyboard(updated))
        await cb.answer("Збережено")
    except Exception as e:
        await cb.answer(f"Помилка: {e}", show_alert=True)

# --- FSM для додавання каналу без команд ---
class AddChannelStates(StatesGroup):
    waiting_channel = State()

@dp.message(AddChannelStates.waiting_channel)
async def add_channel_via_fsm(message: Message, state: FSMContext):
    if not message.text or message.from_user is None:
        await message.answer("❌ Надішліть у форматі: @назва_каналу номер_категорії")
        return
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[0].startswith("@"):
        await message.answer("❌ Формат: @назва_каналу номер_категорії")
        return
    channel = parts[0].lstrip('@')
    try:
        category_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Номер категорії має бути числом")
        return
    # Перевіримо наявність категорії
    categories = get_categories()
    category_name = next((name for cid, name in categories if cid == category_id), None)
    if category_name is None:
        await message.answer("❌ Категорія не знайдена. Спробуйте ще раз.")
        return
    try:
        add_channel(message.from_user.id, channel, category_id)
        await message.answer(f"✅ Канал @{channel} додано до категорії {category_name}!")
    except Exception as e:
        await message.answer(f"❌ Помилка додавання каналу: {e}")
        return
    finally:
        await state.clear()

# Добавим обработчик для кнопки "Допомога"
@dp.callback_query(lambda c: c.data == "help")
async def inline_help(callback: CallbackQuery):
    help_text = """🤖 *Допомога з командами бота:*

📝 *Основні команди:*
• /start — запуск бота
• /help — це повідомлення
• /digest — отримати дайджест зараз

📺 *Робота з каналами:*
• /addchannel @назва — додати канал
• /listchannels — список каналів
• /deletechannel @назва — видалити канал

⚙️ *Налаштування:*
• /setdigest on — увімкнути автодайджест
• /setdigest off — вимкнути автодайджест
• /setdigest 3h — встановити інтервал (1-24h)
• /clearhistory — очистити історію постів
• /addcategory Назва_категорії — додати категорію
• /delcategory id_категорії — видалити категорію

🔍 *Додатково:*
• Дайджест автоматично видаляє дублікати
• Медіафайли зберігаються 24 години
• Історія постів зберігається 7 днів"""
# 5. Клавіатури та меню (InlineKeyboardButton, InlineKeyboardMarkup)

    # Создаем клавиатуру с кнопкой "Назад"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
    ])
    
    if callback.message:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
            message_id=callback.message.message_id,
            text=help_text,
            parse_mode="Markdown",
            reply_markup=keyboard  # Добавляем клавиатуру
        )
    else:
        await bot.send_message(
            chat_id=callback.from_user.id,
            text=help_text,
            parse_mode="Markdown",
            reply_markup=keyboard  # Добавляем клавиатуру
        )
    await callback.answer()

@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer("""Команди:
/start — запуск
/help — допомога
/addchannel @назва — додати канал
/listchannels — список каналів
/deletechannel @назва — видалити канал
/digest — отримати дайджест
/setdigest [on/off/2h/3h...] — керування авто-дайджестом
/clearhistory — очистити історію отправлених постів
/addcategory Назва_категорії — додати категорію
/delcategory id_категорії — видалити категорію""")

@dp.message(Command("addchannel"))
async def add_channel_handler(message: Message, command: CommandObject):
    if not message.text:
        await message.answer("❌ Формат: /addchannel @назва_каналу [категорія]")
        return
        
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith("@"): 
        await message.answer("❌ Формат: /addchannel @назва_каналу [категорія]")
        return
        
    channel = args[1].lstrip("@")
    
    # Проверяем указана ли категория
    if len(args) <= 2:
        # Показываем список категорий
        categories = get_categories()
        text = "Виберіть категорію для каналу:\n\n"
        for cat_id, cat_name in categories:
            text += f"{cat_id} - {cat_name}\n"
        text += "\nВикористайте команду:\n/addchannel @назва_каналу номер_категорії"
        await message.answer(text)
        return
        
    try:
        category_id = int(args[2])
        # Проверяем существует ли такая категория
        categories = get_categories()
        category_name = next((name for id, name in categories if id == category_id), None)
        
        if category_name is None:
            await message.answer("❌ Категорія не знайдена. Використайте правильний номер категорії.")
            return
            
        if message.from_user is None:
            await message.answer("❌ Не вдалося визначити користувача.")
            return
            
        add_channel(message.from_user.id, channel, category_id)
        await message.answer(f"✅ Канал @{channel} додано до категорії {category_name}!")
        
    except ValueError:
        await message.answer("❌ Номер категорії має бути числом")

@dp.message(Command("listchannels"))
async def list_channels_handler(message: Message):
    if not message.from_user:
        return

    channels = get_channels(message.from_user.id)
    if not channels:
        await message.answer("🔍 Ви ще не додали жодного каналу.")
        return
    
# 6. FSM для редагування категорій
    # Группируем каналы по категориям
    channels_by_category = {}
    for channel, category in channels:
        if category not in channels_by_category:
            channels_by_category[category] = []
        channels_by_category[category].append(channel)

    # Формируем текст и кнопки
    text = "📋 Ваші канали по категоріям:\n\n"
    keyboard_buttons = []
    for category, channel_list in channels_by_category.items():
        text += f"📑 {category}:\n"
        for channel in channel_list:
            text += f"• @{channel}\n"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="❌",
                    callback_data=f"delete_channel_{channel}"
                ),
                InlineKeyboardButton(
                    text="↔️",
                    callback_data=f"move_channel_{channel}"
                ),
                InlineKeyboardButton(
                    text=f"@{channel}",
                    callback_data=f"channel_info_{channel}"
                )
            ])
        text += "\n"

    # Додаємо список категорій для зміни
    categories = get_categories()
    text += "\n🗂 *Список категорій для зміни назви:*\n"
    for cat_id, cat_name in categories:
        text += f"• {cat_id}: {cat_name}\n"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"✏️ Змінити назву '{cat_name}'",
                callback_data=f"edit_category_{cat_id}"
            )
        ])

    keyboard_buttons.extend([
        [InlineKeyboardButton(text="➕ Додати канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data and c.data.startswith("channel_info_"))
async def channel_info_noop(cb: CallbackQuery):
    # Нічого не робимо, кнопка лише як мітка
    await cb.answer()

@dp.message(Command("deletechannel"))
async def delete_channel_handler(message: Message, command: CommandObject):
    if not message.text:
        await message.answer("❌ Формат: /deletechannel @назва_каналу")
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].startswith("@"): 
        await message.answer("❌ Формат: /deletechannel @назва_каналу")
        return
    channel = args[1].lstrip("@")
    if message.from_user is None:
        await message.answer("❌ Не вдалося визначити користувача.")
        return
    if delete_channel(message.from_user.id, channel):
        await message.answer(f"✅ Канал @{channel} видалено!")
    else:
        await message.answer(f"❌ Канал @{channel} не знайдено.")
# 7. Групування та фільтрація новин

def create_post_hash(
    text: Optional[str],
    channel: Optional[str],
    date: Optional[datetime] = None,
    media: Optional[str] = None,
    url: Optional[str] = None,
    message_id: Optional[int] = None
) -> str:
    """Створює стабільний хеш поста з урахуванням змісту, а не часу."""
    normalized_text = ""
    if text:
        normalized_text = re.sub(r'http\S+', '', text)
        normalized_text = re.sub(r'\s+', ' ', normalized_text).strip().lower()

    hash_parts = []
    if normalized_text:
        hash_parts.append(normalized_text[:500])

    if media:
        try:
            file_size = os.path.getsize(media)
            hash_parts.append(f"{os.path.basename(media)}:{file_size}")
        except Exception as e:
            logging.debug(f"Media size read error for {media}: {e}")

    if not hash_parts:
        if url:
            hash_parts.append(url)
        elif channel and date:
            hash_parts.append(f"{channel}:{int(date.timestamp())}")
        elif channel:
            hash_parts.append(channel)
        elif date:
            hash_parts.append(str(int(date.timestamp())))

    if message_id is not None and channel:
        hash_parts.append(f"msg:{channel}:{message_id}")

    content = "|".join(hash_parts) or (url or f"{channel}:{date}" if (channel or date) else "empty")
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def are_posts_similar(text1: str, text2: str) -> bool:
    """Проверяет схожесть двух текстов"""
    if not text1 or not text2:
        return False
        
    # Очищаем тексты
    def clean_text(text: str) -> str:
        # Удаляем ссылки, эмодзи, спецсимволы
        text = re.sub(r'http\S+', '', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.lower().strip()
    
    text1 = clean_text(text1)
    text2 = clean_text(text2)
    
    # Если тексты слишком короткие, считаем их разными
    if len(text1) < 10 or len(text2) < 10:
        return False
    
    # Разбиваем на слова
    words1 = set(text1.split())
    words2 = set(text2.split())
    
    # Находим общие слова
    common_words = words1.intersection(words2)
    
    # Вычисляем процент совпадения
    similarity = len(common_words) / max(len(words1), len(words2))
    
    return similarity > 0.4  # Порог схожести 40%

import difflib

def is_similar_news(text1, text2, threshold=0.7):
    """Повертає True, якщо тексти схожі більше ніж на threshold (0..1)"""
    if not text1 or not text2:
        return False
    seq = difflib.SequenceMatcher(None, text1, text2)
    return seq.ratio() > threshold

async def send_digest_to_user(user_id: int, category_id: Optional[int] = None):
    try:
        # Получаем каналы в зависимости от выбранной категории
        if category_id:
            channels = get_channels_by_category(user_id, category_id)
            if not channels:
                await bot.send_message(
                    chat_id=user_id,
                    text="❗ У цій категорії немає каналів."
                )
                return
        else:
            channels = get_channels(user_id)
            if not channels:
                await bot.send_message(
                    chat_id=user_id,
                    text="❗ Ви ще не додали жодного каналу."
                )
                return

        # Получаем только имена каналов из результатов
        cleaned_channels = []
        for channel_data in channels:
            if isinstance(channel_data, tuple):
                channel_name = channel_data[0]  # Первый элемент кортежа - имя канала
            else:
                channel_name = channel_data
            
            if channel_name and len(channel_name.strip()) > 1:
                cleaned_channels.append(channel_name.strip().lstrip('@'))

        if not cleaned_channels:
            await bot.send_message(
                chat_id=user_id,
                text="❗ Не знайдено дійсних каналів для отримання новин."
            )
            return

        logging.info(f"Получаем новости из каналов: {cleaned_channels}")
     # 8. Основна логіка дайджесту (send_digest_to_user, send_digest_to_all_users)
 
        # Получаем посты из каналов (расширяем окно до 20 постов на канал)
        fetch_tasks = [get_recent_posts(channel, limit=20) for channel in cleaned_channels]
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        # Фильтруем результаты, исключая ошибки
        all_posts = []
        for channel, result in zip(cleaned_channels, results):
            if isinstance(result, Exception):
                logging.error(f"Ошибка при получении постов из канала {channel}: {result}")
                continue
            if isinstance(result, list):
                all_posts.extend(result)
            else:
                logging.error(f"Неожиданный тип результата из канала {channel}: {type(result)}")

        new_posts_count = 0
        seen_hashes = set()
        processed_posts = []

        # Сортируем посты по дате
        all_posts.sort(key=lambda x: x['date'], reverse=True)

        for post in all_posts:
            post_hash = create_post_hash(
                text=post.get('text'),
                channel=post.get('channel'),
                date=post.get('date'),
                media=post.get('media'),
                url=post.get('url'),
                message_id=post.get('id')
            )

            if post_hash in seen_hashes:
                continue
            seen_hashes.add(post_hash)

            if not is_post_sent(user_id, post_hash):
                post['digest_hash'] = post_hash
                processed_posts.append(post)
                new_posts_count += 1
                add_sent_post(user_id, post_hash)

                if new_posts_count >= 20:
                    break

        if not processed_posts:
            await bot.send_message(
                chat_id=user_id,
                text="🤔 Нових постів поки немає."
            )
            return

        # Отправляем дайджест
        digest_text = "📰 *Дайджест нових постів*\n\n"
        
        # Получаем настройки пользователя
        user_settings = get_user_digest_settings(user_id)
        user_threshold = user_settings.get('similarity_threshold', 0.7)

        filtered_posts = []
        seen_urls = set()
        for post in processed_posts:
            is_duplicate = False

            post_url = post.get('url')
            if post_url:
                if post_url in seen_urls:
                    continue
                seen_urls.add(post_url)

            for f_post in filtered_posts:
                if is_similar_news(post.get('text', ''), f_post.get('text', ''), threshold=user_threshold):
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered_posts.append(post)

        for post in filtered_posts:
            try:
                # Подготавливаем текст поста
                post_text_full = post.get('text', '') or ''
                shortened_text = post_text_full[:200] + ('...' if len(post_text_full) > 200 else '')
                escaped_text = escape_markdown_v2(shortened_text)
                post_url = escape_markdown_v2(post['url'])
                
                post_text = f"🔹 {escaped_text}\n\n"
                post_text += f"🔗 [       Читати повністю    Читати повністю   Читати повністю                        ]({post_url})\n\n\n"
                # Если есть медиа, отправляем его с текстом
                if post['media'] and os.path.exists(post['media']):
                    try:
                        if post['media'].endswith(('.mp4', '.avi', '.mov')):
                            await bot.send_video(
                                chat_id=user_id,
                                video=types.FSInputFile(post['media']),
                                caption=post_text,
                                parse_mode="MarkdownV2"
                            )
                        else:
                            await bot.send_photo(
                                chat_id=user_id,
                                photo=types.FSInputFile(post['media']),
                                caption=post_text,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        logging.error(f"Помилка при відправці поста з медіа: {e}")
                        # Если не удалось отправить з медіа, отправляем только текст
                        await bot.send_message(
                            chat_id=user_id,
                            text=post_text,
                            parse_mode="MarkdownV2"
                        )
                else:
                    # Если медиа нет, отправляем только текст
                    await bot.send_message(
                        chat_id=user_id,
                        text=post_text,
                        parse_mode="MarkdownV2"
                    )
            except Exception as e:
                logging.error(f"Помилка при відправці поста: {e}")
                continue

        # Отправляем информацию о следующем дайджесте
        user_settings = get_user_digest_settings(user_id)
        interval_hours = user_settings.get('interval_hours', 1)
        now = datetime.now()
        # Розраховуємо наступний час розсилки (початок години)
        current_hour = now.hour
        next_hour = ((current_hour + interval_hours - 1) // interval_hours) * interval_hours
        if next_hour <= current_hour:
            next_hour += interval_hours
            
        next_digest = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        if next_digest <= now:
            next_digest += timedelta(hours=interval_hours)
            
        # Розраховуємо різницю в часі для повідомлення
        time_diff = next_digest - now + timedelta(hours=2)
        hours_diff = int(time_diff.total_seconds() / 3600)
        minutes_diff = int((time_diff.total_seconds() % 3600) / 60)
        
        time_text = f"{hours_diff - 2} год"
        if minutes_diff > 0:
            time_text += f" {minutes_diff} хв"
            
        await bot.send_message(
            
            chat_id=user_id,
            text=f"✅ Дайджест завершено!\nНаступний дайджест буде відправлено о {(next_digest + timedelta(hours=2)).strftime('%H:%M')} (через {time_text})")
  
        # === 9️⃣ Надсилання дайджесту на пошту (з урахуванням налаштувань користувача) ===
        from notifier import send_email_digest, save_html_digest
        import os

        try:
            if processed_posts:
                user_settings = get_user_digest_settings(user_id)
                if user_settings.get('email_enabled') and (user_settings.get('email_to') or os.getenv("EMAIL_TO")):
                    save_html_digest(processed_posts, "daily_digest.html")
                    recipient = user_settings.get('email_to') or os.getenv("EMAIL_TO")
                    send_email_digest(
                        "VVNewsDigest — сьогоднішні новини",
                        processed_posts,
                        recipient
                    )
                    logging.info("📧 Дайджест успішно відправлено на email.")
                else:
                    logging.info("📧 Email-розсилка вимкнена або не налаштована адреса — пропускаю відправлення.")
            else:
                logging.info("⚠️ Немає нових постів для відправлення email.")
        except Exception as e:
            logging.error(f"❌ Помилка під час відправлення email-дайджесту: {e}")

    except Exception as e:
        logging.error(f"Помилка при відправці дайджесту: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=user_id,
            text="❌ Виникла помилка при формуванні дайджесту. Спробуйте пізніше."
        )


async def send_user_digest_with_preferences(user_id: int):
    """
    Відправляє дайджест із урахуванням вибраних категорій користувача.
    Якщо категорії не вибрані — надсилає повний дайджест.
    """
    try:
        settings = get_user_digest_settings(user_id)
    except Exception as e:
        logging.error(f"Не вдалося отримати налаштування користувача {user_id}: {e}")
        return

    selected_categories = settings.get('selected_categories') or []

    if selected_categories:
        for category_id in selected_categories:
            try:
                await send_digest_to_user(user_id, category_id=category_id)
            except Exception as e:
                logging.error(
                    f"Помилка при відправці дайджесту користувачу {user_id} "
                    f"для категорії {category_id}: {e}"
                )
    else:
        await send_digest_to_user(user_id)


@dp.message(Command("digest"))
async def digest_handler(message: Message):
    if message.from_user:
        await send_digest_to_user(message.from_user.id)

async def send_digest_to_all_users():
    """Отправка дайджеста всем пользователям с учетом выбранных категорий"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id
        FROM user_settings 
        WHERE enabled = 1
    """)
    users = [row[0] for row in cursor.fetchall()]
    conn.close()

    for user_id in users:
        try:
            await send_user_digest_with_preferences(user_id)
        except Exception as e:
            logging.error(f"Не вдалося надіслати дайджест користувачу {user_id}: {e}")

# --- Додатково: керування задачами розсилки для кожного користувача ---
user_digest_jobs = {}

def schedule_user_digest(scheduler, user_id, interval_hours):
    job_id = f"user_digest_{user_id}"
    # Видаляємо стару задачу, якщо є
    if job_id in user_digest_jobs:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
    
    # Розраховуємо час першого запуску (наступна година кратна інтервалу)
    now = datetime.now()
    current_hour = now.hour
    next_hour = ((current_hour + interval_hours - 1) // interval_hours) * interval_hours
    if next_hour <= current_hour:
        next_hour += interval_hours
    
    start_time = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
    if start_time <= now:
        start_time += timedelta(hours=interval_hours)
    
    # Додаємо нову задачу з потрібним інтервалом
    job = scheduler.add_job(
        send_user_digest_with_preferences,
        trigger=IntervalTrigger(hours=interval_hours, start_date=start_time),
        args=[user_id],
        id=job_id,
        replace_existing=True
    )
    user_digest_jobs[job_id] = job

def remove_user_digest_job(scheduler, user_id):
    job_id = f"user_digest_{user_id}"
    if job_id in user_digest_jobs:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        user_digest_jobs.pop(job_id, None)

@dp.message(Command("setdigest"))
async def setdigest_handler(message: Message, command: CommandObject):
    if not message.text:
        await message.answer("❌ Формат: /setdigest [on/off/2h/3h/…]")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Формат: /setdigest [on/off/2h/3h/…]")
        return

    value = args[1].lower()
    if message.from_user is None:
        await message.answer("❌ Не вдалося визначити користувача.")
        return
    user_id = message.from_user.id
    if value == "off":
        set_user_digest_settings(user_id, enabled=False)
        remove_user_digest_job(scheduler, user_id)
        await message.answer("🔕 Автоматичну розсилку вимкнено.")
    elif value == "on":
        set_user_digest_settings(user_id, enabled=True, interval_hours=2)
        schedule_user_digest(scheduler, user_id, 2)
        await message.answer("🔔 Автоматичну розсилку увімкнено (кожні 2 години).")
    elif value.endswith("h") and value[:-1].isdigit():
        hours = int(value[:-1])
        if 1 <= hours <= 24:
            set_user_digest_settings(user_id, enabled=True, interval_hours=hours)
            schedule_user_digest(scheduler, user_id, hours)
            await message.answer(f"🔔 Автоматичну розсилку увімкнено (кожні {hours} годин).")
        else:
            await message.answer("❌ Допустимі значення — від 1h до 24h")
    else:
        await message.answer("❌ Неправильне значення. Спробуйте /setdigest 3h або /setdigest off")

@dp.callback_query(lambda c: c.data == "select_digest_categories")
async def select_digest_categories(callback: CallbackQuery):
    """Меню вибору категорій для автодайджесту"""
    if callback.from_user is None:
        return

    settings = get_user_digest_settings(callback.from_user.id)
    selected_categories = settings.get('selected_categories', [])
    categories = get_categories()
    keyboard_buttons = []

    for cat_id, cat_name in categories:
        is_selected = cat_id in selected_categories
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{'✅' if is_selected else '❌'} {cat_name}",
                callback_data=f"toggle_digest_category_{cat_id}"
            )
        ])

    keyboard_buttons.extend([
        [InlineKeyboardButton(
            text="✨ Вибрати всі",
            callback_data="select_all_digest_categories"
        )],
        [InlineKeyboardButton(
            text="« Назад",
            callback_data="settings"
        )]
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    text = """*📑 Виберіть категорії для автодайджесту*

✅ — категорія включена
❌ — категорія виключена

Якщо не вибрана жодна категорія — будуть враховуватися всі."""

    if callback.message:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("toggle_digest_category_"))
async def toggle_digest_category(callback: CallbackQuery):
    """Включення/виключення категорії"""
    if callback.from_user is None:
        return

    try:
        if not callback.data:
            await callback.answer("❌ Помилка: не вдалося визначити категорію.", show_alert=True)
            return
        category_id = int(callback.data.replace("toggle_digest_category_", ""))
        settings = get_user_digest_settings(callback.from_user.id)
        
        # Преобразуем строку с ID категорий в список целых чисел
        selected_categories = []
        if settings.get('selected_categories'):
            if isinstance(settings['selected_categories'], str):
                selected_categories = [int(x) for x in settings['selected_categories'].split(',')]
            elif isinstance(settings['selected_categories'], list):
                selected_categories = [int(x) for x in settings['selected_categories']]

        # Переключаем категорию
        if category_id in selected_categories:
            selected_categories.remove(category_id)
        else:
            selected_categories.append(category_id)

        # Сохраняем обновленный список
        set_user_digest_settings(
            callback.from_user.id,
            selected_categories=selected_categories
        )

        await callback.answer("✅ Налаштування збережено")
        await select_digest_categories(callback)

    except Exception as e:
        logging.error(f"Помилка переключення категорії: {e}")
        await callback.answer("❌ Помилка зміни налаштувань", show_alert=True)
    
@dp.callback_query(lambda c: c.data == "list_channels")
async def inline_list_channels(cb: CallbackQuery):
    channels = get_channels(cb.from_user.id)
    categories_list = get_categories()
    
    keyboard_buttons = []
    text = ""
    if not channels:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Додати канал", callback_data="add_channel")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
        ])
        text = "🔍 У вас ще немає доданих каналів\n\nНатисніть кнопку «Додати канал», щоб почати."
        if cb.message:
            await bot.edit_message_text(
                chat_id=cb.message.chat.id if cb.message else cb.from_user.id,
                message_id=cb.message.message_id,
                text=text,
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                chat_id=cb.from_user.id,
                text=text,
                reply_markup=keyboard
            )
        await cb.answer()
        return

    # Группируем каналы по категориям
    channels_by_category = {}
    for channel, category in channels:
        if category not in channels_by_category:
            channels_by_category[category] = []
        channels_by_category[category].append(channel)
    
    text += "📋 Ваші канали по категоріям:\n\n"
    for category, channel_list in channels_by_category.items():
        text += f"📑 {category}:\n"
        for channel in channel_list:
            text += f"• @{channel}\n"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"❌ Видалити @{channel}",
                    callback_data=f"delete_channel_{channel}"
                ),
                InlineKeyboardButton(
                    text=f"📋 Перемістити @{channel}",
                    callback_data=f"move_channel_{channel}"
                )
            ])
        text += "\n"
    
    # Додаємо список категорій для зміни
    text += "\n🗂 *Список категорій для зміни назви:*\n"
    for cat_id, cat_name in categories_list:
        text += f"• {cat_id}: {cat_name}\n"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"✏️ Змінити назву '{cat_name}'",
                callback_data=f"edit_category_{cat_id}"
            )
        ])
    
    keyboard_buttons.extend([
        [InlineKeyboardButton(text="➕ Додати канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    if cb.message:
        try:
            await bot.edit_message_text(
                chat_id=cb.message.chat.id if cb.message else cb.from_user.id,
                message_id=cb.message.message_id if cb.message else None,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
    else:
        await bot.send_message(
            chat_id=cb.from_user.id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    await cb.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Додати канал", callback_data="add_channel"),
            InlineKeyboardButton(text="📋 Список каналів", callback_data="list_channels")
        ],
        [
            InlineKeyboardButton(text="📰 Дайджест", callback_data="digest"),
            InlineKeyboardButton(text="⚙️ Налаштування", callback_data="settings")
        ],
        [
            InlineKeyboardButton(text="❓ Допомога", callback_data="help")
        ]
    ])
    
    if callback.message:
        if callback.message:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
                message_id=callback.message.message_id if callback.message else None,
                text="Головне меню:",
                reply_markup=keyboard
            )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "add_channel")
async def inline_add_channel(callback: CallbackQuery):
    """Показ списка категорій для добавления канала"""
    categories = get_categories()
    keyboard_buttons = []
    
    for cat_id, cat_name in categories:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=cat_name,
                callback_data=f"select_category_{cat_id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="« Назад", callback_data="back_to_main")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    text = "*📝 Виберіть категорію для нового каналу:*"
    
    if callback.message:
        if callback.message and callback.message.message_id:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
                message_id=callback.message.message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("delete_channel_"))
async def delete_channel_button(callback: CallbackQuery):
    """Удаление канала по кнопке"""
    if callback.data is None:
        await callback.answer("❌ Помилка: не вдалося визначити канал.", show_alert=True)
        return
    channel = callback.data.replace("delete_channel_", "")
    if delete_channel(callback.from_user.id, channel):
        await callback.answer(f"✅ Канал @{channel} видалено!", show_alert=True)
        # Обновляем список каналов
        await inline_list_channels(callback)
    else:
        await callback.answer(f"❌ Помилка видалення каналу @{channel}", show_alert=True)

@dp.callback_query(lambda c: c.data and c.data.startswith("select_category_"))
async def category_selected(callback: CallbackQuery):
    """Обработка выбора категории при добавлении канала"""
    if not callback.data:
        await callback.answer("❌ Помилка: не вдалося визначити категорію.", show_alert=True)
        return
    category_id = int(callback.data.replace("select_category_", ""))
    categories = get_categories()
    category_name = next((name for id, name in categories if id == category_id), "Інше")
    
    text = f"""*📝 Додавання каналу в категорію "{category_name}"*

Для додавання каналу відправте команду:
"`/addchannel @назва\\_каналу {category_id}`"

Наприклад:
`/addchannel @mychannel {category_id}`

 *Важливо:*
• Канал має бути публічним
• Використовуйте @ перед назвою каналу
• Бот повинен мати доступ до каналу"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад до категорій", callback_data="add_channel")],
        [InlineKeyboardButton(text="« Головне меню", callback_data="back_to_main")]
    ])

    if callback.message:
        try:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
                message_id=callback.message.message_id,
                text=text,
                parse_mode="MarkdownV2",
                reply_markup=keyboard
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == "digest")
async def inline_digest(callback: CallbackQuery):
    """Обработка кнопки дайджеста"""
    categories = get_categories()
    keyboard_buttons = []
    
    # Добавляем кнопку для полного дайджеста
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="📰 Повний дайджест",
            callback_data="digest_all"
        )
    ])
    
    # Добавляем кнопки для каждой категории
    for cat_id, cat_name in categories:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"📚 {cat_name}",
                callback_data=f"digest_category_{cat_id}"
            )
        ])
    
    # Добавляем кнопку "Назад"
    keyboard_buttons.append([
        InlineKeyboardButton(text="« Назад", callback_data="back_to_main")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    text = r"""📚 Виберіть тип дайджесту:

• Повний дайджест \- всі канали
• Або виберіть конкретну категорію"""

    if callback.message:
        await bot.edit_message_text(
        chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
        message_id=callback.message.message_id if callback.message else None,
        text=text,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "digest_all")
async def digest_all(callback: CallbackQuery):
    """Отправка полного дайджеста"""
    await callback.answer("⏳ Збираю дайджест...", show_alert=True)
    await send_digest_to_user(callback.from_user.id)

@dp.callback_query(lambda c: c.data and c.data.startswith("digest_category_"))
async def digest_category(callback: CallbackQuery):
    """Отправка дайджета по категории"""
    try:
        if not callback.data:
            await callback.answer("❌ Помилка: не вдалося визначити категорію.", show_alert=True)
            return
            
        category_id = int(callback.data.replace("digest_category_", ""))
        
        # Получаем каналы в этой категории
        channels = get_channels_by_category(callback.from_user.id, category_id)
        
        if not channels:
            await callback.answer("❌ У цій категорії немає каналів", show_alert=True)
            return
            
        # Получаем название категории
        categories = get_categories()
        category_name = next((name for id, name in categories if id == category_id), "Невідома")
        
        await callback.answer(
            f"⏳ Збираю дайджест для категорії {category_name}...",
            show_alert=True
        )
        await send_digest_to_user(callback.from_user.id, category_id=category_id)
        
    except Exception as e:
        logging.error(f"Помилка отримання дайджесту по категорії: {e}")
        await callback.answer("❌ Помилка отримання дайджесту", show_alert=True)
@dp.callback_query(lambda c: c.data == "settings")
async def settings_menu(callback: CallbackQuery):
    user_settings = get_user_digest_settings(callback.from_user.id)
    threshold = user_settings.get('similarity_threshold', 0.7)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Поріг схожості: {int(threshold*100)}%", callback_data="set_threshold")],
        [InlineKeyboardButton(text="🔔 Вимкнути" if user_settings['enabled'] else "🔕 Увімкнути", callback_data="toggle_digest")],
        [
            InlineKeyboardButton(text="⏰ 1 година", callback_data="set_interval_1"),
            InlineKeyboardButton(text="⏰ 2 години", callback_data="set_interval_2"),
            InlineKeyboardButton(text="⏰ 3 години", callback_data="set_interval_3")
        ],
        [
            InlineKeyboardButton(text="⏰ 6 годин", callback_data="set_interval_6"),
            InlineKeyboardButton(text="⏰ 12 годин", callback_data="set_interval_12"),
            InlineKeyboardButton(text="⏰ 24 години", callback_data="set_interval_24")
        ],
        [InlineKeyboardButton(
            text="📑 Вибір категорій",
            callback_data="select_digest_categories"
        )],
        [InlineKeyboardButton(text="📎 Медіа як файли" if user_settings['media_as_file'] else "🖼 Медіа як фото/відео",
            callback_data="toggle_media_type"
        )],
        [InlineKeyboardButton(text="🗑 Очистити історію", callback_data="clear_history")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
    ])
    interval_hours = user_settings.get('interval_hours', 1)
    text = (
        f"⚙️ Налаштування\n\n"
        f"Поточний поріг схожості новин: *{int(threshold*100)}%*\n"
        f"Поточний інтервал розсилки: *{interval_hours} год*\n"
        "Ви можете змінити ці параметри для фільтрації та частоти розсилки новин."
    )
    try:
        if callback.message:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception as e:
        # Якщо не вдалося відредагувати — просто надсилаємо нове меню
        await bot.send_message(
            chat_id=callback.from_user.id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

# --- Обробник для зміни інтервалу розсилки через меню ---
@dp.callback_query(lambda c: c.data and c.data.startswith("set_interval_"))
async def set_interval_callback(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("❌ Помилка: не вдалося визначити інтервал.", show_alert=True)
        return
    try:
        hours = int(callback.data.replace("set_interval_", ""))
        if 1 <= hours <= 24:
            set_user_digest_settings(callback.from_user.id, enabled=True, interval_hours=hours)
            schedule_user_digest(scheduler, callback.from_user.id, hours)
            await callback.answer(f"Інтервал розсилки встановлено: кожні {hours} годин.")
            await settings_menu(callback)
        else:
            await callback.answer("❌ Допустимі значення — від 1h до 24h", show_alert=True)
    except Exception:
        await callback.answer("❌ Помилка при встановленні інтервалу.", show_alert=True)

@dp.callback_query(lambda c: c.data == "set_threshold")
async def set_threshold_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="60%", callback_data="threshold_0.6"),
         InlineKeyboardButton(text="70%", callback_data="threshold_0.7"),
         InlineKeyboardButton(text="80%", callback_data="threshold_0.8")]
    ])
    if callback.message:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text="Оберіть новий поріг схожості для фільтрації новин:",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data and c.data.startswith("threshold_"))
async def set_threshold_value(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("❌ Помилка: не вдалося визначити поріг.", show_alert=True)
        return
    value = float(callback.data.split("_")[1])
    set_user_digest_settings(callback.from_user.id, similarity_threshold=value)
    await callback.answer(f"Поріг схожості встановлено на {int(value*100)}%")
    await settings_menu(callback)

# Обновляем функцию для отправки медиа с учетом настроек
async def send_media_file(chat_id: int, media_path: str, caption: Optional[str] = None) -> bool:
    try:
        if not os.path.exists(media_path) or os.path.getsize(media_path) == 0:
            logging.error(f"File not found or empty: {media_path}")
            return False

        # Получаем настройки пользователя
        settings = get_user_digest_settings(chat_id)
        media_as_file = settings.get('media_as_file', False)

        with open(media_path, 'rb') as f:
            file_data = f.read()
            
        filename = os.path.basename(media_path)
        ext = os.path.splitext(filename)[1].lower()
        input_file = BufferedInputFile(file_data, filename=filename)
        
        if media_as_file:
            # Отправляем как файл
            await bot.send_document(
                chat_id=chat_id,
                document=input_file,
                caption=caption,
                parse_mode="Markdown"
            )
        else:
            # Отправляем в зависимости от типа
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=input_file,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif ext in ['.mp4', '.avi', '.mov', '.webm']:
                await bot.send_video(
                    chat_id=chat_id,
                    video=input_file,
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_document(
                    chat_id=chat_id,
                    document=input_file,
                    caption=caption,
                    parse_mode="Markdown"
                )
        return True
        
    except Exception as e:
        logging.error(f"Failed to send media {media_path}: {e}")
        return False

async def main() -> None:
    """
    Основна функція для запуску бота.
    Обробляє як вебхук, так і полінг режими.
    """
    # Налаштовуємо логування
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info("Запуск бота...")
    
    # Очищення старих постів при запуску
    cleanup_old_posts()
    
    # Запускаємо Telethon клієнт
from telethon import TelegramClient
from config import API_ID, API_HASH
import os, asyncio, logging, sys

SESSION_FILE = "user_session.session"

async def init_telethon():
    if not os.path.exists(SESSION_FILE):
        logging.error("❌ Файл сесії Telethon не знайдено!")
        print("\n⚠️ Не знайдено файл user_session.session. Спочатку виконай:\n   py auth_telethon.py\n")
        sys.exit(1)

    client = TelegramClient("user_session", API_ID, API_HASH)

    await client.connect()
    if not await client.is_user_authorized():
        logging.warning("⚠️ Сесія знайдена, але не авторизована. Виконай повторну авторизацію.")
        print("\n⚠️ Сесія не авторизована. Виконай:\n   py auth_telethon.py\n")
        sys.exit(1)
    else:
        logging.info("✅ Telethon-сесія успішно підключена.")
    return client

      # Додаємо завдання розсилки для всіх користувачів
try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id, enabled, interval_hours FROM user_settings WHERE enabled = 1")
        except Exception as e:
            # Якщо таблиці ще немає (наприклад, на чистому Render) — ініціалізуємо БД і пробуємо ще раз
            if "no such table: user_settings" in str(e):
                try:
                    from db import init_db as _init_db
                    _init_db()
                    cursor.execute("SELECT user_id, enabled, interval_hours FROM user_settings WHERE enabled = 1")
                except Exception as ee:
                    raise ee
            else:
                raise
        for user_id, enabled, interval_hours in cursor.fetchall():
            if enabled and interval_hours:
                schedule_user_digest(scheduler, user_id, interval_hours)
                logger.info(f"Налаштовано розсилку для користувача {user_id} з інтервалом {interval_hours} годин")
        conn.close()
except Exception as e:
        logger.error(f"Помилка при налаштуванні завдань розсилки: {e}")

# Функція для безпечного відправлення повідомлень
async def safe_send(chat_id: int, text: str, reply_markup=None):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Помилка при відправленні повідомлення: {e}")
        return None

# Функція для безпечного редагування повідомлень
async def safe_edit(chat_id: int, message_id: int, text: str, reply_markup=None):
    try:
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Помилка при редагуванні повідомлення: {e}")
        return None

# --- Основні callback-и ---
@dp.callback_query(lambda c: c.data == "list_channels")
async def inline_list_channels(cb: CallbackQuery):
    channels = get_channels(cb.from_user.id)
    categories = get_categories()
    keyboard_buttons = []

    if not channels:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Додати канал", callback_data="add_channel")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
        ])
        await safe_edit(cb.message.chat.id, cb.message.message_id, "🔍 У вас ще немає доданих каналів.<br><br>Натисніть <b>«Додати канал»</b>.", keyboard)
        await cb.answer()
        return

    text = "<b>📋 Ваші канали по категоріях:</b><br><br>"
    grouped = {}
    for channel, category in channels:
        grouped.setdefault(category or "Без категорії", []).append(channel)

    for category, ch_list in grouped.items():
        text += f"📑 <b>{html.escape(category)}</b>:<br>"
        for ch in ch_list:
            text += f"• @{html.escape(ch)}<br>"
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"❌ Видалити @{ch}", callback_data=f"delete_channel_{ch}"),
                InlineKeyboardButton(text=f"📋 Перемістити @{ch}", callback_data=f"move_channel_{ch}")
            ])
        text += "<br>"

    text += "<b>🗂 Категорії:</b><br>"
    for cat_id, cat_name in categories:
        text += f"• {cat_id}: {html.escape(cat_name)}<br>"
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"✏️ Змінити '{cat_name}'", callback_data=f"edit_category_{cat_id}")
        ])

    keyboard_buttons.append([InlineKeyboardButton(text="« Назад", callback_data="back_to_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    if cb.message:
        await safe_edit(cb.message.chat.id, cb.message.message_id, text, keyboard)
    else:
        await safe_send(cb.from_user.id, text, keyboard)
    await cb.answer()

# --- WEBHOOK ---
async def on_startup(bot):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Вебхук встановлено: {WEBHOOK_URL}")

async def on_shutdown(bot):
    await bot.delete_webhook()
    logger.info("🧹 Вебхук видалено.")

async def start_webhook():
    """Start the webhook server."""
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    # Health check on root for Render
    async def health(request):
        return web.Response(text="✅ VVNewsDigestBot is running", content_type="text/plain")
    app.router.add_get("/", health)
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"🚀 Вебхук-сервер запущено на порту {PORT}")
    return runner, site

async def ensure_webhook_deleted():
    """Ensure webhook is deleted before starting polling."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Вебхук успішно видалено")
            return True
        except Exception as e:
            if "terminated by other getUpdates" in str(e) and attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"⚠️ Конфлікт отримання оновлень. Чекаємо {wait_time} секунд... (спроба {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
            logger.warning(f"⚠️ Не вдалося видалити вебхук: {e}")
            return False

async def main():
    """Main application entry point."""
    global runner, site
    
    if RUN_MODE == "render":
        # Ensure scheduler is running on Render
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started")
        # Bind HTTP port ASAP to satisfy Render port scan
        runner, site = await start_webhook()
        await on_startup(bot)
        # Initialize Telethon AFTER binding the port
        if not telethon_client.is_connected():
            logger.info("🔌 Підключення до Telethon...")
            await telethon_client.start()
            logger.info("✅ Telethon клієнт підключено")
        # Keep the application running
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour
    else:
        # Start Telethon client (development/local)
        if not telethon_client.is_connected():
            logger.info("🔌 Підключення до Telethon...")
            await telethon_client.start()
            logger.info("✅ Telethon клієнт підключено")
        # Always ensure webhook is deleted in polling mode
        await ensure_webhook_deleted()
        
        # Start polling in development mode
        logger.info("🏃‍♂️ Запуск в режимі polling...")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
                break  # If polling starts successfully, exit the retry loop
            except Exception as e:
                if "terminated by other getUpdates" in str(e) and attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)  # Exponential backoff
                    logger.warning(f"⚠️ Конфлікт отримання оновлень. Чекаємо {wait_time} секунд... (спроба {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"❌ Помилка при запуску polling: {e}")
                if attempt == max_retries - 1:  # If this was the last attempt
                    logger.error("❌ Перевищено максимальну кількість спроб. Перевірте, чи не запущено інший екземпляр бота.")
                    logger.error("ℹ️ Спробуйте виконати команду: taskkill /F /IM python.exe")
                raise

async def shutdown():
    """Shutdown the application gracefully."""
    print("\n🛑 Завершення роботи бота...")
    
    # Stop the scheduler if it's running
    if 'scheduler' in globals() and scheduler.running:
        scheduler.shutdown()
        print("✅ Планувальник успішно зупинено")
    
    # Close database connection if it exists
    if 'conn' in globals():
        conn.close()
        print("✅ З'єднання з базою даних закрито")
    
    # Close bot session if it exists
    if 'bot' in globals() and hasattr(bot, 'session') and bot.session:
        await bot.session.close()
        print("✅ Сесія бота закрита")
    
    # Disconnect Telethon client if it exists
    if 'telethon_client' in globals() and telethon_client:
        await telethon_client.disconnect()
        print("✅ Telethon клієнт відключений")
    
    # Clean up web server if it exists
    if 'runner' in globals() and 'site' in globals():
        await site.stop()
        await runner.cleanup()
        print("✅ Веб-сервер зупинено")
    
    print("✅ Роботу бота завершено")

async def run_bot():
    """Run the bot with proper error handling."""
    try:
        await main()
    except KeyboardInterrupt:
        print("\n🛑 Бот зупинено вручну")
    except Exception as e:
        print(f"❌ Помилка: {e}")
    finally:
        await shutdown()
        
# === KEEP-ALIVE СЕРВЕР ДЛЯ RENDER ===
import os
import asyncio
import logging
from aiohttp import web

# [1] Проста функція, щоб перевірити, що бот "живий"
async def handle(request):
    return web.Response(text="✅ VVNewsDigestBot is running", content_type="text/plain")

# [2] Асинхронна функція запуску keep-alive сервера
async def start_keep_alive_server():
    """Keep-alive сервер для Render, щоб уникнути засинання сервісу"""
    try:
        # На Render потрібно слухати саме $PORT, який надає платформа
        PORT = int(os.getenv("PORT", 10000))

        app = web.Application()
        app.router.add_get("/", handle)
        app.router.add_get("/healthz", handle)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
        await site.start()

        logging.info(f"🌍 Keep-alive сервер запущено на порту {PORT}")

        # Нескінченний цикл для тримання сервера активним
        while True:
            await asyncio.sleep(3600)

    except OSError as e:
        logging.warning(f"⚠️ Порт зайнятий або недоступний: {e}")
    except Exception as e:
        logging.error(f"❌ Помилка запуску keep-alive сервера: {e}")

# [3] Якщо бот працює на Render — запускаємо keep-alive у фоновому потоці
if __name__ == "__main__":
    pass

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def main():
    if str(RUN_MODE).lower() == "render":
        logging.info("🚀 VVNewsDigestBot запущено у режимі: RENDER")

        if not scheduler.running:
            scheduler.start()

        runner, site = await start_webhook()
        await on_startup(bot)

        if not telethon_client.is_connected():
            logging.info("🔌 Підключення до Telethon...")
            await telethon_client.start()
            logging.info("✅ Telethon клієнт підключено")

        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await site.stop()
            await runner.cleanup()
    else:
        logging.info("🚀 VVNewsDigestBot запущено у режимі: LOCAL")

        if not scheduler.running:
            scheduler.start()

        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("🛑 Бот зупинено вручну.")

import atexit

@atexit.register
def cleanup():
    try:
        if telethon_client.is_connected():
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(telethon_client.disconnect())
            finally:
                loop.close()
            print("🔌 Telethon client disconnected cleanly.")
    except Exception as e:
        logging.debug(f"Cleanup skipped: {e}")

