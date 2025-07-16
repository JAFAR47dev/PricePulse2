# services/strategy_checker.py
import asyncio
from telegram import Bot
from models.db import get_connection
from utils.indicators import get_crypto_indicators

async def check_ai_strategies(bot: Bot):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id, symbol, condition_text FROM ai_alerts")
    rows = cursor.fetchall()

    for row in rows:
        alert_id, user_id, symbol, condition_text = row
        print(f"🔍 Checking strategy for {symbol}: {condition_text}")

        indicators = await get_crypto_indicators(symbol)
        if not indicators:
            print("⚠️ Could not fetch indicators")
            continue

        # --- Evaluate condition using OpenRouter again ---
        try:
            import os
            import requests

            prompt = f"""
You're an alert evaluator. A user saved the strategy:

"{condition_text}"

Here is the latest market data:
- Price: {indicators['price']}
- RSI: {indicators['rsi']}
- EMA(20): {indicators['ema20']}
- MACD: {indicators['macd']}
- MACD Histogram: {indicators['macdHist']}
- 7d Average Price: {indicators.get('sma_7d')}
- 24h High: {indicators['high_24h']}
- 24h Low: {indicators['low_24h']}
- Volume: {indicators['volume']}

Does the strategy trigger now? Only reply with: YES or NO.
"""

            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "mistralai/mixtral-8x7b-instruct",
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=15
            )

            if res.status_code == 200:
                reply = res.json()["choices"][0]["message"]["content"].strip().lower()

                if reply.startswith("yes"):
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"✅ *Strategy Triggered!*\n\n{condition_text}",
                        parse_mode="Markdown"
                    )

                    # Optional: remove or mark alert
                    cursor.execute("DELETE FROM ai_alerts WHERE id = ?", (alert_id,))
                    conn.commit()

        except Exception as e:
            print("Strategy evaluation failed:", e)

    conn.close()