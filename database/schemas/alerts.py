from models.db import get_connection

def init_alert_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------
    # Price alerts
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            condition TEXT,
            target_price REAL,
            repeat INTEGER DEFAULT 0
        )
    """)

    # -------------------------
    # Percent alerts
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS percent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            base_price REAL,
            threshold_percent REAL,
            repeat INTEGER DEFAULT 0
        )
    """)

    # -------------------------
    # Volume alerts
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volume_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            multiplier REAL,
            timeframe TEXT DEFAULT '1h',
            repeat INTEGER DEFAULT 0
        )
    """)

    # -------------------------
    # Risk alerts (SL / TP)
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            stop_price REAL,
            take_price REAL,
            repeat INTEGER DEFAULT 0
        )
    """)

    # -------------------------
    # Indicator alerts
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indicator_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            indicator TEXT,
            condition TEXT,
            timeframe TEXT DEFAULT '1h',
            repeat INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -------------------------
    # Indexes (IMPORTANT)
    # -------------------------
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_user
        ON alerts(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_indicator_alerts_user
        ON indicator_alerts(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_indicator_alerts_symbol
        ON indicator_alerts(symbol)
    """)

    conn.commit()
    conn.close()