from models.db import get_connection
from datetime import datetime, timedelta, timezone


def get_user_plan(user_id: int) -> str:
    """Returns 'pro_monthly'/'pro_yearly'/'pro_lifetime', 'trial', or 'free'."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT plan, trial_started_at FROM users WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return "free"

    plan, trial_started_at = row

    # Already on a paid plan
    if plan in ("pro_monthly", "pro_yearly", "pro_lifetime"):
        return plan

    # Trial not yet started
    if not trial_started_at:
        return "free"

    # Trial in progress or expired
    try:
        started = datetime.fromisoformat(trial_started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).days
        if elapsed < 5:
            return "trial"
    except Exception:
        pass

    return "free"


def start_trial(user_id: int) -> bool:
    """
    Activate the one-time 5-day trial for a user.
    Returns True if trial was started, False if already used.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT trial_started_at FROM users WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()

    if not row or row[0] is not None:
        # User doesn't exist or trial already used
        conn.close()
        return False

    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "UPDATE users SET trial_started_at = ? WHERE user_id = ?",
        (now, user_id),
    )
    conn.commit()
    conn.close()
    return True


def get_trial_days_remaining(user_id: int) -> int | None:
    """Returns days remaining in trial, or None if not in trial."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT trial_started_at FROM users WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        return None

    try:
        started = datetime.fromisoformat(row[0])
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).days
        remaining = 4 - elapsed  # 5 days = days 0,1,2,3,4
        return max(remaining, 0) if remaining >= 0 else None
    except Exception:
        return None


def set_user_plan(user_id: int, plan: str, expiry_date: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, plan) VALUES (?, ?)", (user_id, plan)
    )
    if expiry_date:
        cursor.execute(
            "UPDATE users SET plan = ?, expiry_date = ? WHERE user_id = ?",
            (plan, expiry_date, user_id),
        )
    else:
        cursor.execute(
            "UPDATE users SET plan = ?, expiry_date = NULL WHERE user_id = ?",
            (plan, user_id),
        )
    conn.commit()
    conn.close()


def get_users_expiring_in(hours: int = 24) -> list[dict]:
    """Return users whose trial expires within `hours` hours. Used by job queue."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, trial_started_at FROM users WHERE trial_started_at IS NOT NULL AND plan = 'free'")
    rows = cursor.fetchall()
    conn.close()

    expiring = []
    now = datetime.now(timezone.utc)
    for user_id, trial_started_at in rows:
        try:
            started = datetime.fromisoformat(trial_started_at)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            expiry = started + timedelta(days=5)
            time_left = (expiry - now).total_seconds() / 3600
            if 0 < time_left <= hours:
                expiring.append({"user_id": user_id, "expiry": expiry})
        except Exception:
            continue

    return expiring
    

async def trial_expiry_warning_job(context):
    """Warn users 24h before trial ends."""
    expiring = get_users_expiring_in(hours=24)
    for user in expiring:
        try:
            await context.bot.send_message(
                chat_id=user["user_id"],
                text=(
                    "⏰ *Your Pro trial expires tomorrow.*\n\n"
                    "You've had full access to:\n"
                    "🧠 AI setup analysis\n"
                    "📊 Full technical breakdowns\n"
                    "🔔 Advanced alerts\n"
                    "⚖️ Risk tools\n\n"
                    "Keep everything with /upgrade\n"
                    "or drop to free tier tomorrow."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"⚠️ Trial warning failed for {user['user_id']}: {e}")


async def trial_expiry_notification_job(context):
    """Notify users the day their trial expires."""
    # Users whose trial ended in the last 24h
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, trial_started_at FROM users "
        "WHERE trial_started_at IS NOT NULL AND plan = 'free'"
    )
    rows = cursor.fetchall()
    conn.close()

    now = datetime.now(timezone.utc)
    for user_id, trial_started_at in rows:
        try:
            started = datetime.fromisoformat(trial_started_at)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed_hours = (now - started).total_seconds() / 3600
            # Fire once between 120h and 144h (day 5 to day 6)
            if 120 <= elapsed_hours <= 144:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⏳ *Your Pro trial has ended.*\n\n"
                        "You still have free access — alerts,\n"
                        "basic levels, and market data.\n\n"
                        "Everything you used this week is\n"
                        "waiting behind /upgrade."
                    ),
                    parse_mode="Markdown",
                )
        except Exception as e:
            print(f"⚠️ Expiry notification failed for {user_id}: {e}")



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


#def set_auto_delete_minutes(user_id, minutes):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
#    cursor.execute("UPDATE users SET auto_delete_minutes = ? WHERE user_id = ?", (minutes, user_id))
#    conn.commit()
#    conn.close()


#def get_user_auto_delete_minutes(user_id):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute("SELECT auto_delete_minutes FROM users WHERE user_id = ?", (user_id,))
#    row = cursor.fetchone()
#    conn.close()
#    return row[0] if row else 0