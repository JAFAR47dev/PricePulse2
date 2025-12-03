import requests
import os
from utils.indicators import get_crypto_indicators
from utils.prices import get_crypto_prices
from models.user import get_user_plan
from utils.auth import is_pro_plan
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from models.user_activity import update_last_active
import json
import httpx

def safe(value):
    try:
        if value is None:
            return "N/A"
        return round(float(value), 4) if isinstance(value, (float, int)) else str(value)
    except:
        return "N/A"
        

# Load CoinGecko IDs mapping (top 200 coins)
COINGECKO_IDS_PATH = os.path.join("services", "coingecko_ids.json")
with open(COINGECKO_IDS_PATH, "r") as f:
    COINGECKO_ID_MAP = json.load(f)

async def get_coingecko_24h(coin_id: str, vs_currency="usd"):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": vs_currency,
        "ids": coin_id,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        if not data or len(data) == 0:
            return None
        coin = data[0]
        return {
            "high_24h": coin.get("high_24h"),
            "low_24h": coin.get("low_24h"),
            "volume_24h": coin.get("total_volume"),
            "current_price": coin.get("current_price"),
        }

async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/prediction")
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade to unlock.",
            parse_mode="Markdown"
        )
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: /prediction BTC [timeframe]\nExample: /prediction ETH 4h"
        )
        return

    symbol = args[0].upper()
    coin_id = COINGECKO_ID_MAP.get(symbol)
    if not coin_id:
        await update.message.reply_text(f"❌ Symbol `{symbol}` not supported for prediction.")
        return

    # Map timeframe
    timeframe_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "8h": "8h",
        "1d": "1day",
        "1w": "1week"
    }

    user_input_tf = args[1] if len(args) > 1 else "1h"
    if user_input_tf not in timeframe_map:
        await update.message.reply_text(
            "❌ Invalid timeframe. Use one of: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d, 1w"
        )
        return

    timeframe = timeframe_map[user_input_tf]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("🧠 Analyzing market conditions and predicting... Please wait...")

    # Fetch indicators
    indicators = await get_crypto_indicators(symbol, timeframe)
    if indicators is None:
        await update.message.reply_text("⚠️ Could not fetch indicator data for this coin.")
        return

    # Fetch 24h stats from CoinGecko
    stats_24h = await get_coingecko_24h(coin_id)
    if stats_24h is None:
        stats_24h = {"high_24h": "N/A", "low_24h": "N/A", "volume_24h": "N/A", "current_price": indicators.get("price")}

                
    prompt = f"""
You're a professional crypto market analyst. Using the live market data below, give a concise, realistic short-term outlook for {symbol} on the {timeframe} timeframe.

=== Market Data ===
• Price: ${safe(indicators.get('price'))}
• RSI (14): {safe(indicators.get('rsi'))}
• EMA(20): {safe(indicators.get('ema20'))}
• VWAP: {safe(indicators.get('vwap'))}

=== MACD Indicators ===
• MACD: {safe(indicators.get('macd'))}
• Signal: {safe(indicators.get('macdSignal'))}
• Histogram: {safe(indicators.get('macdHist'))}

=== Trend & Momentum Indicators ===
• Stochastic K / D: {safe(indicators.get('stochK'))} / {safe(indicators.get('stochD'))}
• CCI: {safe(indicators.get('cci'))}
• ATR: {safe(indicators.get('atr'))}
• ADX: {safe(indicators.get('adx'))}
• MFI: {safe(indicators.get('mfi'))}

=== Bollinger Bands ===
• Upper: ${safe(indicators.get('bbUpper'))}
• Middle: ${safe(indicators.get('bbMiddle'))}
• Lower: ${safe(indicators.get('bbLower'))}

=== 24H Statistics ===
• High / Low: ${stats_24h.get('high_24h', 'N/A')} / ${stats_24h.get('low_24h', 'N/A')}
• 24h Volume: ${stats_24h.get('volume_24h', 'N/A')}

=== Latest Candle ===
• Volume: ${stats_24h.get('volume_24h', 'N/A')}

=== Instructions ===
Provide a brief, human-like market outlook:
• Identify momentum (bullish, bearish, or neutral)
• Highlight key indicators (RSI, MACD, EMA, Stoch, CCI, ADX, VWAP)
• Mention any likely scenarios (breakout, pullback, sideways)
• Give a final directional prediction: UP, DOWN, or SIDEWAYS

Be concise and avoid exaggeration.
"""


    prediction = None

    try:
        fallback_response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=20
        )

        if fallback_response.status_code == 200:
            prediction = fallback_response.json()["choices"][0]["message"]["content"].strip()
        else:
            print("OpenRouter response error:", fallback_response.status_code, fallback_response.text)
            await update.message.reply_text("❌ Fallback model failed. Please try again later.")
            return

    except Exception as e:
            print("Fallback error:", e)
            await update.message.reply_text("❌ Fallback error occurred. Please try again later.")
            return

    await update.message.reply_text(
        f"📈 *AI Prediction for {symbol} ({timeframe}):*\n\n{prediction}\n\n"
        "⚠️ _Disclaimer: This prediction is generated by AI based on market data and does not constitute financial advice._",
        parse_mode="Markdown"
    )