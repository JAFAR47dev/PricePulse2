from models.analytics_db import get_analytics_connection


def init_analytics_tables():
    conn = get_analytics_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS command_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            used_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes for fast analytics queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_command_usage_command
        ON command_usage(command)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_command_usage_used_at
        ON command_usage(used_at)
    """)

    conn.commit()
    conn.close()