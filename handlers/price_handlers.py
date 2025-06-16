from telegram import Update
from telegram.ext import ContextTypes
from services.price_service import get_crypto_price


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usage: /price <symbol>\nExample: /price BTCUSDT")
        return

    symbol = context.args[0].upper()
    price = get_cached_price(symbol)

    if price is not None:
        await update.message.reply_text(f"💰 *{symbol} Price:* ${price:.2f}", parse_mode="Markdown")

        # Generate and send chart
        url = f"https://min-api.cryptocompare.com/data/v2/histohour?fsym={symbol}&tsym=USD&limit=24"
        headers = {"authorization": f"Apikey {CRYPTOCOMPARE_API_KEY}"}
        try:
            response = requests.get(url, headers=headers)
            closes = [item["close"] for item in response.json()["Data"]["Data"]]
            chart_url = generate_price_chart(symbol, closes)
            await update.message.reply_photo(photo=chart_url, caption=f"{symbol} – 24h Price Trend")
        except Exception as e:
            print(f"Chart generation failed: {e}")
    else:
        await update.message.reply_text("⚠️ Couldn't fetch the price. Please try again later.")
        
from telegram.ext import CommandHandler

def register_price_handlers(app):
    app.add_handler(CommandHandler("price", price))
