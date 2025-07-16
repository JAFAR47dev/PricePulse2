# handlers/fxcal.py
import os
import datetime
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY")

async def fxcal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        today = datetime.date.today()
        end = today + datetime.timedelta(days=7)

        url = "https://finnhub.io/api/v1/calendar/economic"
        params = {
            "from": today.isoformat(),
            "to": end.isoformat(),
            "token": FINNHUB_KEY
        }

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("calendar", [])

        if not data:
            return await update.message.reply_text("✅ No economic events in the next 7 days.")

        text = "📅 *Upcoming Economic Events (Next 7 Days)*\n\n"
        count = 0

        for ev in data:
            evt = ev.get("event")
            country = ev.get("country")
            date = ev.get("date")
            impact = ev.get("impact")
            actual = ev.get("actual", "")
            forecast = ev.get("forecast", "")
            previous = ev.get("previous", "")

            # Impact indicator
            emoji = "🔴" if impact == "high" else "🟠" if impact == "medium" else "🟢"

            text += (
                f"{emoji} *{evt}* ({country})\n"
                f"📅 {date}\n"
            )
            if forecast: text += f"🔮 Forecast: {forecast}\n"
            if actual: text += f"✅ Actual: {actual}\n"
            if previous: text += f"📉 Previous: {previous}\n"
            text += "\n"

            count += 1
            if count >= 10: break

        await update.message.reply_text(text.strip(), parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("FX Calendar error:", e)
        await update.message.reply_text("⚠️ Could not load events. Try again later.")