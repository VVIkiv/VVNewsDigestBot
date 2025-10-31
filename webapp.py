import os
import logging
from flask import Flask, render_template_string, send_from_directory
from datetime import datetime

app = Flask(__name__)

# === HTML-шаблон сторінки (з автооновленням) ===
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="300"> <!-- ⏱ автооновлення кожні 5 хв -->
    <title>🗞 VVNewsDigestBot — {{ date }}</title>
    <style>
        body {
            font-family: "Segoe UI", Arial;
            background: #f5f7fa;
            margin: 0;
            padding: 20px;
        }
        h1 {
            color: #222;
        }
        .container {
            max-width: 900px;
            margin: auto;
        }
        .card {
            background: #fff;
            margin: 15px 0;
            padding: 15px 20px;
            border-radius: 12px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        }
        .card h3 {
            margin: 0 0 10px;
        }
        a {
            color: #0077cc;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        footer {
            margin-top: 20px;
            text-align: center;
            color: #777;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📰 VVNewsDigestBot — {{ date }}</h1>

        {% if news %}
            {% for item in news %}
                <div class="card">
                    <h3>{{ item.date.strftime('%d.%m %H:%M') }}</h3>
                    <p>{{ item.text[:500] }}...</p>
                    {% if item.url %}
                        <p><a href="{{ item.url }}" target="_blank">🔗 Переглянути пост</a></p>
                    {% endif %}
                </div>
            {% endfor %}
        {% else %}
            <p>😔 Дайджест поки що порожній.</p>
        {% endif %}

        <footer>⚙️ Згенеровано VVNewsDigestBot • {{ date }}</footer>
    </div>
</body>
</html>
"""

# === Функція для отримання шляху до файлу дайджесту ===
def find_latest_digest():
    """Шукає найновіший HTML-файл у поточній директорії."""
    files = [f for f in os.listdir(".") if f.endswith(".html") and "digest" in f]
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    return latest


@app.route("/digest")
def show_digest():
    """Показує останній збережений дайджест"""
    try:
        digest_file = find_latest_digest()
        if digest_file:
            logging.info(f"✅ Відображаємо файл дайджесту: {digest_file}")
            return send_from_directory(".", digest_file)
        else:
            logging.warning("⚠️ Файл дайджесту не знайдено, показуємо заглушку")
            return render_template_string(
                HTML_TEMPLATE, news=[], date=datetime.now().strftime("%d.%m.%Y %H:%M")
            )
    except Exception as e:
        logging.error(f"❌ Помилка відображення дайджесту: {e}")
        return "❌ Помилка при завантаженні сторінки."


@app.route("/")
def index():
    """Проста головна сторінка"""
    return "<h2>✅ VVNewsDigestBot працює. Відкрий <a href='/digest'>/digest</a> щоб побачити дайджест.</h2>"


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
