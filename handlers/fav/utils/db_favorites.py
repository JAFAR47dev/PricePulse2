# utils/db_favorites.py

import sqlite3
import os

# Same base directory logic as your main DB
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, 'data', 'alerts.db')

# Ensure /data directory exists
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)


def get_conn():
    """
    Returns a connection to the same alerts.db file.
    - WAL mode for concurrency
    - timeout=10 to avoid locked DB errors
    - check_same_thread=False for multi-threaded Telegram bot
    """
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_favorites_table():
    """
    Creates the favorites table if it doesn't exist.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            symbol TEXT,
            PRIMARY KEY (user_id, symbol)
        )
    """)
    conn.commit()
    conn.close()


def add_favorite(user_id, symbol):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR IGNORE INTO favorites (user_id, symbol) VALUES (?,?)",
            (user_id, symbol.upper())
        )
        conn.commit()
    finally:
        conn.close()


def remove_favorite(user_id, symbol):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "DELETE FROM favorites WHERE user_id = ? AND symbol = ?",
        (user_id, symbol.upper())
    )
    conn.commit()
    conn.close()


def get_favorites(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT symbol FROM favorites WHERE user_id = ?",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]