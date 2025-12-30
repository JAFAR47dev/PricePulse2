"""
Tasks and Rewards System Models

This module handles:
- Database schema for task progress
- Daily streak tracking logic
- Referral system logic
- Task progress queries and updates
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, List, Dict

from models.db import get_connection
from models.user import set_user_plan
from utils.streaks import should_count_for_streak


# ============================================================================
# CONSTANTS
# ============================================================================

REFERRAL_TIERS = {
    1: 1,    # 1 invite → 1 day PRO
    3: 7,    # 3 invites → 7 days PRO
    5: 14    # 5 invites → 14 days PRO
}

STREAK_MILESTONES = [1, 4, 7, 9, 12, 14]


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def create_task_progress_table():
    conn = get_connection()
    cursor = conn.cursor()

    # -----------------------------
    # 1️⃣ BASE TABLE (MINIMAL CREATE)
    # -----------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_progress (
            user_id INTEGER PRIMARY KEY
        )
    """)

    # -----------------------------
    # 2️⃣ SCHEMA MIGRATION (SAFE)
    # -----------------------------
    cursor.execute("PRAGMA table_info(task_progress)")
    existing_columns = {col[1] for col in cursor.fetchall()}

    # -------- DAILY STREAK --------
    if "daily_streak" not in existing_columns:
        cursor.execute("ALTER TABLE task_progress ADD COLUMN daily_streak INTEGER DEFAULT 0")

    if "last_active_date" not in existing_columns:
        cursor.execute("ALTER TABLE task_progress ADD COLUMN last_active_date TEXT")

    if "streak_reward_claimed" not in existing_columns:
        cursor.execute("ALTER TABLE task_progress ADD COLUMN streak_reward_claimed INTEGER DEFAULT 0")

    if "pro_expiry_date" not in existing_columns:
        cursor.execute("ALTER TABLE task_progress ADD COLUMN pro_expiry_date TEXT")

    # -------- REFERRALS --------
    if "referral_count" not in existing_columns:
        cursor.execute("ALTER TABLE task_progress ADD COLUMN referral_count INTEGER DEFAULT 0")

    if "claimed_referral_rewards" not in existing_columns:
        cursor.execute(
            "ALTER TABLE task_progress ADD COLUMN claimed_referral_rewards TEXT DEFAULT '[]'"
        )

    if "referral_rewards_claimed" not in existing_columns:
        cursor.execute(
            "ALTER TABLE task_progress ADD COLUMN referral_rewards_claimed TEXT DEFAULT ''"
        )

    # -------- METADATA --------
    if "created_at" not in existing_columns:
        cursor.execute(
            "ALTER TABLE task_progress ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP"
        )

    if "updated_at" not in existing_columns:
        cursor.execute(
            "ALTER TABLE task_progress ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
        )

    conn.commit()
    conn.close()
    
