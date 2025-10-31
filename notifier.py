import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from jinja2 import Template
import logging

# === 1️⃣ Надсилання дайджесту на email ===
def send_email_digest(subject: str, news_items: list, to_email: str):
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 465
        sender_email = os.getenv("EMAIL_USER")
        sender_pass = os.getenv("EMAIL_PASS")

        if not sender_email or not sender_pass:
            logging.error("❌ Відсутні EMAIL_USER або EMAIL_PASS у .env файлі")
            return

        # Формуємо HTML лист
        html_template = """
        <html>
        <head><meta charset="utf-8"><style>
            body { font-family: Arial; background: #f5f5f5; padding: 20px; }
            h2 { color: #333; }
            .news-item { background: white; padding: 10px 15px; margin-bottom: 10px; border-radius: 8px; }
            a { color: #0066cc; text-decoration: none; }
        </style></head>
        <body>
        <h2>🗞 Щоденний дайджест новин</h2>
        {% for item in news %}
            <div class="news-item">
                <p><b>{{ item.date.strftime('%d.%m %H:%M') }}</b></p>
                <p>{{ item.text[:400] }}...</p>
                {% if item.url %}<p><a href="{{ item.url }}">📎 Перейти до джерела</a></p>{% endif %}
            </div>
        {% endfor %}
        <p>⚙️ VVNewsDigestBot | {{ date }}</p>
        </body></html>
        """

        html_body = Template(html_template).render(news=news_items, date=datetime.now())

        msg = MIMEText(html_body, "html")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_email

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_pass)
            server.send_message(msg)
            logging.info(f"✅ Дайджест успішно відправлено на {to_email}")

    except Exception as e:
        logging.error(f"❌ Помилка відправки email: {e}")

# === 2️⃣ Збереження дайджесту у вигляді HTML-файлу ===
def save_html_digest(news_items: list, output_path="daily_digest.html"):
    try:
        html_template = """
        <html><head><meta charset="utf-8"><title>VVNewsDigestBot</title>
        <style>
        body { font-family: Arial; background: #fafafa; padding: 20px; }
        h1 { color: #222; }
        .card { background: #fff; margin: 10px 0; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        a { color: #0b66c3; }
        </style></head><body>
        <h1>🗞 VVNewsDigestBot — {{ date }}</h1>
        {% for item in news %}
            <div class="card">
                <h3>{{ item.date.strftime('%H:%M %d.%m') }}</h3>
                <p>{{ item.text[:500] }}...</p>
                {% if item.url %}<p><a href="{{ item.url }}">🔗 Переглянути пост</a></p>{% endif %}
            </div>
        {% endfor %}
        <p>📦 Згенеровано автоматично о {{ date }}</p>
        </body></html>
        """
        html_content = Template(html_template).render(news=news_items, date=datetime.now())
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logging.info(f"✅ HTML-документ створено: {output_path}")
    except Exception as e:
        logging.error(f"❌ Помилка при збереженні HTML дайджесту: {e}")
