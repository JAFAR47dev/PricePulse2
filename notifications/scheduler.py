# notifications/scheduler.py

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import UTC
from telegram import Bot
from telegram.error import TelegramError, Forbidden, BadRequest, RetryAfter
from notifications.models import (
    get_all_active_users,
    get_user_last_notified_hour,
    set_user_last_notified_hour
)
from notifications.services.notification_data import get_notification_data


# ============================================================================
# GLOBAL SCHEDULER INSTANCE
# ============================================================================
_scheduler: Optional[AsyncIOScheduler] = None


# ============================================================================
# NOTIFICATION HISTORY & LOGGING
# ============================================================================

def log_notification(
    user_id: int,
    status: str,
    timestamp: datetime,
    message_preview: str = "",
    error: str = ""
) -> None:
    """
    Store notification history in database.
    
    Args:
        user_id: User ID
        status: 'success', 'failed', 'retried', 'blocked'
        timestamp: When notification was attempted
        message_preview: First 100 chars of message
        error: Error message if failed
    """
    try:
        from models.db import get_connection
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                message_preview TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            INSERT INTO notification_history 
            (user_id, status, timestamp, message_preview, error)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, status, timestamp.isoformat(), message_preview[:100], error))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"[History] Failed to log notification for user {user_id}: {e}")


