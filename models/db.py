import sqlite3
import os

# Path to the database file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, 'data', 'alerts.db')

# Ensure the /data directory exists
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)


def get_connection():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            plan TEXT DEFAULT 'free',
            alerts_used INTEGER DEFAULT 0,
            last_reset TEXT,
            auto_delete_minutes INTEGER DEFAULT 0,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expiry_date TEXT,
            username TEXT
        )
    """)

    # Double-check missing columns (in case table pre-existed)
    cursor.execute("PRAGMA table_info(users)")
    columns = {col[1] for col in cursor.fetchall()}

    if "expiry_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN expiry_date TEXT")
    if "username" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")


    # Price alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            condition TEXT,
            target_price REAL,
            repeat INTEGER
        )
    """)

    # Percent alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS percent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            base_price REAL,
            threshold_percent REAL,
            repeat INTEGER
        )
    """)

    # Volume alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volume_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            multiplier REAL,
            timeframe TEXT DEFAULT '1h',
            repeat INTEGER
        )
    """)

    # Risk alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            stop_price REAL,
            take_price REAL,
            repeat INTEGER
        )
    """)

    # Custom alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            price_condition TEXT,
            price_value REAL,
            rsi_condition TEXT,
            rsi_value REAL,
            repeat INTEGER
        )
    """)

    # Portfolio alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            amount REAL,
            direction TEXT,
            target_value REAL,
            repeat INTEGER
        )
    """)

    # Portfolio limits
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_limits (
            user_id INTEGER PRIMARY KEY,
            max_alerts INTEGER DEFAULT 0,
            loss_limit REAL DEFAULT 0,
            profit_target REAL DEFAULT 0
        )
    """)

    # Watchlist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            base_price REAL,
            threshold_percent REAL DEFAULT 0,
            timeframe TEXT DEFAULT '1h'
        )
    """)
    
    # Ensure 'timeframe' column exists in watchlist
    cursor.execute("PRAGMA table_info(watchlist)")
    columns = [col[1] for col in cursor.fetchall()]
    if "timeframe" not in columns:
        cursor.execute("ALTER TABLE watchlist ADD COLUMN timeframe TEXT DEFAULT '1h'")
    
    # Portfolio (user assets)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            user_id INTEGER,
            symbol TEXT,
            amount REAL,
            PRIMARY KEY (user_id, symbol)
    )
""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            user_id INTEGER PRIMARY KEY,
            invited_count INTEGER DEFAULT 0,
            task2_submitted INTEGER DEFAULT 0,
            task3_submitted INTEGER DEFAULT 0,
            reward_claimed INTEGER DEFAULT 0
    )
""")

   
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            conditions TEXT,  -- JSON string containing condition list
            summary TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1  -- 1 = active, 0 = paused
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_wallets (
            user_id INTEGER PRIMARY KEY,
            wallet_address TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    
