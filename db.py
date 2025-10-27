import os
import sqlite3
import logging
from typing import Optional

# === Конфігурація бази даних ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "channels.db")


# === Допоміжні функції ===
def get_connection():
    # check_same_thread=False дозволяє доступ з різних thread (безпечніше для scheduler)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# === Ініціалізація бази ===
def init_db():
    """Створює всі таблиці, якщо їх немає."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            user_id INTEGER,
            channel_name TEXT,
            category_id INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, channel_name),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            enabled BOOLEAN DEFAULT 0,
            interval_hours INTEGER DEFAULT 2,
            last_digest_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            media_as_file BOOLEAN DEFAULT 0,
            selected_categories TEXT DEFAULT NULL,
            similarity_threshold REAL DEFAULT 0.7
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_posts (
            user_id INTEGER,
            post_hash TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, post_hash)
        )
    """)

    # Додаємо базові категорії
    categories = [
        ("📰 Новини",),
        ("🎨 Хобі",),
        ("❤️ Здоров'я",),
        ("🛍️ Шопінг",),
        ("🔄 Інше",)
    ]
    for category in categories:
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", category)

    conn.commit()
    conn.close()


# === 1. Робота з каналами ===
def add_channel(user_id: int, channel: str, category_id: int = 1):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO channels (user_id, channel_name, category_id)
            VALUES (?, ?, ?)
        """, (user_id, channel.strip(), category_id))
        conn.commit()
    finally:
        conn.close()


def delete_channel(user_id: int, channel: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM channels WHERE user_id = ? AND channel_name = ?",
            (user_id, channel.strip())
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"Error deleting channel: {e}")
        return False
    finally:
        conn.close()


def get_channels(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT ch.channel_name, cat.name 
            FROM channels ch
            LEFT JOIN categories cat ON ch.category_id = cat.id
            WHERE ch.user_id = ?
            ORDER BY cat.name, ch.channel_name
        """, (user_id,))
        return [(channel.strip(), category) for channel, category in cursor.fetchall()]
    finally:
        conn.close()


def get_channels_by_category(user_id: int, category_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT channel_name FROM channels
            WHERE user_id = ? AND category_id = ?
            ORDER BY channel_name
        """, (user_id, category_id))
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def update_channel_category(user_id: int, channel: str, new_category_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE channels SET category_id = ?
            WHERE user_id = ? AND channel_name = ?
        """, (new_category_id, user_id, channel.strip()))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logging.error(f"SQL error updating category: {e}")
        return False
    finally:
        conn.close()


# === 2. Робота з категоріями ===
def get_categories():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories ORDER BY id")
    categories = cursor.fetchall()
    conn.close()
    return categories


def add_category(name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_category(category_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM channels WHERE category_id = ?", (category_id,))
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def update_category_name(category_id: int, new_name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, category_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# === 3. Налаштування користувача ===
def set_user_digest_settings(user_id: int, enabled: Optional[bool] = None,
                             interval_hours: Optional[int] = None,
                             media_as_file: Optional[bool] = None,
                             selected_categories: Optional[list] = None,
                             similarity_threshold: Optional[float] = None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        updates = []
        params = []

        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)
        if interval_hours is not None:
            updates.append("interval_hours = ?")
            params.append(interval_hours)
        if media_as_file is not None:
            updates.append("media_as_file = ?")
            params.append(media_as_file)
        if selected_categories is not None:
            updates.append("selected_categories = ?")
            params.append(','.join(map(str, selected_categories)))
        if similarity_threshold is not None:
            updates.append("similarity_threshold = ?")
            params.append(similarity_threshold)

        if updates:
            query = f"""
                INSERT INTO user_settings 
                (user_id, enabled, interval_hours, media_as_file, selected_categories, similarity_threshold)
                VALUES (?, 0, 2, 0, NULL, 0.7)
                ON CONFLICT(user_id) DO UPDATE SET {', '.join(updates)}
            """
            cursor.execute(query, [user_id] + params)
            conn.commit()
    finally:
        conn.close()


def get_user_digest_settings(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT enabled, interval_hours, media_as_file, selected_categories, similarity_threshold
            FROM user_settings WHERE user_id = ?
        """, (user_id,))
        result = cursor.fetchone()

        if not result:
            return {
                'enabled': False,
                'interval_hours': 2,
                'media_as_file': False,
                'selected_categories': [],
                'similarity_threshold': 0.7
            }

        selected_categories = [int(x) for x in result[3].split(',')] if result[3] else []
        return {
            'enabled': bool(result[0]),
            'interval_hours': result[1],
            'media_as_file': bool(result[2]),
            'selected_categories': selected_categories,
            'similarity_threshold': float(result[4]) if result[4] is not None else 0.7
        }
    finally:
        conn.close()


# === 4. Історія відправлених постів ===
def add_sent_post(user_id: int, post_hash: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM sent_posts WHERE user_id = ? AND sent_at < datetime('now', '-7 days')",
        (user_id,)
    )
    cursor.execute(
        "INSERT OR REPLACE INTO sent_posts (user_id, post_hash, sent_at) VALUES (?, ?, datetime('now'))",
        (user_id, post_hash)
    )
    conn.commit()
    conn.close()


def is_post_sent(user_id: int, post_hash: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM sent_posts 
        WHERE user_id = ? AND post_hash = ? 
        AND sent_at > datetime('now', '-7 days')
    """, (user_id, post_hash))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def cleanup_old_posts(days: int = 7):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM sent_posts WHERE sent_at < datetime('now', ?)",
        (f'-{days} days',)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("✅ База даних успішно ініціалізована.")
# Сумісність зі старим кодом
get_user_channels = get_channels

def update_db_structure():
    """Застаріла функція, залишена для сумісності."""
    init_db()
