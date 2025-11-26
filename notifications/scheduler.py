# notifications/scheduler.py

import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import UTC
from telegram import Bot
from notifications.models import get_all_active_users
from utils.timezone_utils import convert_to_local_hour
from notifications.services.notification_data import get_notification_data


# Cache notification messages per hour to avoid regenerating
notification_cache = {}


async def send_notification(bot: Bot, user: dict, message: str):
    """
    Send a notification respecting delivery method.
    Fully resilient: failures for one user won't affect others.
    """
    try:
        chat_id = None
        if user.get("delivery") == "private":
            chat_id = user.get("user_id")
        elif user.get("delivery") == "group":
            chat_id = user.get("group_id")

        if not chat_id:
            print(f"[Notification Warning] No valid chat_id for user {user.get('user_id')}")
            return False

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )
        return True

    except Exception as e:
        print(f"[Notification Error] Failed to send to {user.get('user_id')}: {e}")
        return False


from notifications.models import get_all_active_users, get_user_last_notified_hour, set_user_last_notified_hour
from utils.timezone_utils import convert_to_local_hour

async def check_notifications(app):
    bot = app.bot
    now_utc = datetime.utcnow()

    # Fetch active users
    all_users = get_all_active_users()
    if not all_users:
        return

    # --- Fetch cached notification data once per batch ---
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

    for user in all_users:
        if user.get("frequency") == "off":
            continue

        local_hour = convert_to_local_hour(user.get("timezone") or "UTC", utc_dt=now_utc)

        # --- Fetch last notified hour from DB ---
        last_hour = get_user_last_notified_hour(user["user_id"])

        # Skip if already notified in this hour
        if last_hour == local_hour:
            continue

        # --- Parse scheduled hours ---
        def parse_hour(time_str):
            if not time_str:
                return None
            return int(time_str.split(":")[0])

        morning_hour = parse_hour(user.get("morning_time"))
        evening_hour = parse_hour(user.get("evening_time"))

        notify = False
        if user["frequency"] in ["once", "twice"] and morning_hour == local_hour:
            notify = True
        if user["frequency"] == "twice" and evening_hour == local_hour:
            notify = True

        if notify:
            message = await build_user_notification_message(user, notif_data)
            success = await send_notification(bot, user, message)

            if success:
                # ✅ Save last notified hour in DB
                set_user_last_notified_hour(user["user_id"], local_hour)
                
# --- Build dynamic message per user safely ---
async def build_message(user):
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
            parts.append(f"🌍 {g}")

    # --- 🚀 Top Gainers ---
    if user.get("include_gainers") and notif_data.get("gainers"):
        gainers_data = notif_data["gainers"]
        if isinstance(gainers_data, list) and len(gainers_data) > 0:
            formatted = "\n".join(
                [f"• {c[0]} — 📈 *{c[1]}*" for c in gainers_data[:3]]
            )
            parts.append(f"\n🚀 *Top Gainers (24h)*\n{formatted}")
        else:
            parts.append(f"🚀 *Top Gainers:* {gainers_data}")

    # --- 📉 Top Losers ---
    if user.get("include_losers") and notif_data.get("losers"):
        losers_data = notif_data["losers"]
        if isinstance(losers_data, list) and len(losers_data) > 0:
            formatted = "\n".join(
                [f"• {c[0]} — 🔻 *{c[1]}*" for c in losers_data[:3]]
            )
            parts.append(f"\n📉 *Top Losers (24h)*\n{formatted}")
        else:
            parts.append(f"📉 *Top Losers:* {losers_data}")

    # --- 📰 News Section (Web Preview Disabled) ---
    if user.get("include_news") and notif_data.get("news"):
        news_data = notif_data["news"]
        if isinstance(news_data, list) and len(news_data) > 0:
            formatted = "\n".join(
                [f"• [{n.split('](')[0].replace('[', '').strip()}]({n.split('](')[1][:-1]})"
                 if '](' in n else f"• {n}" for n in news_data[:3]]
            )
            parts.append(f"\n📰 *Latest Crypto News*\n{formatted}")
        else:
            parts.append(f"📰 *News:* {news_data}")

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
        else:
            parts.append(f"\n💡 *Coin of the Day:* {cod_data}")

    return "\n".join(parts)


    # --- Send notifications concurrently ---
    await asyncio.gather(
        *(
            send_notification(
                bot,
                user,
                await build_message(user),
                disable_web_page_preview=True  # 🔒 Disable link previews for News section
            )
            for user in users_to_notify
        )
    )

# notifications/scheduler.py

from telegram.ext import JobQueue

def start_notifications_scheduler(app):
    """
    Schedule portfolio/notification checks using Telegram bot JobQueue.
    This runs every hour at the 0th minute (or adjust interval as needed).
    """

    # Interval in seconds (3600 = 1 hour)
    interval_seconds = 900

    # Schedule repeating job
    app.job_queue.run_repeating(
        callback=check_notifications,
        interval=interval_seconds,
        first=15, 
        name="notifications_scheduler",
        data=app, 
    )

    print("✅ Notifications scheduler started")
    
#import asyncio
#from apscheduler.schedulers.asyncio import AsyncIOScheduler

#async def start_notifications_scheduler(app):
#    """Start APScheduler to check notifications every hour at 0th minute."""
#    loop = asyncio.get_running_loop()  
#    scheduler = AsyncIOScheduler(event_loop=loop)

#    scheduler.add_job(
#        check_notifications,
#        'cron',
#        minute=0,
#        args=[app]
#    )
#    scheduler.start()
#    print("Notifications scheduler started")
#    
#def start_notifications_scheduler(app):
#    """Start APScheduler to check notifications every hour at 0th minute."""
#    # Ensure event loop exists (fixes Pydroid3 RuntimeError)
#    try:
#        loop = asyncio.get_event_loop()
#    except RuntimeError:
#        loop = asyncio.new_event_loop()
#        asyncio.set_event_loop(loop)

#    # Schedule the hourly job
#    scheduler.add_job(
#        lambda: asyncio.create_task(check_notifications(app)),
#        'cron',
#        minute=0  # Every hour
#    )
#    scheduler.start()
#    print("Notifications scheduler started")