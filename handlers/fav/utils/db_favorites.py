# handlers/fav/utils/db_favorites.py
from models.db import get_connection

def init_favorites_table():
    conn = get_connection()
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
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR IGNORE INTO favorites (user_id, symbol) VALUES (?,?)",
            (user_id, symbol.upper())
        )
        conn.commit()
        # rowcount is 1 if inserted, 0 if ignored
        return c.rowcount > 0
    finally:
        conn.close()

def remove_favorite(user_id, symbol):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM favorites WHERE user_id = ? AND symbol = ?", (user_id, symbol.upper()))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

def get_favorites(user_id):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT symbol FROM favorites WHERE user_id = ? ORDER BY symbol", (user_id,))
        rows = c.fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()