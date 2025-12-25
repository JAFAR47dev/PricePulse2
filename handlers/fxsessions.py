# handlers/fxsessions.py
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta, time
import pytz
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Sessions defined with their UTC offset ranges (when they're open in UTC time)
# These are approximate and account for typical DST patterns
SESSIONS = [
    # Sydney: typically opens around 22:00 UTC (previous day) to 07:00 UTC
    {"name": "Sydney", "utc_open": 22, "utc_close": 7, "crosses_midnight": True},
    # Tokyo: typically opens around 00:00 UTC to 09:00 UTC
    {"name": "Tokyo", "utc_open": 0, "utc_close": 9, "crosses_midnight": False},
    # London: typically opens around 08:00 UTC to 17:00 UTC (winter) / 07:00-16:00 (summer)
    {"name": "London", "utc_open": 8, "utc_close": 17, "crosses_midnight": False},
    # New York: typically opens around 13:00 UTC to 22:00 UTC (winter) / 12:00-21:00 (summer)
    {"name": "New York", "utc_open": 13, "utc_close": 22, "crosses_midnight": False},
    # Hong Kong: typically opens around 01:00 UTC to 10:00 UTC
    {"name": "Hong Kong", "utc_open": 1, "utc_close": 10, "crosses_midnight": False},
]


def format_timedelta(td: timedelta) -> str:
    """Format timedelta as 'Xh Ym' or 'Ym'"""
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_session_status(session: dict, now_utc: datetime) -> str:
    """
    Calculate if a session is open/closed based on UTC time.
    
    Args:
        session: dict with 'name', 'utc_open', 'utc_close', 'crosses_midnight'
        now_utc: current UTC datetime (timezone-aware)
    
    Returns:
        Formatted status string
    """
    current_hour = now_utc.hour
    current_minute = now_utc.minute
    
    open_hour = session["utc_open"]
    close_hour = session["utc_close"]
    crosses_midnight = session["crosses_midnight"]
    
    # Create datetime objects for open and close times today
    today = now_utc.date()
    open_time = datetime.combine(today, time(open_hour, 0)).replace(tzinfo=pytz.utc)
    close_time = datetime.combine(today, time(close_hour, 0)).replace(tzinfo=pytz.utc)
    
    # Handle sessions that cross midnight
    if crosses_midnight:
        # If close_hour < open_hour, the close is on the next day
        close_time = close_time + timedelta(days=1)
        
        # Check if we're in the session (either today's late hours or tomorrow's early hours)
        if now_utc >= open_time or now_utc < close_time:
            is_open = True
            # Calculate time until close
            if now_utc >= open_time:
                time_left = close_time - now_utc
            else:
                # We're in the early morning hours of the next day
                time_left = close_time - now_utc
        else:
            is_open = False
            # Next open is today at open_hour
            if now_utc < open_time:
                next_open = open_time
            else:
                next_open = open_time + timedelta(days=1)
            time_until = next_open - now_utc
    else:
        # Normal session (doesn't cross midnight)
        if open_time <= now_utc < close_time:
            is_open = True
            time_left = close_time - now_utc
        else:
            is_open = False
            # Calculate next open
            if now_utc < open_time:
                next_open = open_time
            else:
                # Next open is tomorrow
                next_open = open_time + timedelta(days=1)
            time_until = next_open - now_utc
    
    # Format the status message
    if is_open:
        close_time_str = close_time.strftime("%H:%M UTC")
        return f"🟢 *{session['name']}*: Open — Closes in {format_timedelta(time_left)} (at {close_time_str})"
    else:
        next_open_str = next_open.strftime("%H:%M UTC")
        day_suffix = " (tomorrow)" if next_open.date() > now_utc.date() else ""
        return f"🔴 *{session['name']}*: Closed — Opens in {format_timedelta(time_until)} (at {next_open_str}{day_suffix})"


def is_forex_weekend(now_utc: datetime) -> tuple[bool, datetime | None]:
    """
    Check if it's forex weekend (Friday 22:00 UTC to Sunday 22:00 UTC).
    
    Returns:
        (is_weekend, reopen_time)
    """
    weekday = now_utc.weekday()  # 0=Monday, 4=Friday, 6=Sunday
    hour = now_utc.hour
    
    # Friday after 22:00 UTC
    if weekday == 4 and hour >= 22:
        # Calculate when Sunday 22:00 UTC is
        days_until_sunday = 2
        reopen_date = now_utc.date() + timedelta(days=days_until_sunday)
        reopen_time = datetime.combine(reopen_date, time(22, 0)).replace(tzinfo=pytz.utc)
        return True, reopen_time
    
    # All of Saturday
    if weekday == 5:
        # Calculate Sunday 22:00 UTC
        days_until_sunday = 1
        reopen_date = now_utc.date() + timedelta(days=days_until_sunday)
        reopen_time = datetime.combine(reopen_date, time(22, 0)).replace(tzinfo=pytz.utc)
        return True, reopen_time
    
    # Sunday before 22:00 UTC
    if weekday == 6 and hour < 22:
        # Reopen today at 22:00 UTC
        reopen_time = datetime.combine(now_utc.date(), time(22, 0)).replace(tzinfo=pytz.utc)
        return True, reopen_time
    
    return False, None


async def fxsessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler: /fxsessions
    Shows Forex market session status in UTC time.
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/fxsessions")
    await handle_streak(update, context)

    # Get current UTC time
    now_utc = datetime.now(pytz.utc)
    current_time_str = now_utc.strftime("%A, %B %d, %Y at %H:%M UTC")
    
    # Check if it's weekend
    is_weekend, reopen_time = is_forex_weekend(now_utc)
    
    if is_weekend:
        time_until_open = reopen_time - now_utc
        reopen_str = reopen_time.strftime("%A at %H:%M UTC")
        
        text = (
            f"🕒 Current time: *{current_time_str}*\n\n"
            "📅 *Weekend — Forex markets are closed*\n\n"
            f"🟠 Markets reopen: *{reopen_str}*\n"
            f"⏰ Time until open: *{format_timedelta(time_until_open)}*"
        )
        return await update.message.reply_text(text, parse_mode="Markdown")
    
    # Get status for all sessions
    session_lines = [get_session_status(session, now_utc) for session in SESSIONS]
    
    text = (
        f"🕒 Current time: *{current_time_str}*\n\n"
        "🌐 *Forex Session Status*\n\n" +
        "\n\n".join(session_lines) +
        "\n\n_All times shown in UTC_"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")