def create_referrals_table():
    """
    Create the referrals tracking table to store referral relationships.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(referrer_id, referred_id)
        )
    """)
    
    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_referrer_id 
        ON referrals(referrer_id)
    """)
    
    conn.commit()
    conn.close()


def init_task_progress(user_id: int):
    """
    Initialize task progress for a new user.
    Creates a row with default values if it doesn't exist.
    
    Args:
        user_id: The user's Telegram ID
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ✅ Get all existing columns dynamically
        cursor.execute("PRAGMA table_info(task_progress)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # ✅ Build dynamic INSERT with only existing columns
        column_defaults = {
            'user_id': user_id,
            'daily_streak': 0,
            'last_active_date': None,
            'streak_reward_claimed': 0,
            'pro_expiry_date': None,
            'referral_count': 0,
            'claimed_referral_rewards': '[]',
            'referral_rewards_claimed': '',
            'social_tg': 0,
            'social_tw': 0,
            'social_story': 0
        }
        
        # ✅ Only use columns that actually exist in the table
        insert_columns = [col for col in column_defaults.keys() if col in columns]
        insert_values = [column_defaults[col] for col in insert_columns]
        
        # ✅ Build the SQL dynamically
        columns_str = ', '.join(insert_columns)
        placeholders = ', '.join(['?' for _ in insert_columns])
        
        cursor.execute(f"""
            INSERT OR IGNORE INTO task_progress ({columns_str})
            VALUES ({placeholders})
        """, insert_values)

        conn.commit()
        print(f"✅ Task progress initialized for user {user_id}")
    except Exception as e:
        print(f"❌ Error initializing task progress for user {user_id}: {e}")
        conn.rollback()
    finally:
        conn.close()
        

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_date_safely(date_string: Optional[str]) -> Optional[object]:
    """
    Safely parse a date string that might be in various formats.
    
    Args:
        date_string: Date string to parse
    
    Returns:
        date object or None if parsing fails
    """
    if not date_string:
        return None
    
    # Try different date formats
    formats = [
        "%Y-%m-%d",                    # 2025-12-25
        "%Y-%m-%d %H:%M:%S",          # 2025-12-25 14:30:00
        "%Y-%m-%dT%H:%M:%S",          # ISO format
        "%Y-%m-%dT%H:%M:%S.%f",       # ISO with microseconds
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt).date()
        except ValueError:
            continue
    
    # Last resort: try fromisoformat
    try:
        return datetime.fromisoformat(date_string.replace('Z', '+00:00')).date()
    except Exception:
        return None


# ============================================================================
# TASK PROGRESS QUERIES
# ============================================================================

def get_task_progress(user_id: int) -> Dict:
    """
    Get all task progress data for a user.
    
    Args:
        user_id: The user's Telegram ID
    
    Returns:
        Dictionary containing all task progress fields
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ✅ Select all columns with *
        cursor.execute("""
            SELECT *
            FROM task_progress 
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()

        # ✅ Default values for all possible fields
        defaults = {
            "user_id": user_id,
            "daily_streak": 0,
            "last_active_date": None,
            "streak_reward_claimed": 0,
            "pro_expiry_date": None,
            "referral_count": 0,
            "claimed_referral_rewards": [],
            "referral_rewards_claimed": "",
            "social_tg": 0,
            "social_tw": 0,
            "social_story": 0,
            "created_at": None,
            "updated_at": None
        }

        if not row:
            # Return default values if no row exists
            return defaults

        # ✅ Get column names from cursor description
        column_names = [description[0] for description in cursor.description]
        
        # ✅ Build result dictionary dynamically
        result = {}
        for i, col_name in enumerate(column_names):
            value = row[i]
            
            # Handle JSON columns
            if col_name == "claimed_referral_rewards":
                result[col_name] = json.loads(value or "[]")
            else:
                result[col_name] = value
        
        # ✅ Fill in any missing columns with defaults (for backwards compatibility)
        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value
        
        return result
    
    except Exception as e:
        print(f"❌ Error getting task progress for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        # Return defaults on error
        return {
            "user_id": user_id,
            "daily_streak": 0,
            "last_active_date": None,
            "streak_reward_claimed": 0,
            "pro_expiry_date": None,
            "referral_count": 0,
            "claimed_referral_rewards": [],
            "referral_rewards_claimed": "",
            "social_tg": 0,
            "social_tw": 0,
            "social_story": 0,
            "created_at": None,
            "updated_at": None
        }
    finally:
        conn.close()

# ============================================================================
# DAILY STREAK SYSTEM
# ============================================================================

def update_daily_streak(
    user_id: int,
    message_text: Optional[str] = None
) -> Tuple[Optional[int], Optional[int], Optional[bool]]:
    """
    Update user's daily streak based on calendar day changes (UTC), not 24-hour periods.
    
    A streak is maintained when:
    - User is active on consecutive calendar days
    - Even if less than 24 hours have passed between actions
    
    A streak is broken when:
    - More than 1 calendar day has passed since last activity
    
    Args:
        user_id: The user's Telegram ID
        message_text: Optional message text to check if it should count for streak
    
    Returns:
        Tuple of (new_streak, milestone_hit, reward_ready):
        - new_streak: Current streak count
        - milestone_hit: Milestone number if reached, else None
        - reward_ready: True if 14-day reward is ready, else False
        Returns (None, None, None) if message shouldn't count or error occurs
    """
    # Check if message should count for streak
    if message_text and not should_count_for_streak(message_text):
        return None, None, None
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get current user data
        cursor.execute("""
            SELECT daily_streak, last_active_date, streak_reward_claimed
            FROM task_progress WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        # Get today's date in UTC (date only, no time component)
        today = datetime.now(timezone.utc).date()
        
        # Initialize defaults
        daily_streak = 0
        last_active_date = None
        reward_claimed = 0
        
        if row:
            daily_streak = row[0] or 0
            last_active_date = parse_date_safely(row[1])
            reward_claimed = row[2] or 0
        
        # Handle first-time activity
        if not last_active_date:
            daily_streak = 1
            milestone_hit = 1  # First day milestone
            reward_ready = False
        else:
            # Check if we've already counted today
            if last_active_date == today:
                # Already counted for today - return current values without updating
                milestone_hit = None
                reward_ready = (daily_streak >= 14 and reward_claimed == 0)
                return daily_streak, milestone_hit, reward_ready
            
            # Calculate days since last activity
            days_diff = (today - last_active_date).days
            
            if days_diff == 1:
                # Consecutive day - increment streak
                daily_streak += 1
            elif days_diff > 1:
                # Streak broken - reset to 1
                daily_streak = 1
            else:
                # Edge case: last_active_date is in the future
                daily_streak = 1
            
            # Check if milestone was hit
            milestone_hit = daily_streak if daily_streak in STREAK_MILESTONES else None
            
            # Check if 14-day reward is ready
            reward_ready = (daily_streak >= 14 and reward_claimed == 0)
        
        # Update database with new streak and today's date
        cursor.execute("""
            UPDATE task_progress
            SET daily_streak = ?,
                last_active_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (daily_streak, today.isoformat(), user_id))
        
        conn.commit()
        
        return daily_streak, milestone_hit, reward_ready
    
    except Exception as e:
        print(f"Error updating daily streak for user {user_id}: {e}")
        conn.rollback()
        return None, None, None
    
    finally:
        conn.close()


def get_streak_info(user_id: int) -> Dict:
    """
    Get current streak information for a user without updating it.
    
    Args:
        user_id: The user's Telegram ID
    
    Returns:
        Dictionary with streak info:
        - streak: current streak count
        - last_active: last active date
        - reward_claimed: whether 14-day reward was claimed
        - days_until_break: days until streak breaks (0 if breaking today)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT daily_streak, last_active_date, streak_reward_claimed
            FROM task_progress WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return {
                'streak': 0,
                'last_active': None,
                'reward_claimed': 0,
                'days_until_break': None
            }
        
        daily_streak = row[0] or 0
        last_active_date = parse_date_safely(row[1])
        reward_claimed = row[2] or 0
        
        # Calculate days until streak breaks
        today = datetime.now(timezone.utc).date()
        if last_active_date:
            days_diff = (today - last_active_date).days
            days_until_break = max(0, 1 - days_diff)  # 0 if already breaking/broken
        else:
            days_until_break = None
        
        return {
            'streak': daily_streak,
            'last_active': last_active_date,
            'reward_claimed': reward_claimed,
            'days_until_break': days_until_break
        }
    
    except Exception as e:
        print(f"Error getting streak info for user {user_id}: {e}")
        return {
            'streak': 0,
            'last_active': None,
            'reward_claimed': 0,
            'days_until_break': None
        }
    finally:
        conn.close()


# ============================================================================
# REFERRAL SYSTEM
# ============================================================================

def get_referral_rewards(user_id: int) -> Tuple[int, List[int]]:
    """
    Get referral count and claimed tiers for a user.
    
    Args:
        user_id: The user's Telegram ID
    
    Returns:
        Tuple of (referral_count, claimed_tiers)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT referral_count, referral_rewards_claimed
            FROM task_progress
            WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()

        if not row:
            return 0, []

        referral_count = row[0] or 0
        claimed_str = row[1] or ""
        
        # Parse claimed tiers (comma-separated string to list of ints)
        if claimed_str:
            claimed = [int(t) for t in claimed_str.split(",") if t.strip().isdigit()]
        else:
            claimed = []

        return referral_count, claimed
    
    except Exception as e:
        print(f"Error getting referral rewards for user {user_id}: {e}")
        return 0, []
    finally:
        conn.close()


def add_referral(referrer_id: int, referred_id: int) -> bool:
    """
    Record a new referral and increment referrer's count.
    
    Args:
        referrer_id: The user who referred
        referred_id: The new user who was referred
    
    Returns:
        True if successful, False if duplicate or error
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if referral already exists
        cursor.execute("""
            SELECT id FROM referrals
            WHERE referrer_id = ? AND referred_id = ?
        """, (referrer_id, referred_id))
        
        if cursor.fetchone():
            return False  # Duplicate referral
        
        # Add referral record
        cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
        """, (referrer_id, referred_id))
        
        # Increment referral count
        cursor.execute("""
            UPDATE task_progress
            SET referral_count = referral_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (referrer_id,))
        
        conn.commit()
        return True
    
    except Exception as e:
        print(f"Error adding referral {referrer_id} -> {referred_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_user_referrals(user_id: int) -> List[Dict]:
    """
    Get list of all users referred by a specific user.
    
    Args:
        user_id: The referrer's Telegram ID
    
    Returns:
        List of referral records with referred_id and timestamp
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT referred_id, timestamp
            FROM referrals
            WHERE referrer_id = ?
            ORDER BY timestamp DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        return [
            {"referred_id": row[0], "timestamp": row[1]}
            for row in rows
        ]
    
    except Exception as e:
        print(f"Error getting user referrals for {user_id}: {e}")
        return []
    finally:
        conn.close()

