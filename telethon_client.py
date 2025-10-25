from telethon import TelegramClient
from telethon.tl.types import User, Chat, Channel
from config import API_ID, API_HASH
import os
import logging
from typing import List, Dict, Union, Optional

async def main():
    # старт telethon client, якщо потрібно
    if not client.is_connected():
        await client.start()
    # ... scheduler.start(), dp.start_polling() ...


import os
print("📁 Поточна директорія:", os.getcwd())
print("📄 Файли тут:", os.listdir())

# Авторизація а телетон
client = TelegramClient('bot_session', API_ID, API_HASH)
#client = TelegramClient('anon', API_ID, API_HASH)


EntityType = Union[User, Chat, Channel]

async def download_media(message):
    try:
        if message.media:
            filename = f"media/{message.id}_{message.date.timestamp()}"
            logging.info(f"Начинаю загрузку медиа для сообщения {message.id}")
            logging.info(f"Тип медиа: {type(message.media).__name__}")
            
            path = await message.download_media(filename)
            
            if path:
                logging.info(f"Медиа успешно загружено в: {path}")
                return path
            else:
                logging.error(f"Не удалось загрузить медиа: путь пустой")
                return None
    except Exception as e:
        logging.error(f"Ошибка загрузки медиа для сообщения {message.id}: {str(e)}")
        return None

async def get_recent_posts(channel: str, limit: int = 5) -> List[Dict]:
    try:
        # Проверяем существование канала
        try:
            channel_entity = await client.get_entity(channel)
            if isinstance(channel_entity, (Chat, Channel)):
                logging.info(f"Канал {channel} найден: {channel_entity.id}")
            else:
                logging.error(f"Сущность {channel} не является каналом")
                return []
        except Exception as e:
            logging.error(f"Канал {channel} не найден: {str(e)}")
            return []

        messages = []
        logging.info(f"Начинаю получение сообщений из канала {channel}, лимит: {limit}")
        
        async for message in client.iter_messages(channel_entity, limit=limit):
            if not message:
                logging.warning(f"Пустое сообщение из канала {channel}")
                continue
                
            logging.info(f"Обработка сообщения {message.id} из канала {channel}")
            
            # Получаем ссылку на пост
            post_url = f"https://t.me/{channel}/{message.id}"
            logging.info(f"URL поста: {post_url}")
            
            # Получаем текст сообщения
            text = message.text or message.raw_text or ""
            logging.info(f"Текст сообщения: {text[:100]}...")  # Логируем первые 100 символов
            
            # Обрабатываем медиафайлы
            media_path = None
            if message.media:
                logging.info(f"Найдено медиа в сообщении {message.id}, тип: {type(message.media).__name__}")
                try:
                    media_path = await download_media(message)
                    logging.info(f"Медиа успешно загружено: {media_path}")
                except Exception as e:
                    logging.error(f"Ошибка загрузки медиа из {channel}, сообщение {message.id}: {e}")
            
            post_data = {
                "text": text,
                "media": media_path,
                "url": post_url,
                "date": message.date
            }
            logging.info(f"Добавляю пост {message.id} в список")
            messages.append(post_data)
            
        logging.info(f"Всего получено {len(messages)} сообщений из канала {channel}")
        return messages
    except Exception as e:
        logging.error(f"Ошибка получения сообщений из канала {channel}: {e}", exc_info=True)
        return []