def get_user_notification_stats(user_id: int) -> Dict[str, Any]:
    """
    Get notification statistics for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        dict: Statistics including total sent, success rate, etc.
    """
    try:
        from models.db import get_connection
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Total notifications
        cursor.execute("""
            SELECT COUNT(*) FROM notification_history 
            WHERE user_id = ?
        """, (user_id,))
        total = cursor.fetchone()[0]
        
        # Successful notifications
        cursor.execute("""
            SELECT COUNT(*) FROM notification_history 
            WHERE user_id = ? AND status = 'success'
        """, (user_id,))
        successful = cursor.fetchone()[0]
        
        # Last notification
        cursor.execute("""
            SELECT timestamp, status FROM notification_history 
            WHERE user_id = ? 
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        last_row = cursor.fetchone()
        
        conn.close()
        
        success_rate = (successful / total * 100) if total > 0 else 0
        
        return {
            "total_sent": total,
            "successful": successful,
            "success_rate": round(success_rate, 1),
            "last_sent": last_row[0] if last_row else None,
            "last_status": last_row[1] if last_row else None
        }
        
    except Exception as e:
        print(f"[Stats] Failed to get stats for user {user_id}: {e}")
        return {
            "total_sent": 0,
            "successful": 0,
            "success_rate": 0,
            "last_sent": None,
            "last_status": None
        }


# ============================================================================
# NOTIFICATION SENDING WITH RETRY
# ============================================================================

async def send_notification_with_retry(
    bot: Bot,
    user: Dict[str, Any],
    message: str,
    disable_web_page_preview: bool = True,
    max_retries: int = 3
) -> Tuple[bool, str]:
    """
    Send a notification with retry logic.
    
    Args:
        bot: Telegram Bot instance
        user: User dictionary
        message: Message to send
        disable_web_page_preview: Whether to disable link previews
        max_retries: Maximum retry attempts
        
    Returns:
        tuple: (success: bool, error_message: str)
    """
    user_id = user.get("user_id")
    
    for attempt in range(1, max_retries + 1):
        try:
            chat_id = None
            if user.get("delivery") == "private":
                chat_id = user.get("user_id")
            elif user.get("delivery") == "group":
                chat_id = user.get("group_id")

            if not chat_id:
                return False, "No valid chat_id"

            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=disable_web_page_preview
            )
            
            if attempt > 1:
                print(f"[Notification] ✅ Succeeded on retry {attempt} for user {user_id}")
                log_notification(user_id, "retried", datetime.utcnow(), message)
            else:
                print(f"[Notification] ✅ Sent to user {user_id}")
                log_notification(user_id, "success", datetime.utcnow(), message)
            
            return True, ""

        except Forbidden as e:
            error = f"Bot blocked: {e}"
            print(f"[Notification] ❌ {error} - user {user_id}")
            log_notification(user_id, "blocked", datetime.utcnow(), message, str(e))
            return False, error
            
        except BadRequest as e:
            error = f"Bad request: {e}"
            print(f"[Notification] ❌ {error} - user {user_id}")
            log_notification(user_id, "failed", datetime.utcnow(), message, str(e))
            return False, error
            
        except RetryAfter as e:
            wait_time = e.retry_after
            print(f"[Notification] ⏳ Rate limited, waiting {wait_time}s - user {user_id}")
            await asyncio.sleep(wait_time)
            continue
            
        except TelegramError as e:
            error = f"Telegram error: {e}"
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                print(f"[Notification] ⚠️ Attempt {attempt} failed, retrying in {wait_time}s - user {user_id}")
                await asyncio.sleep(wait_time)
            else:
                print(f"[Notification] ❌ {error} after {max_retries} attempts - user {user_id}")
                log_notification(user_id, "failed", datetime.utcnow(), message, str(e))
                return False, error
                
        except Exception as e:
            error = f"Unexpected error: {e}"
            print(f"[Notification] ❌ {error} - user {user_id}")
            log_notification(user_id, "failed", datetime.utcnow(), message, str(e))
            return False, error
    
    return False, f"Failed after {max_retries} retries"


# ============================================================================
# MESSAGE BUILDING
# ============================================================================

def parse_hour(time_str: Optional[str]) -> Optional[int]:
    """
    Parse hour from time string (HH:MM format in UTC).
    
    Args:
        time_str: Time string in HH:MM format
        
    Returns:
        int: Hour value (0-23) or None if invalid
    """
    if not time_str or not isinstance(time_str, str):
        return None
    try:
        hour = int(time_str.split(":")[0])
        if 0 <= hour <= 23:
            return hour
        return None
    except (ValueError, IndexError):
        return None


def should_notify_user(user: Dict[str, Any], current_utc_hour: int, last_hour: Optional[int]) -> bool:
    """
    Determine if user should be notified at current UTC hour.
    
    Args:
        user: User dictionary with notification preferences
        current_utc_hour: Current hour in UTC (0-23)
        last_hour: Last hour user was notified
        
    Returns:
        bool: True if user should be notified
    """
    # Skip if already notified in this hour
    if last_hour == current_utc_hour:
        return False
    
    frequency = user.get("frequency")
    if frequency == "off":
        return False
    
    # Parse scheduled hours (now in UTC)
    morning_hour = parse_hour(user.get("morning_time"))
    evening_hour = parse_hour(user.get("evening_time"))
    
    # Check if current UTC hour matches any scheduled notification time
    if frequency in ["once", "twice"] and morning_hour == current_utc_hour:
        return True
    if frequency == "twice" and evening_hour == current_utc_hour:
        return True
    
    return False


async def build_message(user: Dict[str, Any], notif_data: Dict[str, Any]) -> str:
    """
    Build dynamic notification message per user safely.
    
    Args:
        user: User dictionary with notification preferences
        notif_data: Notification data dictionary
        
    Returns:
        str: Formatted message string
    """
    parts = ["📊 *Daily Market Update*"]

    # --- 🌍 Global Market Section ---
    if user.get("include_global") and notif_data.get("global"):
        g = notif_data["global"]
        if isinstance(g, dict):
            parts.append(
                "\n🌍 *Global Market Overview*\n"
                f"💰 *Market Cap:* {g.get('market_cap', 'N/A')}\n"
                f"📊 *24h Volume:* {g.get('volume', 'N/A')}\n"
                f"📈 *Change:* {g.get('change', 'N/A')}\n"
                f"🏆 *BTC Dom:* {g.get('btc_dominance', 'N/A')} | "
                f"💎 *ETH Dom:* {g.get('eth_dominance', 'N/A')}"
            )
        else:
            parts.append(f"\n🌍 {g}")

    # --- 🚀 Top Gainers ---
    if user.get("include_gainers") and notif_data.get("gainers"):
        gainers_data = notif_data["gainers"]
        if isinstance(gainers_data, list) and len(gainers_data) > 0:
            formatted = "\n".join(
                [f"• {c[0]} — 📈 *{c[1]}*" for c in gainers_data[:3] if len(c) >= 2]
            )
            if formatted:
                parts.append(f"\n🚀 *Top Gainers (24h)*\n{formatted}")
        elif isinstance(gainers_data, str):
            parts.append(f"\n🚀 *Top Gainers:* {gainers_data}")

    # --- 📉 Top Losers ---
    if user.get("include_losers") and notif_data.get("losers"):
        losers_data = notif_data["losers"]
        if isinstance(losers_data, list) and len(losers_data) > 0:
            formatted = "\n".join(
                [f"• {c[0]} — 🔻 *{c[1]}*" for c in losers_data[:3] if len(c) >= 2]
            )
            if formatted:
                parts.append(f"\n📉 *Top Losers (24h)*\n{formatted}")
        elif isinstance(losers_data, str):
            parts.append(f"\n📉 *Top Losers:* {losers_data}")

    # --- 📰 News Section ---
    if user.get("include_news") and notif_data.get("news"):
        news_data = notif_data["news"]
        if isinstance(news_data, list) and len(news_data) > 0:
            formatted_news = []
            for n in news_data[:3]:
                if isinstance(n, str) and '](' in n:
                    try:
                        title = n.split('](')[0].replace('[', '').strip()
                        url = n.split('](')[1].rstrip(')')
                        formatted_news.append(f"• [{title}]({url})")
                    except (IndexError, ValueError):
                        formatted_news.append(f"• {n}")
                else:
                    formatted_news.append(f"• {n}")
            
            if formatted_news:
                parts.append(f"\n📰 *Latest Crypto News*\n" + "\n".join(formatted_news))
        elif isinstance(news_data, str):
            parts.append(f"\n📰 *News:* {news_data}")

    # --- ⛽ Gas Fees ---
    if user.get("include_gas") and notif_data.get("gas"):
        gas_data = notif_data["gas"]
        if isinstance(gas_data, str):
            parts.append(f"\n⛽ *Gas Fees*\n{gas_data}")
        elif isinstance(gas_data, dict):
            parts.append(
                "\n⛽ *Gas Fees (ETH)*\n"
                f"• Low: {gas_data.get('low', 'N/A')}\n"
                f"• Standard: {gas_data.get('standard', 'N/A')}\n"
                f"• High: {gas_data.get('high', 'N/A')}"
            )

    # --- 💡 Coin of the Day ---
    if user.get("include_cod") and notif_data.get("cod"):
        cod_data = notif_data["cod"]
        if isinstance(cod_data, dict):
            parts.append(
                f"\n💡 *Coin of the Day*\n"
                f"• *{cod_data.get('coin', 'N/A')}* — {cod_data.get('reason', 'No reason provided.')}"
            )
        elif isinstance(cod_data, str):
            parts.append(f"\n💡 *Coin of the Day:* {cod_data}")

    return "\n".join(parts)


# ============================================================================
# BATCH SENDING WITH RATE LIMITING
# ============================================================================

async def send_notifications_in_batches(
    bot: Bot,
    users_to_notify: List[Tuple[Dict[str, Any], int]],
    notif_data: Dict[str, Any],
    batch_size: int = 30,
    delay_between_batches: float = 1.0
) -> Dict[str, int]:
    """
    Send notifications in controlled batches to avoid rate limits.
    
    Args:
        bot: Telegram Bot instance
        users_to_notify: List of (user, utc_hour) tuples
        notif_data: Notification data
        batch_size: Number of users per batch
        delay_between_batches: Seconds to wait between batches
        
    Returns:
        dict: Statistics (sent, failed, retried, blocked)
    """
    stats = {"sent": 0, "failed": 0, "retried": 0, "blocked": 0}
    
    async def send_to_user(user: Dict[str, Any], utc_hour: int) -> None:
        try:
            message = await build_message(user, notif_data)
            success, error = await send_notification_with_retry(
                bot,
                user,
                message,
                disable_web_page_preview=True
            )

            if success:
                stats["sent"] += 1
                set_user_last_notified_hour(user["user_id"], utc_hour)
            else:
                if "blocked" in error.lower():
                    stats["blocked"] += 1
                else:
                    stats["failed"] += 1
                    
        except Exception as e:
            print(f"[Batch] Error sending to user {user.get('user_id')}: {e}")
            stats["failed"] += 1
    
    # Process in batches
    total_batches = (len(users_to_notify) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(users_to_notify))
        batch = users_to_notify[start_idx:end_idx]
        
        print(f"[Batch] Processing batch {batch_num + 1}/{total_batches} ({len(batch)} users)")
        
        await asyncio.gather(
            *(send_to_user(user, hour) for user, hour in batch),
            return_exceptions=True
        )
        
        # Delay between batches (except for last batch)
        if batch_num < total_batches - 1:
            await asyncio.sleep(delay_between_batches)
    
    return stats


# ============================================================================
# MISSED NOTIFICATIONS CHECK
# ============================================================================

async def check_missed_notifications(app, lookback_hours: int = 2) -> None:
    """
    Check for notifications that should have been sent while bot was down.
    
    Args:
        app: Telegram application instance
        lookback_hours: How many hours back to check
    """
    try:
        bot = app.bot
        now_utc = datetime.utcnow()
        current_hour = now_utc.hour
        
        print(f"[Missed Check] Checking for missed notifications in last {lookback_hours} hours...")
        
        all_users = get_all_active_users()
        if not all_users:
            print("[Missed Check] No active users")
            return
        
        # Get notification data
        try:
            notif_data = await get_notification_data(ttl=600)
        except Exception as e:
            print(f"[Missed Check] Failed to fetch data: {e}")
            return
        
        users_to_notify = []
        
        for user in all_users:
            try:
                user_id = user.get("user_id")
                if not user_id:
                    continue
                
                frequency = user.get("frequency")
                if frequency == "off":
                    continue
                
                last_hour = get_user_last_notified_hour(user_id)
                
                # Check each hour in lookback period
                for hours_ago in range(lookback_hours):
                    check_hour = (current_hour - hours_ago) % 24
                    
                    morning_hour = parse_hour(user.get("morning_time"))
                    evening_hour = parse_hour(user.get("evening_time"))
                    
                    should_have_been_sent = False
                    if frequency in ["once", "twice"] and morning_hour == check_hour:
                        should_have_been_sent = True
                    if frequency == "twice" and evening_hour == check_hour:
                        should_have_been_sent = True
                    
                    # If it should have been sent but wasn't
                    if should_have_been_sent and last_hour != check_hour:
                        users_to_notify.append((user, current_hour))
                        print(f"[Missed Check] Found missed notification for user {user_id}")
                        break  # Only add once
                        
            except Exception as e:
                print(f"[Missed Check] Error processing user {user.get('user_id')}: {e}")
                continue
        
        if users_to_notify:
            print(f"[Missed Check] Sending {len(users_to_notify)} missed notifications...")
            stats = await send_notifications_in_batches(
                bot,
                users_to_notify,
                notif_data,
                batch_size=20,
                delay_between_batches=2.0
            )
            print(f"[Missed Check] Results: {stats}")
        else:
            print("[Missed Check] No missed notifications found")
            
    except Exception as e:
        print(f"[Missed Check] Critical error: {e}")


# ============================================================================
# MAIN NOTIFICATION CHECK
# ============================================================================

async def check_notifications(app) -> None:
    """
    Main notification checking and sending function.
    Runs every hour to check and send notifications.
    
    Args:
        app: Telegram application instance
    """
    try:
        bot = app.bot
        now_utc = datetime.utcnow()
        current_utc_hour = now_utc.hour
        
        print(f"[Scheduler] Running notification check for UTC hour {current_utc_hour}:00")

        # Fetch active users
        all_users = get_all_active_users()
        if not all_users:
            print("[Scheduler] No active users found")
            return

        # Fetch notification data (cached for 10 minutes)
        try:
            notif_data = await get_notification_data(ttl=600)
        except Exception as e:
            print(f"[Scheduler] Failed to fetch notification data: {e}")
            notif_data = {
                "global": None,
                "gainers": [],
                "losers": [],
                "news": [],
                "gas": None,
                "cod": None
            }

        # Collect users who need notifications at this UTC hour
        users_to_notify = []

        for user in all_users:
            try:
                user_id = user.get("user_id")
                if not user_id:
                    continue

                # Get last notified hour from DB
                last_hour = get_user_last_notified_hour(user_id)

                # Check if user should be notified at current UTC hour
                if should_notify_user(user, current_utc_hour, last_hour):
                    users_to_notify.append((user, current_utc_hour))

            except Exception as e:
                print(f"[Scheduler] Error processing user {user.get('user_id')}: {e}")
                continue

        if not users_to_notify:
            print(f"[Scheduler] No users scheduled for UTC {current_utc_hour}:00")
            return

        print(f"[Scheduler] Sending notifications to {len(users_to_notify)} users")

        # Send notifications in batches with rate limiting
        stats = await send_notifications_in_batches(
            bot,
            users_to_notify,
            notif_data,
            batch_size=30,
            delay_between_batches=1.0
        )

        print(f"[Scheduler] Batch completed - Sent: {stats['sent']}, Failed: {stats['failed']}, Blocked: {stats['blocked']}")

    except Exception as e:
        print(f"[Scheduler] Critical error in check_notifications: {e}")


# ============================================================================
# PREVIEW COMMAND HELPER
# ============================================================================

async def generate_preview_message(user_settings: Dict[str, Any]) -> str:
    """
    Generate a preview of what the notification will look like.
    
    Args:
        user_settings: User's notification settings
        
    Returns:
        str: Preview message
    """
    try:
        notif_data = await get_notification_data(ttl=600)
        preview = await build_message(user_settings, notif_data)
        
        morning_time = user_settings.get("morning_time", "Not set")
        evening_time = user_settings.get("evening_time", "Not set")
        frequency = user_settings.get("frequency", "off")
        
        schedule_info = f"\n\n⏰ *Schedule (UTC):*\n"
        if frequency == "once":
            schedule_info += f"• Morning: {morning_time} UTC"
        elif frequency == "twice":
            schedule_info += f"• Morning: {morning_time} UTC\n• Evening: {evening_time} UTC"
        else:
            schedule_info += "• Notifications are OFF"
        
        return preview + schedule_info
        
    except Exception as e:
        print(f"[Preview] Error generating preview: {e}")
        return "❌ Could not generate preview. Please try again."


# ============================================================================
# EMERGENCY BROADCAST
# ============================================================================

async def send_emergency_broadcast(
    app,
    message: str,
    all_users: bool = True,
    user_ids: Optional[List[int]] = None
) -> Dict[str, int]:
    """
    Send immediate notification outside normal schedule.
    
    Args:
        app: Telegram application instance
        message: Message to broadcast
        all_users: Whether to send to all active users
        user_ids: Specific user IDs to send to (if all_users=False)
        
    Returns:
        dict: Statistics of broadcast
    """
    try:
        bot = app.bot
        
        if all_users:
            users = get_all_active_users()
        elif user_ids:
            users = [{"user_id": uid, "delivery": "private"} for uid in user_ids]
        else:
            return {"sent": 0, "failed": 0, "error": "No users specified"}
        
        print(f"[Broadcast] Sending emergency message to {len(users)} users")
        
        stats = {"sent": 0, "failed": 0, "blocked": 0}
        
        for user in users:
            success, error = await send_notification_with_retry(
                bot,
                user,
                message,
                disable_web_page_preview=False,
                max_retries=2
            )
            
            if success:
                stats["sent"] += 1
            else:
                if "blocked" in error.lower():
                    stats["blocked"] += 1
                else:
                    stats["failed"] += 1
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.1)
        
        print(f"[Broadcast] Completed - Sent: {stats['sent']}, Failed: {stats['failed']}, Blocked: {stats['blocked']}")
        return stats
        
    except Exception as e:
        print(f"[Broadcast] Error: {e}")
        return {"sent": 0, "failed": 0, "error": str(e)}


# ============================================================================
# SCHEDULER MANAGEMENT
# ============================================================================

def start_scheduler(app) -> AsyncIOScheduler:
    """
    Initialize and start the notification scheduler.
    Checks for notifications every hour at minute 0 UTC.
    
    Args:
        app: Telegram application instance
        
    Returns:
        AsyncIOScheduler: Started scheduler instance
    """
    global _scheduler
    
    if _scheduler is not None and _scheduler.running:
        print("[Scheduler] Scheduler already running")
        return _scheduler
    
    try:
        # Create scheduler
        _scheduler = AsyncIOScheduler(timezone=UTC)
        
        # Main notification check - every hour at :00
        _scheduler.add_job(
            check_notifications,
            trigger=CronTrigger(minute=0, timezone=UTC),
            args=[app],
            id='notification_checker',
            name='Hourly Notification Checker',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        # Start the scheduler
        _scheduler.start()
        print("[Scheduler] ✅ Notification scheduler started successfully")
        
        jobs = _scheduler.get_jobs()
        if jobs:
            print(f"[Scheduler] 📅 Next run at: {jobs[0].next_run_time}")
        
        # Run missed notification check on startup (after 30 seconds)
        asyncio.create_task(asyncio.sleep(30))
        asyncio.create_task(check_missed_notifications(app, lookback_hours=3))
        
        return _scheduler
        
    except Exception as e:
        print(f"[Scheduler] ❌ Failed to start scheduler: {e}")
        raise


def stop_scheduler() -> None:
    """
    Stop the notification scheduler gracefully.
    """
    global _scheduler
    
    if _scheduler is None:
        print("[Scheduler] No scheduler to stop")
        return
    
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=True)
            print("[Scheduler] ✅ Scheduler stopped successfully")
        _scheduler = None
    except Exception as e:
        print(f"[Scheduler] ❌ Error stopping scheduler: {e}")


def get_scheduler_status() -> Dict[str, Any]:
    """
    Get current scheduler status and job information.
    
    Returns:
        dict: Scheduler status information
    """
    global _scheduler
    
    if _scheduler is None:
        return {
            "running": False,
            "jobs": [],
            "status": "Not initialized"
        }
    
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {
        "running": _scheduler.running,
        "jobs": jobs,
        "status": "Running" if _scheduler.running else "Stopped",
        "timezone": "UTC"
    }


async def trigger_manual_check(app) -> Dict[str, Any]:
    """
    Manually trigger a notification check (useful for testing).
    
    Args:
        app: Telegram application instance
        
    Returns:
        dict: Result of manual check
    """
    try:
        print("[Scheduler] 🔧 Manual notification check triggered")
        await check_notifications(app)
        return {
            "success": True,
            "message": "Manual check completed"
        }
    except Exception as e:
        print(f"[Scheduler] ❌ Manual check failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }