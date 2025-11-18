from datetime import datetime
import pytz

def convert_to_local_time(user_timezone: str, hour_str: str) -> str:  
    """  
    Convert a UTC HH:MM time string into user's local timezone same-day HH:MM.  
    Handles invalid timezones safely.  
    """  
    # Parse hour string flexibly (e.g. "8", "8:00", "08:00")  
    parts = hour_str.split(":")  
    hour = int(parts[0])  
    minute = int(parts[1]) if len(parts) > 1 else 0  
  
    # Use current day to avoid DST errors  
    now = datetime.utcnow()  
    utc = pytz.timezone("UTC")  
    utc_dt = utc.localize(datetime(now.year, now.month, now.day, hour, minute))  
  
    # Validate timezone  
    try:  
        local_tz = pytz.timezone(user_timezone)  
    except Exception:  
        local_tz = utc  # fallback  
  
    local_dt = utc_dt.astimezone(local_tz)  
    return local_dt.strftime("%H:%M")  
    
    
def convert_to_local_hour(user_timezone: str, utc_dt: datetime = None) -> int:
    """
    Convert current UTC time to user's local timezone and return the hour (0-23).
    If utc_dt is provided, converts that time instead of now.
    Handles invalid timezones safely.
    """
    if utc_dt is None:
        utc_dt = datetime.utcnow()

    # Ensure UTC is timezone-aware
    utc = pytz.timezone("UTC")
    utc_dt = utc.localize(utc_dt.replace(tzinfo=None))

    # Validate timezone
    try:
        local_tz = pytz.timezone(user_timezone)
    except Exception:
        local_tz = utc  # fallback

    local_dt = utc_dt.astimezone(local_tz)
    return local_dt.hour
    
from datetime import datetime
import pytz

def convert_to_utc_time(user_timezone: str, local_hour_str: str) -> str:
    """
    Convert a HH:MM string in user's local timezone to UTC HH:MM.
    Returns a string in "HH:MM".
    """
    parts = local_hour_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0

    try:
        local_tz = pytz.timezone(user_timezone)
    except Exception:
        local_tz = pytz.UTC

    now = datetime.utcnow()
    local_dt = local_tz.localize(datetime(now.year, now.month, now.day, hour, minute))
    utc_dt = local_dt.astimezone(pytz.UTC)
    return utc_dt.strftime("%H:%M")