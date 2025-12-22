from models.db import get_connection

def init_tracked_wallets_table():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------
    # Tracked wallets table
    # -------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            wallet_address TEXT NOT NULL,
            blockchain TEXT NOT NULL,        -- e.g. eth, btc, tron, sol
            label TEXT,                      -- optional user label
            active INTEGER DEFAULT 1,        -- 1 = active, 0 = paused
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE(user_id, wallet_address, blockchain)
        )
    """)

    # -------------------------
    # Backward compatibility
    # -------------------------
    cursor.execute("PRAGMA table_info(tracked_wallets)")
    columns = {col[1] for col in cursor.fetchall()}

    if "blockchain" not in columns:
        cursor.execute(
            "ALTER TABLE tracked_wallets ADD COLUMN blockchain TEXT DEFAULT 'eth'"
        )

    if "label" not in columns:
        cursor.execute(
            "ALTER TABLE tracked_wallets ADD COLUMN label TEXT"
        )

    if "active" not in columns:
        cursor.execute(
            "ALTER TABLE tracked_wallets ADD COLUMN active INTEGER DEFAULT 1"
        )

    if "created_at" not in columns:
        cursor.execute(
            "ALTER TABLE tracked_wallets ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
        )

    # -------------------------
    # Indexes (critical)
    # -------------------------
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracked_wallets_user
        ON tracked_wallets(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracked_wallets_chain
        ON tracked_wallets(blockchain)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracked_wallets_active
        ON tracked_wallets(active)
    """)

    conn.commit()
    conn.close()