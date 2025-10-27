# File: telethon_reader.py
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command

from config import BOT_TOKEN
from db import add_channel, get_user_channels
from telethon_client import get_recent_posts
from summarizer import summarize

import asyncio
# from db import remove_channel  # Removed because it does not exist in db.py

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Команда /start
@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привіт! Я бот, який збиратиме новини з каналів і стискатиме їх до суті.")

# Команда /help
@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "Команди:\n"
        "/start — початок\n"
        "/help — допомога\n"
        "/addchannel @назва — додати канал\n"
        "/listchannels — список каналів\n"
        "/digest — отримати дайджест"
    )

# Команда /listchannels
@dp.message(Command("listchannels"))
async def list_channels_handler(message: Message):
    if not message.from_user or not hasattr(message.from_user, "id"):
        await message.answer("❌ Не вдалося отримати список каналів. Спробуйте ще раз.")
        return
    channels = get_user_channels(message.from_user.id)
    if not channels:
        await message.answer("🔍 Ви ще не додали жодного каналу.")
    else:
        text = "📋 Ваші канали:\n" + "\n".join(f"- @{ch}" for ch in channels)
        await message.answer(text)

def remove_channel(user_id, channel):
    raise NotImplementedError

# Команда /removechannel
@dp.message(Command("removechannel"))
async def remove_channel_handler(message: Message):
    if not message.text or not message.from_user or not hasattr(message.from_user, "id"):
        await message.answer("❌ Не вдалося обробити команду. Спробуйте ще раз.")
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].startswith("@"):
        await message.answer("❌ Формат: /removechannel @назва_каналу")
        return
    channel = args[1].lstrip("@")
    # Видалення каналу для користувача
    removed = remove_channel(message.from_user.id, channel)
    if removed:
        await message.answer(f"✅ Канал @{channel} видалено!")
    else:
        await message.answer(f"❌ Канал @{channel} не знайдено у вашому списку.")

# Команда /addchannel
@dp.message(Command("addchannel"))
async def add_channel_handler(message: Message):
    if not message.text or not message.from_user or not hasattr(message.from_user, "id"):
        await message.answer("❌ Не вдалося обробити команду. Спробуйте ще раз.")
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].startswith("@"):
        await message.answer("❌ Формат: /addchannel @назва_каналу")
        return
    channel = args[1].lstrip("@")  # зберігаємо без @
    add_channel(message.from_user.id, channel)
    await message.answer(f"✅ Канал @{channel} додано!")

# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

# Команда /digest
@dp.message(Command("digest"))
async def digest_handler(message: Message):
    if not message.from_user or not hasattr(message.from_user, "id"):
        await message.answer("❌ Не вдалося отримати дайджест. Спробуйте ще раз.")
        return
    channels = get_user_channels(message.from_user.id)
    if not channels:
        await message.answer("❗ Ви ще не додали жодного каналу.")
        return

    digest_text = "📰 *Ваш дайджест новин:*\n\n"
    for channel in channels:
        # If channel is a tuple (e.g., (id, name)), extract the name
        channel_name = channel[1] if isinstance(channel, tuple) and len(channel) > 1 else channel
        try:
            posts = await get_recent_posts(channel_name, limit=2)
            if posts is None:
                digest_text += f"⚠️ Не вдалося отримати пости з каналу @{channel_name}.\n\n"
                continue
            if isinstance(posts, Exception):
                digest_text += f"⚠️ Помилка з каналом @{channel_name}: {posts}\n\n"
                continue
            for post in posts:
                post_text = post.get("text", "") if isinstance(post, dict) else str(post)
                short = summarize(post_text)
                digest_text += f"📌 _@{channel_name}_:\n{short}\n\n"
        except Exception as e:
            digest_text += f"⚠️ Помилка з каналом @{channel_name}: {e}\n\n"
    await message.answer(digest_text, parse_mode="Markdown")
