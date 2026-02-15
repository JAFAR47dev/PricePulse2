# database/setup_db.py

from models.db import get_connection

def create_setup_tables():
    """Create tables for setup tracking"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Trade setups table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_setups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            score INTEGER NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit_1 REAL NOT NULL,
            take_profit_2 REAL NOT NULL,
            risk_reward REAL NOT NULL,
            created_at TIMESTAMP NOT NULL,
            outcome TEXT,  -- 'win', 'loss', or NULL if pending
            profit_pct REAL,  -- Actual profit/loss %
            closed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Indexes for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_setups_symbol_timeframe 
        ON trade_setups(symbol, timeframe, created_at)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_setups_user 
        ON trade_setups(user_id, created_at)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_setups_score 
        ON trade_setups(score, outcome)
    """)
    
    conn.commit()
    conn.close()

# Run on startup
create_setup_tables()
