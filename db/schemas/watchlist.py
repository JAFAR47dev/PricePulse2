from models.db import get_connection

def init_watchlist_table():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------
    # Watchlist table
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            base_price REAL,
            threshold_percent REAL DEFAULT 0,
            timeframe TEXT DEFAULT '1h',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE (user_id, symbol)
        )
    """)

    # -------------------------
    # Backward compatibility
    # -------------------------
    cursor.execute("PRAGMA table_info(watchlist)")
    columns = {col[1] for col in cursor.fetchall()}

    if "timeframe" not in columns:
        cursor.execute(
            "ALTER TABLE watchlist ADD COLUMN timeframe TEXT DEFAULT '1h'"
        )

    if "created_at" not in columns:
        cursor.execute(
            "ALTER TABLE watchlist ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
        )

    # -------------------------
    # Indexes (performance)
    # -------------------------
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_watchlist_user
        ON watchlist(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_watchlist_symbol
        ON watchlist(symbol)
    """)

    conn.commit()
    conn.close()