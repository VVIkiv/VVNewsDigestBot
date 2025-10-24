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

# 1. Очищення папки media

def cleanup_media_folder(folder_path="media", max_age_hours=24):
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
# 2. Імпорти, ініціалізація, логування

from aiogram import Bot, Dispatcher, types
from aiogram.types import (Message, InputMediaPhoto, InputMediaVideo, 
                         InlineKeyboardButton, InlineKeyboardMarkup,
                         CallbackQuery)
from aiogram.filters import Command
import sqlite3
import asyncio
import re
import os
import io
import hashlib
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from aiogram.types.input_file import BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import BOT_TOKEN
from db import (
    add_channel,
    delete_channel,
    get_channels,              # нова назва замість get_user_channels
    get_categories,
    add_category,
    delete_category,
    update_channel_category,
    update_category_name,
    get_user_digest_settings,
    set_user_digest_settings,
    add_sent_post,
    is_post_sent,
    cleanup_old_posts,
    init_db                    # цього достатньо, update_db_structure більше не потрібна
)

# === ІНІЦІАЛІЗАЦІЯ БАЗИ ТА ПЕРЕВІРКА ===
print("🗃️ Ініціалізація бази даних...")
try:
    init_db()
    from db import get_categories, get_channels

    categories = get_categories()
    total_categories = len(categories)
    print(f"✅ База даних готова. Категорій: {total_categories}")

    # Опціонально: підрахунок загальної кількості каналів
    import sqlite3
    from db import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM channels")
    total_channels = cursor.fetchone()[0]
    conn.close()

    print(f"📡 У базі збережено каналів: {total_channels}")

except Exception as e:
    print(f"❌ Помилка ініціалізації бази: {e}")


# --- Ініціалізація бази при старті ---
print("🗃️ Ініціалізація бази даних...")
init_db()
print("✅ База даних готова до роботи.")
# --- Ініціалізація бази при старті ---
print("🗃️ Ініціалізація бази даних...")
init_db()
print("✅ База даних готова до роботи.")
from telethon_client import get_recent_posts, client as telethon_client
from summarizer import summarize

import sys
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# Настройка логирования
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
# 3. Допоміжні функції (escape_markdown, escape_markdown_v2, create_post_hash, is_similar_news тощо)

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

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

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# 4. Обробники команд (start, help, addchannel, listchannels, deletechannel, addcategory, delcategory)

@dp.message(Command("start"))
async def start_handler(message: Message):
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
    await message.answer(
        "Привіт! Я бот, який збиратиме новини з каналів і стискатиме їх до суті.",
        reply_markup=keyboard
    )

# Добавим обработчик для кнопки "Допомога"
@dp.callback_query(lambda c: c.data == "help")
async def inline_help(callback: types.CallbackQuery):
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
async def add_channel_handler(message: Message):
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

@dp.message(Command("deletechannel"))
async def delete_channel_handler(message: Message):
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

