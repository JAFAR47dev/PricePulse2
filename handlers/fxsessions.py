# handlers/fxsessions.py
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta, time
import pytz
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Sessions defined as LOCAL market hours (local timezone + open/close hour)
# This is DST-safe because we convert the local times to UTC for each date.
SESSIONS = [
    {"name": "Sydney", "tz": "Australia/Sydney", "open": 8, "close": 17},
    {"name": "Tokyo",  "tz": "Asia/Tokyo",      "open": 9, "close": 18},
    {"name": "London", "tz": "Europe/London",   "open": 8, "close": 17},
    {"name": "New York", "tz": "America/New_York", "open": 8, "close": 17},
    {"name": "Hong Kong", "tz": "Asia/Hong_Kong", "open": 9, "close": 18},
]

def format_timedelta(td: timedelta) -> str:
    # friendly Hh Mm
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def make_aware_local(dt_date, hour, local_tz):
    """Return a timezone-aware datetime in local_tz for date dt_date at given hour."""
    local_naive = datetime.combine(dt_date, time(hour, 0))
    local = local_tz.localize(local_naive, is_dst=None)
    return local

def get_session_status(session, now_utc, user_tz):
    """
    Calculate open/closed for a session.
    session: dict with keys name, tz (pytz zone string), open (int hour), close (int hour)
    now_utc: timezone-aware UTC datetime
    user_tz: timezone object or tzinfo for user's local display
    """
    local_tz = pytz.timezone(session["tz"])
    local_now = now_utc.astimezone(local_tz)
    today = local_now.date()

    open_local = make_aware_local(today, session["open"], local_tz)
    close_local = make_aware_local(today, session["close"], local_tz)

    # If close <= open in local time, session crosses midnight (close is next day)
    if close_local <= open_local:
        close_local = close_local + timedelta(days=1)

    open_utc = open_local.astimezone(pytz.utc)
    close_utc = close_local.astimezone(pytz.utc)

    # If now is before open_utc but local_now is after midnight and it's actually part of previous day's session,
    # also check previous day's open (handles early local morning hours falling into previous day's session)
    if now_utc < open_utc and (local_now.hour < session["open"]):
        # try previous day's session
        prev_open_local = make_aware_local(today - timedelta(days=1), session["open"], local_tz)
        prev_close_local = make_aware_local(today - timedelta(days=1), session["close"], local_tz)
        if prev_close_local <= prev_open_local:
            prev_close_local = prev_close_local + timedelta(days=1)
        prev_open_utc = prev_open_local.astimezone(pytz.utc)
        prev_close_utc = prev_close_local.astimezone(pytz.utc)
        if prev_open_utc <= now_utc < prev_close_utc:
            open_utc, close_utc = prev_open_utc, prev_close_utc

    is_open = (open_utc <= now_utc < close_utc)

    if is_open:
        time_left = close_utc - now_utc
        local_close_for_user = close_utc.astimezone(user_tz).strftime("%Y-%m-%d %H:%M")
        return f"🟢 *{session['name']}*: Open — Closes in {format_timedelta(time_left)} (at {local_close_for_user})"
    else:
        # find next open (today or tomorrow)
        if now_utc < open_utc:
            next_open_utc = open_utc
        else:
            # next day's open
            next_open_local = make_aware_local(today + timedelta(days=1), session["open"], local_tz)
            next_open_utc = next_open_local.astimezone(pytz.utc)

        time_until = next_open_utc - now_utc
        next_open_local_for_user = next_open_utc.astimezone(user_tz).strftime("%Y-%m-%d %H:%M")
        return f"🔴 *{session['name']}*: Closed — Opens in {format_timedelta(time_until)} (at {next_open_local_for_user})"

def forex_weekend_window():
    """
    Returns two timezone-aware datetimes (utc) marking the weekend close and reopen:
    closed_from (Fri 22:00 UTC) up to (but not including) reopen_at (Sun 22:00 UTC).
    """
    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    # Find most recent Friday
    friday = now.date() + timedelta((4 - now.weekday()) % 7)  # next or this Friday
    # But we want the nearest previous Friday relative to now — simplify: compute last Friday
    # safer approach:
    last_friday = now.date() - timedelta(days=(now.weekday() - 4) % 7)
    closed_from = datetime.combine(last_friday, time(22, 0)).replace(tzinfo=pytz.utc)
    # reopen is next Sunday 22:00 UTC after that Friday
    reopen_date = (last_friday + timedelta(days=2))  # Sunday
    reopen_at = datetime.combine(reopen_date, time(22, 0)).replace(tzinfo=pytz.utc)
    return closed_from, reopen_at

async def fxsessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler: /fxsessions
    Shows Forex market session status (UTC-aware, DST-correct, shows local times).
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/fxsessions")
    await handle_streak(update, context)

    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)

    # user's local tz (system local)
    user_tz = datetime.now().astimezone().tzinfo

    # Weekend detection: closed Friday 22:00 UTC -> Sunday 22:00 UTC
    closed_from, reopen_at = forex_weekend_window()
    if closed_from <= now_utc < reopen_at:
        next_local_open = reopen_at.astimezone(user_tz)
        text = (
            f"🕒 Your local time: *{now_utc.astimezone(user_tz).strftime('%A %Y-%m-%d %H:%M')}*\n"
            "📅 It's the weekend — Forex markets are currently *closed*.\n\n"
            f"🟠 Trading resumes: *{reopen_at.strftime('%Y-%m-%d %H:%M UTC')}* "
            f"→ local: *{next_local_open.strftime('%A %H:%M')}*"
        )
        return await update.message.reply_text(text, parse_mode="Markdown")

    # Otherwise compute session statuses
    session_lines = [get_session_status(s, now_utc, user_tz) for s in SESSIONS]

    text = (
        f"🕒 Your local time: *{now_utc.astimezone(user_tz).strftime('%A %Y-%m-%d %H:%M')}*\n"
        "🌐 *Forex Session Status*\n\n" +
        "\n".join(session_lines)
    )
    await update.message.reply_text(text, parse_mode="Markdown")