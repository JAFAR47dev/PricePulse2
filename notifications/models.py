import sqlite3  
from models.db import get_connection  

def create_notifications_table():  
    conn = get_connection()  
    cur = conn.cursor()  

    cur.execute("""  
    CREATE TABLE IF NOT EXISTS user_notifications (  
        user_id INTEGER PRIMARY KEY,  
        frequency TEXT DEFAULT 'once',          -- once per day
        delivery TEXT DEFAULT 'private',        -- private by default
        group_id INTEGER,  
        morning_time TEXT DEFAULT '08:00',      -- default notification time
        evening_time TEXT DEFAULT '20:00',  
        include_global INTEGER DEFAULT 0,       -- OFF by default
        include_gainers INTEGER DEFAULT 1,      -- /best ON
        include_losers INTEGER DEFAULT 1,       -- /worst ON
        include_news INTEGER DEFAULT 1,         -- /news ON
        include_gas INTEGER DEFAULT 0,          -- OFF
        include_cod INTEGER DEFAULT 0,          -- OFF
        timezone TEXT DEFAULT 'UTC'  
    )  
    """)  

    conn.commit()  
    conn.close()
    

def get_user_notification_settings(user_id):
    """Fetch settings. If none, insert default and return dictionary."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row      # <-- return dict-like rows
    cur = conn.cursor()

    cur.execute("SELECT * FROM user_notifications WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row:
        conn.close()
        return dict(row)

    # Insert defaults
    cur.execute("""
        INSERT INTO user_notifications (
            user_id,
            frequency,
            delivery,
            morning_time,
            evening_time,
            include_global,
            include_gainers,
            include_losers,
            include_news,
            include_gas,
            include_cod
        ) VALUES (?, 'once', 'private', '08:00', '20:00', 1, 1, 1, 1, 1, 1)
    """, (user_id,))

    conn.commit()

    cur.execute("SELECT * FROM user_notifications WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    conn.close()
    return dict(row)


def update_user_notification_setting(user_id, field, value):
    """
    Safely update one field only if it exists in the table.
    Prevents SQL injection.
    """
    allowed_fields = [
        "frequency", "delivery", "group_id", "morning_time", "evening_time",
        "include_global", "include_gainers", "include_losers",
        "include_news", "include_gas", "include_cod", "timezone"
    ]

    if field not in allowed_fields:
        raise ValueError(f"Invalid field: {field}")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE user_notifications SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()


def update_multiple_notification_settings(user_id, updates: dict):
    """
    Example usage:
    update_multiple_notification_settings(123, {
        "frequency": "twice",
        "delivery": "group",
        "group_id": -1001234567
    })
    """
    allowed_fields = [
        "frequency", "delivery", "group_id", "morning_time", "evening_time",
        "include_global", "include_gainers", "include_losers",
        "include_news", "include_gas", "include_cod"
    ]

    conn = get_connection()
    cur = conn.cursor()

    for field, value in updates.items():
        if field in allowed_fields:
            cur.execute(f"UPDATE user_notifications SET {field} = ? WHERE user_id = ?", (value, user_id))

    conn.commit()
    conn.close()
    
def get_all_active_users():
    """
    Fetch all users who should receive notifications:
    - frequency is not 'off'
    - delivery is 'private' or 'group' with a valid group_id
    Returns list of dicts with user settings.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            user_id,
            frequency,
            delivery,
            group_id,
            morning_time,
            evening_time,
            
            include_global,
            include_gainers,
            include_losers,
            include_news,
            include_gas,
            include_cod,
        
            COALESCE(timezone, 'UTC') AS timezone
        FROM user_notifications
        WHERE frequency != 'off'
        AND (
            delivery = 'private'
            OR (delivery = 'group' AND group_id IS NOT NULL)
        )
        ORDER BY user_id
    """)

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]
    

    
# --- Last notified hour helpers ---
def get_user_last_notified_hour(user_id: int) -> int | None:
    """
    Returns the last hour (0-23) the user was notified.
    Returns None if never notified.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure column exists (migration-safe)
    cur.execute("PRAGMA table_info(user_notifications)")
    columns = [col["name"] for col in cur.fetchall()]
    if "last_notified_hour" not in columns:
        cur.execute("ALTER TABLE user_notifications ADD COLUMN last_notified_hour INTEGER")
        conn.commit()

    cur.execute("SELECT last_notified_hour FROM user_notifications WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    return row["last_notified_hour"] if row and row["last_notified_hour"] is not None else None


def set_user_last_notified_hour(user_id: int, hour: int):
    """
    Update the last notified hour (0-23) for the user.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Ensure column exists
    cur.execute("PRAGMA table_info(user_notifications)")
    columns = [col["name"] for col in cur.fetchall()]
    if "last_notified_hour" not in columns:
        cur.execute("ALTER TABLE user_notifications ADD COLUMN last_notified_hour INTEGER")
        conn.commit()

    # Insert or update
    cur.execute("""
        UPDATE user_notifications SET last_notified_hour = ? WHERE user_id = ?
    """, (hour, user_id))

    conn.commit()
    conn.close()