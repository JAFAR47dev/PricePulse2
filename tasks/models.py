import sqlite3
from models.db import get_connection

def create_referrals_table():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    
def create_task_progress_table():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_progress (
            user_id INTEGER PRIMARY KEY,
            task1_done INTEGER DEFAULT 0,
            task2_done INTEGER DEFAULT 0,
            task3_done INTEGER DEFAULT 0,
            proof1 TEXT,
            proof2 TEXT,
            proof3 TEXT,
            approved_by_admin INTEGER DEFAULT 0,
            reward_given INTEGER DEFAULT 0,
            expiry_date TEXT
        )
    """)

    conn.commit()
    conn.close()
    
def init_task_progress(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO task_progress (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_task_progress(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT task1_done, task2_done, task3_done FROM task_progress WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "task1_done": row[0],
            "task2_done": row[1],
            "task3_done": row[2]
        }
    return {"task1_done": 0, "task2_done": 0, "task3_done": 0}
    
    
from models.db import get_connection

def save_proof(user_id: int, task_num: int, proof: str):
    conn = get_connection()
    cursor = conn.cursor()

    # Ensure row exists
    cursor.execute("INSERT OR IGNORE INTO task_progress (user_id) VALUES (?)", (user_id,))
    cursor.execute(f"""
        UPDATE task_progress
        SET proof{task_num} = ?
        WHERE user_id = ?
    """, (proof, user_id))

    conn.commit()
    conn.close()
    
def store_referral(referrer_id: int, referred_id: int):
    if referrer_id == referred_id:
        print("❌ Self-referral attempt blocked.")
        return False  # Block self-referral

    conn = get_connection()
    cursor = conn.cursor()

    # Prevent duplicate
    cursor.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (referred_id,))
    if cursor.fetchone():
        conn.close()
        return False

    cursor.execute(
        "INSERT INTO referrals (referrer_id, referred_id, timestamp) VALUES (?, ?, datetime('now'))",
        (referrer_id, referred_id)
    )

    conn.commit()
    conn.close()
    return True