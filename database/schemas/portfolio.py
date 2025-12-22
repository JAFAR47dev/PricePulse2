from models.db import get_connection

def init_portfolio_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------
    # Portfolio assets
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            user_id INTEGER,
            symbol TEXT,
            amount REAL,
            PRIMARY KEY (user_id, symbol),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # -------------------------
    # Portfolio limits (global per user)
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_limits (
            user_id INTEGER PRIMARY KEY,
            max_alerts INTEGER DEFAULT 0,
            loss_limit REAL DEFAULT NULL,
            profit_target REAL DEFAULT NULL,
            repeat_limit_loss INTEGER DEFAULT 0,
            repeat_limit_profit INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # -------------------------
    # Backward compatibility
    # -------------------------
    cursor.execute("PRAGMA table_info(portfolio_limits)")
    columns = {col[1] for col in cursor.fetchall()}

    if "repeat_limit_loss" not in columns:
        cursor.execute(
            "ALTER TABLE portfolio_limits ADD COLUMN repeat_limit_loss INTEGER DEFAULT 0"
        )

    if "repeat_limit_profit" not in columns:
        cursor.execute(
            "ALTER TABLE portfolio_limits ADD COLUMN repeat_limit_profit INTEGER DEFAULT 0"
        )

    # -------------------------
    # Portfolio alerts
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            amount REAL,
            direction TEXT,        -- 'above' | 'below'
            target_value REAL,
            repeat INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # -------------------------
    # Indexes (performance)
    # -------------------------
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_portfolio_user
        ON portfolio(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_portfolio_alerts_user
        ON portfolio_alerts(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_portfolio_alerts_symbol
        ON portfolio_alerts(symbol)
    """)

    conn.commit()
    conn.close()