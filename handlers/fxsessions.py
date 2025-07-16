from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta, time
import pytz

# Define global Forex sessions with UTC open/close times
SESSIONS = [
    {"name": "Sydney", "open": 22, "close": 7},
    {"name": "Tokyo", "open": 0, "close": 9},
    {"name": "London", "open": 8, "close": 17},
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

    # Calculate local open/close times
    open_utc = now_utc.replace(hour=open_hour, minute=0, second=0, microsecond=0)
    close_utc = now_utc.replace(hour=close_hour, minute=0, second=0, microsecond=0)

    if open_hour > close_hour:
        # Session spans across midnight
        is_open = now_utc.hour >= open_hour or now_utc.hour < close_hour
        if now_utc.hour >= open_hour:
            close_utc = close_utc + timedelta(days=1)
        else:
            open_utc = open_utc - timedelta(days=1)
    else:
        is_open = open_hour <= now_utc.hour < close_hour
        if now_utc.hour >= close_hour:
            open_utc += timedelta(days=1)
        elif now_utc.hour < open_hour:
            close_utc -= timedelta(days=1)

    if is_open:
        time_left = close_utc - now_utc
        local_close_time = close_utc.astimezone(user_tz).strftime('%H:%M')
        return f"🟢 *{name}*: Open — Closes in {strfdelta(time_left)} (at {local_close_time})"
    else:
        time_until = open_utc - now_utc
        local_open_time = open_utc.astimezone(user_tz).strftime('%H:%M')
        return f"🔴 *{name}*: Closed — Opens in {strfdelta(time_until)} (at {local_open_time})"

async def fxsessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    user_tz = datetime.now().astimezone().tzinfo
    now_local = now_utc.astimezone(user_tz)

    # Weekend detection (Saturday/Sunday)
    if now_utc.weekday() >= 5:
        text = (
            f"🕒 Your local time: *{now_local.strftime('%A %H:%M')}*\n"
            f"📅 It's the weekend! Forex markets are currently *closed*.\n\n"
            f"🟠 Trading resumes Sunday 22:00 UTC (Monday {datetime.combine(datetime.utcnow().date(), time(22)).astimezone(user_tz).strftime('%H:%M')} local time)."
        )
        return await update.message.reply_text(text, parse_mode="Markdown")

    session_lines = [get_session_status(s, now_utc, user_tz) for s in SESSIONS]
    text = (
        f"🕒 Your local time: *{now_local.strftime('%A %H:%M')}*\n"
        f"🌐 *Forex Session Status*\n\n" +
        "\n".join(session_lines)
    )
    await update.message.reply_text(text, parse_mode="Markdown")