📦 Telegram Bot Deployment (Render.com)
git add render.yaml
git commit -m "fix start command"
git push

1️⃣ Створи новий репозиторій на GitHub і завантаж усі файли.
2️⃣ Перейди на https://render.com → New → Web Service → вибери репозиторій.
3️⃣ У полі Environment вибери Python 3.
4️⃣ У полі Build Command:
    pip install -r requirements.txt
5️⃣ У полі Start Command:
    python bot.py
6️⃣ Додай змінні середовища:
    BOT_TOKEN = <токен від BotFather>
    API_ID    = <твій API_ID із my.telegram.org>
    API_HASH  = <твій API_HASH із my.telegram.org>
7️⃣ Натисни Deploy і зачекай, поки бот запуститься.
8️⃣ У логах Render побачиш:
    "Запуск бота..." і "Bot polling started..."
