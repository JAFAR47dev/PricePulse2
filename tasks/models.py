import sqlite3
from models.db import get_connection
from datetime import datetime, timedelta
import json


def create_task_progress_table():
    """
    Creates the main task_progress table with all required columns
    for Daily Streak, Referral Rewards, and Social Boost Tasks.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_progress (
            user_id INTEGER PRIMARY KEY,

            -- DAILY STREAK SYSTEM
            daily_streak INTEGER DEFAULT 0,
            last_active_date TEXT,
            streak_reward_claimed INTEGER DEFAULT 0,
            pro_expiry_date TEXT,

            -- REFERRAL REWARD SYSTEM
            referral_count INTEGER DEFAULT 0,
            claimed_referral_rewards TEXT DEFAULT '[]',  -- JSON: ["1","3"]

            -- SOCIAL BOOST TASKS
            social_tg INTEGER DEFAULT 0,
            social_tw INTEGER DEFAULT 0,
            social_story INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    
def init_task_progress(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO task_progress (
            user_id,
            daily_streak,
            last_active_date,
            streak_reward_claimed,
            pro_expiry_date,
            referral_count,
            claimed_referral_rewards,
            social_tg,
            social_tw,
            social_story
        ) VALUES (?, 0, NULL, 0, NULL, 0, '[]', 0, 0, 0)
    """, (user_id,))

    conn.commit()
    conn.close()
    

def get_task_progress(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT daily_streak, last_active_date, streak_reward_claimed, pro_expiry_date
        FROM task_progress 
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "daily_streak": 0,
            "last_active_date": None,
            "streak_reward_claimed": 0,
            "pro_expiry_date": None
        }

    return {
        "daily_streak": row[0],
        "last_active_date": row[1],
        "streak_reward_claimed": row[2],
        "pro_expiry_date": row[3]
    }
    
from datetime import datetime
from utils.streaks import should_count_for_streak

def update_daily_streak(user_id, message_text=None):
    """
    Update user's daily streak. Counts a new day when the date changes (UTC),
    not based on 24 hours passing.
    Returns: (new_streak, milestone_hit, reward_ready)
    """
    if message_text and not should_count_for_streak(message_text):
        return None, None, None  # ignore messages that shouldn't count

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT daily_streak, last_active_date, streak_reward_claimed
        FROM task_progress WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    today = datetime.utcnow().date()

    # Defaults
    daily_streak = 0
    last_active_raw = None
    reward_claimed = 0

    if row:
        daily_streak = row[0] or 0
        last_active_raw = row[1]  # may be None or a string
        reward_claimed = row[2]

    # Handle first ever activity
    if not last_active_raw:
        daily_streak = 1
    else:
        # Convert last_active_date safely
        try:
            last_active_date = datetime.strptime(last_active_raw, "%Y-%m-%d").date()
        except:
            # If stored with timestamp (e.g. "2025-11-20 07:30:11"), handle it
            last_active_date = datetime.fromisoformat(last_active_raw).date()

        if last_active_date == today:
            # Already counted today
            return daily_streak, None, None

        # New day → count streak
        day_diff = (today - last_active_date).days

        if day_diff == 1:
            daily_streak += 1  # consecutive day
        else:
            daily_streak = 1  # long gap → reset streak

    # Check milestones
    milestone_hit = daily_streak if daily_streak in [3, 4, 7, 9, 12] else None

    # 14-day reward
    reward_ready = (daily_streak >= 14 and reward_claimed == 0)

    # Write updated streak back to DB
    cursor.execute("""
        UPDATE task_progress
        SET daily_streak = ?, last_active_date = ?
        WHERE user_id = ?
    """, (daily_streak, today.strftime("%Y-%m-%d"), user_id))

    conn.commit()
    conn.close()

    return daily_streak, milestone_hit, reward_ready
    

        
import json

REFERRAL_TIERS = {
    1: 1,   # invites : reward days
    3: 7,
    5: 14
}

def get_referral_rewards(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT referral_count, claimed_referral_rewards FROM task_progress WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return 0, []

    referral_count = row[0]
    claimed = json.loads(row[1] or "[]")

    return referral_count, claimed
 

# --- REFERRAL TIER CLAIM ---
def claim_referral_tier(user_id, tier):
    reward_days = REFERRAL_TIERS[tier]
    conn = get_connection()
    cursor = conn.cursor()

    # Fetch claimed tiers
    cursor.execute("SELECT claimed_referral_rewards FROM task_progress WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    claimed = json.loads(row[0] if row and row[0] else "[]")

    if tier in claimed:
        return None  # Already claimed

    # Append new tier
    claimed.append(tier)

    # Set expiry date for Pro access
    expiry_date = (datetime.utcnow() + timedelta(days=reward_days)).strftime("%Y-%m-%d %H:%M:%S")

    # Update task_progress table
    cursor.execute("""
        UPDATE task_progress
        SET claimed_referral_rewards = ?, pro_expiry_date = ?
        WHERE user_id = ?
    """, (json.dumps(claimed), expiry_date, user_id))

    conn.commit()
    conn.close()

    # Upgrade user in main users table
    set_user_plan(user_id, "pro", expiry_date)

    return reward_days, expiry_date

       
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
    

