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

    # --- Backward compatibility check (auto-add missing columns) ---
    cursor.execute("PRAGMA table_info(users)")
    columns = {col[1] for col in cursor.fetchall()}

    # Add missing columns safely (no CURRENT_TIMESTAMP defaults)
    if "username" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")

    if "plan" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'")

    if "alerts_used" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN alerts_used INTEGER DEFAULT 0")

    if "last_reset" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_reset DATETIME")

    if "auto_delete_minutes" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN auto_delete_minutes INTEGER DEFAULT 0")

    if "joined_at" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN joined_at DATETIME")
        cursor.execute("UPDATE users SET joined_at = datetime('now') WHERE joined_at IS NULL")

    if "expiry_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN expiry_date DATETIME")

    if "last_active" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_active DATETIME")
        cursor.execute("UPDATE users SET last_active = datetime('now') WHERE last_active IS NULL")

    # Optional: Add index for faster stats queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_active ON users(last_active)")


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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            amount REAL,
            direction TEXT,
            target_value REAL,
            repeat INTEGER,
            FOREIGN KEY (user_id) REFERENCES portfolio_limits(user_id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_limits (
            user_id INTEGER PRIMARY KEY,
            max_alerts INTEGER DEFAULT 0,
            loss_limit REAL DEFAULT NULL,
            profit_target REAL DEFAULT NULL,
            repeat_limit_loss INTEGER DEFAULT 0,   -- 0 = off, 1 = repeat
            repeat_limit_profit INTEGER DEFAULT 0  -- 0 = off, 1 = repeat
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            wallet_address TEXT NOT NULL,
            UNIQUE(user_id, wallet_address)
    )
""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS command_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            used_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    
