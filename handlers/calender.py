# handlers/calendar.py
import os
import datetime
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
COINDAR_API_KEY = os.getenv("COINDAR_API_KEY")

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        today = datetime.date.today()
        end_date = today + datetime.timedelta(days=14)

        url = "https://coindar.org/api/v2/events"
        params = {
            "access_token": COINDAR_API_KEY,
            "start_date": today.isoformat(),
            "end_date": end_date.isoformat(),
            "sort_by": "date",
            "limit": 10,
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        events = response.json()

        if not events:
            return await update.message.reply_text("✅ No major events in the next 14 days.")

        text = "📆 *Upcoming Events (Next 14 Days)*\n\n"
        for event in events:
            coin_name = event.get("coin", {}).get("name", "Unknown")
            symbol = event.get("coin", {}).get("symbol", "").upper()
            event_date = event.get("date")
            caption = event.get("caption", "No details")
            days_left = (datetime.datetime.strptime(event_date, "%Y-%m-%d").date() - today).days

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