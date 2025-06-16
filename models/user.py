from models.db import get_connection
from datetime import datetime, timedelta


def get_user_plan(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "free"


from datetime import datetime
from models.db import get_connection

def set_user_plan(user_id: int, plan: str, expiry_date: str = None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT OR IGNORE INTO users (user_id, plan) VALUES (?, ?)", (user_id, plan))
    if expiry_date:
        cursor.execute("UPDATE users SET plan = ?, expiry_date = ? WHERE user_id = ?", (plan, expiry_date, user_id))
    else:
        cursor.execute("UPDATE users SET plan = ?, expiry_date = NULL WHERE user_id = ?", (plan, user_id))

    conn.commit()
    conn.close()


def can_create_price_alert(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT alerts_used, last_reset, plan FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    now = datetime.utcnow()

    if not row:
        # First time user
        cursor.execute(
            "INSERT INTO users (user_id, alerts_used, last_reset, plan) VALUES (?, ?, ?, ?)",
            (user_id, 1, now.isoformat(), "free")
        )
        conn.commit()
        conn.close()
        return True

    used, last_reset_str, plan = row
    last_reset = datetime.fromisoformat(last_reset_str) if last_reset_str else now

    if plan == "pro":
        conn.close()
        return True  # Unlimited for Pro

    # Reset if 24 hours passed
    if now - last_reset > timedelta(hours=24):
        cursor.execute(
            "UPDATE users SET alerts_used = ?, last_reset = ? WHERE user_id = ?",
            (1, now.isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        return True

    if used >= 3:
        conn.close()
        return False

    # Increment usage
    cursor.execute(
        "UPDATE users SET alerts_used = alerts_used + 1 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()
    return True


def set_auto_delete_minutes(user_id, minutes):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET auto_delete_minutes = ? WHERE user_id = ?", (minutes, user_id))
    conn.commit()
    conn.close()


def get_user_auto_delete_minutes(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT auto_delete_minutes FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0