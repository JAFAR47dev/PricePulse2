from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta, time
import pytz
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Define global Forex sessions with UTC open/close times
SESSIONS = [
    {"name": "Sydney", "open": 21, "close": 6},
    {"name": "Tokyo", "open": 23, "close": 8},
    {"name": "London", "open": 7, "close": 16},
    {"name": "New York", "open": 13, "close": 22},
]

def strfdelta(td):
    seconds = int(td.total_seconds())
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"

def get_session_status(session, now_utc, user_tz):
    open_hour = session["open"]
    close_hour = session["close"]
    name = session["name"]

    # Today's base open/close
    open_utc = now_utc.replace(hour=open_hour, minute=0, second=0, microsecond=0)
    close_utc = now_utc.replace(hour=close_hour, minute=0, second=0, microsecond=0)

    # Handle sessions crossing midnight
    if open_hour > close_hour:
        # e.g. Sydney 21:00–06:00 UTC
        if now_utc.hour >= open_hour:
            close_utc += timedelta(days=1)
            is_open = True
        elif now_utc.hour < close_hour:
            open_utc -= timedelta(days=1)
            close_utc = close_utc
            is_open = True
        else:
            is_open = False
    else:
        is_open = open_hour <= now_utc.hour < close_hour

    if is_open:
        time_left = close_utc - now_utc
        local_close_time = close_utc.astimezone(user_tz).strftime('%H:%M')
        return f"🟢 *{name}*: Open — Closes in {strfdelta(time_left)} (at {local_close_time})"
    else:
        # Ensure next open time is in the future
        if open_utc <= now_utc:
            open_utc += timedelta(days=1)
        time_until = open_utc - now_utc
        local_open_time = open_utc.astimezone(user_tz).strftime('%H:%M')
        return f"🔴 *{name}*: Closed — Opens in {strfdelta(time_until)} (at {local_open_time})"
        
async def fxsessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    user_tz = datetime.now().astimezone().tzinfo
    now_local = now_utc.astimezone(user_tz)

    
    # Weekend detection (Saturday/Sunday)
    if now_utc.weekday() >= 5:
        # Find the next Sunday 22:00 UTC
        days_until_sunday = (6 - now_utc.weekday()) % 7
        next_sunday_open = datetime.combine(
            (now_utc + timedelta(days=days_until_sunday)).date(),
            time(22, 0)
        )

        # Convert to user's local timezone
        next_local_open = next_sunday_open.astimezone(user_tz)

        text = (
            f"🕒 Your local time: *{now_local.strftime('%A %H:%M')}*\n"
            f"📅 It's the weekend! Forex markets are currently *closed*.\n\n"
            f"🟠 Trading resumes Sunday 22:00 UTC "
            f"(Monday {next_local_open.strftime('%H:%M')} local time)."
        )

        return await update.message.reply_text(text, parse_mode="Markdown")
    
    session_lines = [get_session_status(s, now_utc, user_tz) for s in SESSIONS]
    text = (
        f"🕒 Your local time: *{now_local.strftime('%A %H:%M')}*\n"
        f"🌐 *Forex Session Status*\n\n" +
        "\n".join(session_lines)
    )
    await update.message.reply_text(text, parse_mode="Markdown")