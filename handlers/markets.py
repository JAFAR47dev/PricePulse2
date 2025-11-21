# handlers/markets.py
import requests
import json
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load CoinGecko ID mappings
with open("utils/coingecko_ids.json", "r") as f:
    COINGECKO_IDS = json.load(f)

async def markets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    if len(context.args) != 1:
        return await update.message.reply_text("❌ Usage: /markets [coin]")

    symbol = context.args[0].upper()
    coin_id = COINGECKO_IDS.get(symbol)

    if not coin_id:
        return await update.message.reply_text("❌ Unsupported or unknown coin symbol.")

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
    params = {"include_exchange_logo": False}

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        tickers = data.get("tickers", [])

        if not tickers:
            return await update.message.reply_text("❌ No market data found for that coin.")

        results = []
        for t in tickers[:10]:  # Top 10
            market = t.get("market", {}).get("name")
            pair = f"{t['base']}/{t['target']}"
            price = t.get("last")
            volume = t.get("volume")
            results.append((market, pair, price, volume))

        results.sort(key=lambda x: x[2], reverse=True)
        highest = results[0][2]
        lowest = results[-1][2]
        spread = highest - lowest
        spread_pct = (spread / lowest) * 100 if lowest else 0

        text = f"🌍 *{symbol} Market Prices*\n"
        text += f"🔺 Highest: ${highest:,.2f} | 🔻 Lowest: ${lowest:,.2f} | Spread: {spread_pct:.2f}%\n\n"

        for m in results:
            text += f"📈 {m[0]}: {m[1]} = *${m[2]:,.2f}* (Vol: {m[3]:,.0f})\n"

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Markets error:", e)
        await update.message.reply_text("⚠️ Couldn't fetch market data. Try another coin.")