def create_post_hash(text: str, channel: str, date: Optional[datetime] = None, media: Optional[str] = None) -> str:
    """Создает уникальный хеш поста"""
    # Очищаем текст от пробелов и служебных символов
    clean_text = re.sub(r'\s+', ' ', text.strip()) if text else ''
    clean_text = re.sub(r'http\S+', '', clean_text)  # Удаляем ссылки
    
    # Формируем список частей для хеширования
    hash_parts = []
    hash_parts.append(channel)
    hash_parts.append(clean_text[:200])  # Берем первые 200 символов текста
    hash_parts.append(str(date.timestamp()) if date else '')  # Добавляем дату публикации
    
    # Добавляем информацию о медиафайле
    if media:
        try:
            file_size = os.path.getsize(media)
            hash_parts.append(f"{os.path.basename(media)}:{file_size}")
        except Exception as e:
            logging.error(f"Ошибка при получении размера файла {media}: {e}")
            
    # Соединяем все части
    content = "|".join(str(part) for part in hash_parts)
    return hashlib.md5(content.encode()).hexdigest()

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
 
        # Получаем посты из каналов
        fetch_tasks = [get_recent_posts(channel, limit=5) for channel in cleaned_channels]
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
            # Проверяем есть ли текст в посте
            if not post['text']:
                continue
                
            # Создаем хеш поста для проверки дубликатов
            post_hash = hashlib.md5(post['text'].encode()).hexdigest()
            
            # Пропускаем дубликаты
            if post_hash in seen_hashes:
                continue
                
            seen_hashes.add(post_hash)
            
            # Проверяем, был ли пост уже отправлен ранее
            if not is_post_sent(user_id, post_hash):
                processed_posts.append(post)
                new_posts_count += 1
                add_sent_post(user_id, post_hash)
                
                # Ограничиваем количество постов в дайджесте
                if new_posts_count >= 20:  #/// максимум 10-20 постів в одному дайджесте///
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
        for post in processed_posts:
            is_duplicate = False
            for f_post in filtered_posts:
                if is_similar_news(post['text'], f_post['text'], threshold=user_threshold):
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered_posts.append(post)

        for post in filtered_posts:
            try:
                # Подготавливаем текст поста
                shortened_text = post['text'][:200] + ('...' if len(post['text']) > 200 else '')
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
        time_diff = next_digest - now
        hours_diff = int(time_diff.total_seconds() / 3600)
        minutes_diff = int((time_diff.total_seconds() % 3600) / 60)
        
        time_text = f"{hours_diff} год"
        if minutes_diff > 0:
            time_text += f" {minutes_diff} хв"
            
        await bot.send_message(
            chat_id=user_id,
            text=f"✅ Дайджест завершено!\nНаступний дайджест буде відправлено о {next_digest.strftime('%H:%M')} (через {time_text})"
        )

    except Exception as e:
        logging.error(f"Помилка при відправці дайджесту: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=user_id,
            text="❌ Виникла помилка при формуванні дайджесту. Спробуйте пізніше."
        )


@dp.message(Command("digest"))
async def digest_handler(message: Message):
    if message.from_user:
        await send_digest_to_user(message.from_user.id)

