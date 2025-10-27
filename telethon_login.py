from telethon import TelegramClient

API_ID = 25311370
API_HASH = 'ae3e5211df263c6fc43b1ac8a8f1157f'

client = TelegramClient("anon", API_ID, API_HASH)
client.start()
print("✅ Авторизація завершена. Створено anon.session")
