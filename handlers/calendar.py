import os
import datetime
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from utils.coin_cache import load_coin_map

load_dotenv()
COINDAR_API_KEY = os.getenv("COINDAR_API_KEY")

# Cache coin map globally
coin_map = {}

def fetch_coin_map():
    try:
        url = "https://coindar.org/api/v2/coins"
        params = {"access_token": COINDAR_API_KEY}
        r = requests.get(url, params=params)
        r.raise_for_status()
        coins = r.json()
        return {str(c["id"]): {"name": c["name"], "symbol": c["symbol"]} for c in coins}
    except Exception as e:
        print("❌ Failed to fetch coin map:", e)
        return {}

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global coin_map
    try:
        if not COINDAR_API_KEY:
            return await update.message.reply_text("❌ Calendar API key missing.")

        # Load coin map if not yet loaded
       
        coin_map = load_coin_map()

        today = datetime.date.today()
        end_date = today + datetime.timedelta(days=14)

        url = "https://coindar.org/api/v2/events"
        params = {
            "access_token": COINDAR_API_KEY,
            "start_date": today.isoformat(),
            "end_date": end_date.isoformat(),
            "limit": 15  # Reduced to avoid overload
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        if not response.text.strip():
            return await update.message.reply_text("⚠️ No response from Coindar.")

        events = response.json()
        if not events:
            return await update.message.reply_text("✅ No major events in the next 14 days.")

        # Filter only future events based on `date_start`
        upcoming = []
        for e in events:
            date_str = e.get("date_start") or e.get("date_public")
            try:
                event_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                if event_date >= today:
                    upcoming.append((event_date, e))
            except:
                continue

        if not upcoming:
            return await update.message.reply_text("✅ No upcoming events in the next 14 days.")

        # Sort by date
        upcoming.sort(key=lambda x: x[0])

        text = "📆 *Upcoming Events (Next 14 Days)*\n\n"
        for event_date, event in upcoming[:10]:  # Limit to 10 events
            coin_id = event.get("coin_id", "")
            coin = coin_map.get(str(coin_id), {"name": "Unknown", "symbol": ""})
            coin_name = coin["name"]
            symbol = coin["symbol"].upper()

            caption = event.get("caption", "No details")
            days_left = (event_date - today).days

            text += (
                f"🔔 *{coin_name} ({symbol})*\n"
                f"Event: {caption}\n"
                f"📅 {event_date} ({days_left} days left)\n\n"
            )

        text += "👉 Get alerts on these events with Pro: /upgrade@EliteTradeSignalBot"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Calendar error:", e)
        await update.message.reply_text("⚠️ Couldn't load calendar events. Try again later.")