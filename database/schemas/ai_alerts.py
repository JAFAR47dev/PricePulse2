from models.db import get_connection

def init_ai_alerts_table():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------
    # AI Alerts table
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            conditions TEXT NOT NULL,   -- JSON string
            summary TEXT,
            active INTEGER DEFAULT 1,   -- 1 = active, 0 = paused
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # -------------------------
    # Backward compatibility
    # -------------------------
    cursor.execute("PRAGMA table_info(ai_alerts)")
    columns = {col[1] for col in cursor.fetchall()}

    if "summary" not in columns:
        cursor.execute("ALTER TABLE ai_alerts ADD COLUMN summary TEXT")

    if "active" not in columns:
        cursor.execute("ALTER TABLE ai_alerts ADD COLUMN active INTEGER DEFAULT 1")

    if "created_at" not in columns:
        cursor.execute(
            "ALTER TABLE ai_alerts ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
        )

    # -------------------------
    # Indexes (critical for performance)
    # -------------------------
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_alerts_user
        ON ai_alerts(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_alerts_symbol
        ON ai_alerts(symbol)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_alerts_active
        ON ai_alerts(active)
    """)

    conn.commit()
    conn.close()