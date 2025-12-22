from models.db import get_connection

def init_users_table():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------
    # Core users table
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            plan TEXT DEFAULT 'free',
            alerts_used INTEGER DEFAULT 0,
            last_reset DATETIME,
            auto_delete_minutes INTEGER DEFAULT 0,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expiry_date DATETIME,
            last_active DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -------------------------
    # Backward compatibility
    # -------------------------
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {col[1] for col in cursor.fetchall()}

    def add_column_if_missing(name, definition, update_sql=None):
        if name not in existing_columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
            if update_sql:
                cursor.execute(update_sql)

    add_column_if_missing("username", "TEXT")
    add_column_if_missing("plan", "TEXT DEFAULT 'free'")
    add_column_if_missing("alerts_used", "INTEGER DEFAULT 0")
    add_column_if_missing("last_reset", "DATETIME")
    add_column_if_missing("auto_delete_minutes", "INTEGER DEFAULT 0")

    add_column_if_missing(
        "joined_at",
        "DATETIME",
        "UPDATE users SET joined_at = datetime('now') WHERE joined_at IS NULL"
    )

    add_column_if_missing("expiry_date", "DATETIME")

    add_column_if_missing(
        "last_active",
        "DATETIME",
        "UPDATE users SET last_active = datetime('now') WHERE last_active IS NULL"
    )

    # -------------------------
    # Indexes
    # -------------------------
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_last_active
        ON users(last_active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_plan
        ON users(plan)
    """)

    conn.commit()
    conn.close()