# handlers/markets.py
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

async def markets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /markets [coin]")

    coin = context.args[0].lower()

    url = f"https://api.coingecko.com/api/v3/coins/{coin}/tickers"
    params = {"include_exchange_logo": False}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        tickers = data.get("tickers", [])

        if not tickers:
            return await update.message.reply_text("❌ No market data found for that coin.")

        # Group by exchange and get latest price
        results = []
        for t in tickers[:10]:  # Limit to top 10
            market = t.get("market", {}).get("name")
            pair = f"{t['base']}/{t['target']}"
            price = t.get("last")
            volume = t.get("volume")
            results.append((market, pair, price, volume))

        # Sort by price (optional)
        results.sort(key=lambda x: x[2], reverse=True)
        highest = results[0][2]
        lowest = results[-1][2]
        spread = highest - lowest
        spread_pct = (spread / lowest) * 100 if lowest else 0

        text = f"🌍 *{coin.upper()} Market Prices*\n"
        text += f"🔺 Highest: ${highest:,.2f} | 🔻 Lowest: ${lowest:,.2f} | Spread: {spread_pct:.2f}%\n\n"

        for m in results:
            text += f"📈 {m[0]}: {m[1]} = *${m[2]:,.2f}* (Vol: {m[3]:,.0f})\n"

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Markets error:", e)
        await update.message.reply_text("⚠️ Couldn't fetch market data. Try another coin.")