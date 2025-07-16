# models/wallet_tracker.py

from models.db import get_connection

def save_tracked_wallet(user_id: int, wallet: str):
    db = get_connection()
    db.execute(
        "INSERT OR REPLACE INTO tracked_wallets (user_id, wallet_address) VALUES (?, ?)",
        (user_id, wallet)
    )
    db.commit()

def get_all_tracked_wallets():
    db = get_connection()
    result = db.execute("SELECT user_id, wallet_address FROM tracked_wallets").fetchall()
    return [{"user_id": row[0], "wallet": row[1]} for row in result]

def remove_tracked_wallet(user_id: int):
    db = get_connection()
    db.execute("DELETE FROM tracked_wallets WHERE user_id = ?", (user_id,))
    db.commit()