async def send_digest_to_all_users():
    """Отправка дайджеста всем пользователям с учетом выбранных категорий"""
    conn = sqlite3.connect("channels.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, selected_categories 
        FROM user_settings 
        WHERE enabled = 1
    """)
    users = cursor.fetchall()
    conn.close()

    for user_id, selected_categories in users:
        try:
            if selected_categories:
                # Преобразуем строку в список ID категорий
                categories = [int(x) for x in selected_categories.split(',')]
                for category_id in categories:
                    await send_digest_to_user(user_id, category_id=category_id)
            else:
                # Если категории не выбраны - отправляем полный дайджест
                await send_digest_to_user(user_id)
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
        send_digest_to_user,
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
async def setdigest_handler(message: Message):
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
async def select_digest_categories(callback: types.CallbackQuery):
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
async def toggle_digest_category(callback: types.CallbackQuery):
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
async def inline_list_channels(cb: types.CallbackQuery):
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
async def back_to_main(callback: types.CallbackQuery):
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
async def inline_add_channel(callback: types.CallbackQuery):
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
async def delete_channel_button(callback: types.CallbackQuery):
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
async def category_selected(callback: types.CallbackQuery):
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
async def inline_digest(callback: types.CallbackQuery):
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
async def digest_all(callback: types.CallbackQuery):
    """Отправка полного дайджеста"""
    await callback.answer("⏳ Збираю дайджест...", show_alert=True)
    await send_digest_to_user(callback.from_user.id)

@dp.callback_query(lambda c: c.data and c.data.startswith("digest_category_"))
async def digest_category(callback: types.CallbackQuery):
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
async def settings_menu(callback: types.CallbackQuery):
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
async def set_interval_callback(callback: types.CallbackQuery):
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
async def set_threshold_menu(callback: types.CallbackQuery):
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
async def set_threshold_value(callback: types.CallbackQuery):
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
    # Настраиваем логирование
    setup_logging()
    logging.info("Запуск бота...")
    
    # Очищення старих постів
    cleanup_old_posts()
    
    # Запускаем Telethon клиент
    try:
        await telethon_client.connect()
        if not await telethon_client.is_user_authorized():
            logging.error("Telethon не авторизован!")
            return
        me = await telethon_client.get_me()
        logging.info(f"Telethon успішно авторизований як {getattr(me, 'username', None) or getattr(me, 'first_name', None) or getattr(me, 'user_id', None)}")
    except Exception as e:
        logging.error(f"Помилка при запуску Telethon: {e}")
        return
    # 9. Планувальник, очищення історії, медіа

    # --- Додаємо запуск задач розсилки для всіх користувачів ---
    conn = sqlite3.connect("channels.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, enabled, interval_hours FROM user_settings WHERE enabled = 1")
    for user_id, enabled, interval_hours in cursor.fetchall():
        if enabled and interval_hours:
            schedule_user_digest(scheduler, user_id, interval_hours)
    conn.close()
    # Настраиваем планировщик
    # scheduler.add_job(
    #     send_digest_to_all_users,
    #     trigger='cron',
    #     hour='*',
    #     minute=0,
    #     id='hourly_digest'
    # )
    
    try:
        # Запускаем планировщик
        scheduler.start()

        # Запускаем бота
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Помилка при запуску бота: {e}")
    finally:
        await bot.session.close()
        telethon_client.disconnect()

# === KEEP-ALIVE ДЛЯ RENDER ===
import threading
import http.server
import socketserver
import os

def start_keep_alive_server():
    """Запускає простий HTTP-сервер, щоб Render бачив відкритий порт."""
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"🌍 Фіктивний сервер запущено на порту {port}")
        httpd.serve_forever()

# Запускаємо сервер у фоновому потоці
threading.Thread(target=start_keep_alive_server, daemon=True).start()


if __name__ == "__main__":
    import asyncio
    try:
        import sys
        if sys.version_info >= (3, 7):
            asyncio.run(main())
        else:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")
    except Exception as e:
        logging.error(f"Критична помилка: {e}", exc_info=True)

from telethon_client import client, download_media  # Add this import at the top of your file or before this function

async def get_recent_posts(channel: str, limit: int = 5) -> List[Dict]:
    channel_name = None
    try:
        if not channel or len(channel) <= 1:
            logging.error(f"Некорректное имя канала: {channel}")
            return []
            
        clean_channel = channel.lstrip('@')
        channel_name = f"@{clean_channel}"
        
        logging.info(f"Получаем посты из канала: {channel_name}")
        
        messages = []
        logging.info(f"Начинаем получение сообщений из канала {channel_name}")
        
        async for message in client.iter_messages(channel_name, limit=limit):
            logging.info(f"Получено сообщение из канала {channel_name}: {message.id}")
            if not message:
                continue

            # Пропускаем служебные сообщения
            if hasattr(message, 'action'):
                continue

            post_url = f"https://t.me/{clean_channel}/{message.id}"

            # Получаем текст сообщения
            text = ""
            if hasattr(message, 'message'):  # Сначала проверяем атрибут message
                text = message.message
            elif hasattr(message, 'text'):   # Затем проверяем text
                text = message.text
            elif hasattr(message, 'raw_text'): # И наконец raw_text
                text = message.raw_text
            
            text = text or ''  # Если все атрибуты отсутствуют, используем пустую строку

            # Обрабатываем медиафайлы
            media_path = None
            if hasattr(message, 'media') and message.media:
                try:
                    media_path = await download_media(message)
                except Exception as e:
                    logging.error(f"Ошибка загрузки медиа из {channel_name}: {e}")

            if not text and not media_path:
                continue

            messages.append({
                "text": text,
                "media": media_path,
                "url": post_url,
                "date": message.date
            })
            
        logging.info(f"Получено {len(messages)} постов из канала {channel_name}")
        return messages
            
    except Exception as e:
        logging.error(f"Ошибка получения сообщений из {channel_name}: {e}")
        return []

def is_post_sent(user_id: int, post_hash: str) -> bool:
    """Проверяет, был ли пост уже отправлен пользователю"""
    conn = sqlite3.connect("channels.db")
    cursor = conn.cursor()
    
    # Добавьте логирование
    logging.info(f"Проверяем отправку поста {post_hash} пользователю {user_id}")
    
    cursor.execute(
        "SELECT COUNT(*) FROM sent_posts WHERE user_id = ? AND post_hash = ?",
        (user_id, post_hash)
    )
    count = cursor.fetchone()[0]
    conn.close()
    
    # Логируем результат
    if count > 0:
        logging.info(f"Пост {post_hash} уже был отправлен пользователю {user_id}")
    
    return count > 0

def cleanup_sent_posts():
    """Удаляет старые записи из таблицы sent_posts"""
    conn = sqlite3.connect("channels.db")
    cursor = conn.cursor()
    
    # Удаляем записи старше 2 дней
    cursor.execute("DELETE FROM sent_posts WHERE timestamp < datetime('now', '-2 days')")
    conn.commit()
    conn.close()
    
    logging.info("Очистка старых записей в sent_posts завершена")

# Планувальник для очищення старих записів і медіа
scheduler = AsyncIOScheduler()
scheduler.add_job(
    cleanup_sent_posts,
    trigger='interval',
    days=1,  # Запускати раз на добу
    misfire_grace_time=15
)
scheduler.add_job(
    cleanup_media_folder,
    trigger='interval',
    days=1,  # Запускати раз на добу
    misfire_grace_time=15
)
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

@dp.callback_query(lambda c: c.data == "edit_category_name")
async def edit_category_name_menu(callback: types.CallbackQuery):
    categories = get_categories()
    keyboard_buttons = []
    for cat_id, cat_name in categories:
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"✏️ {cat_name}", callback_data=f"edit_category_{cat_id}")
        ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="« Назад", callback_data="settings")
    ])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    text = "*Виберіть категорію для зміни назви:*"
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
    await callback.answer()

class CategoryEdit(StatesGroup):
    waiting_for_new_name = State()

@dp.callback_query(lambda c: c.data and c.data.startswith("edit_category_"))
async def ask_new_category_name(callback: types.CallbackQuery, state: FSMContext):
    if not callback.data:
        await callback.answer("❌ Не вдалося визначити категорію.", show_alert=True)
        return
    try:
        category_id = int(callback.data.replace("edit_category_", ""))
    except Exception:
        await callback.answer("❌ Некоректний ID категорії.", show_alert=True)
        return
    await state.set_state(CategoryEdit.waiting_for_new_name)
    await state.update_data(category_id=category_id)
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=f"Введіть нову назву для категорії (id={category_id}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="edit_category_name")]
        ])
    )
    await callback.answer()

@dp.message(CategoryEdit.waiting_for_new_name)
async def handle_new_category_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Назва не може бути порожньою.")
        return
    data = await state.get_data()
    category_id = data.get("category_id")
    new_name = message.text.strip() if message.text else None
    if not new_name:
        await message.answer("❌ Назва не може бути порожньою.")
        return
    if not category_id:
        await message.answer("❌ Не вдалося визначити категорію.")
        await state.clear()
        return
    success = update_category_name(category_id, new_name)
    if success:
        await message.answer(f"✅ Назву категорії змінено на: {new_name}")
    else:
        await message.answer("❌ Не вдалося змінити назву категорії.")
    await state.clear()

@dp.message(Command("addcategory"))
async def add_category_handler(message: Message):
    if not message.text:
        await message.answer("❌ Формат: /addcategory Назва_категорії")
        return
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await message.answer("❌ Формат: /addcategory Назва_категорії")
        return
    name = args[1].strip()
    if not name:
        await message.answer("❌ Назва категорії не може бути порожньою.")
        return
    success = add_category(name)
    if success:
        await message.answer(f"✅ Категорію '{name}' додано!")
    else:
        await message.answer(f"❌ Не вдалося додати категорію. Можливо, така вже існує.")

@dp.message(Command("delcategory"))
async def delete_category_handler(message: Message):
    if not message.text:
        await message.answer("❌ Формат: /delcategory id_категорії")
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("❌ Формат: /delcategory id_категорії")
        return
    category_id = int(args[1])
    success = delete_category(category_id)
    if success:
        await message.answer(f"✅ Категорію з id={category_id} видалено!")
    else:
        await message.answer(f"❌ Не вдалося видалити категорію. Перевірте id.")

import threading, http.server, socketserver

