from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from models.user import get_user_plan
from utils.auth import is_pro_plan
from utils.ohlcv import fetch_candles
from utils.formatting import format_large_number


import statistics
import os
import requests
from dotenv import load_dotenv

load_dotenv()

VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]
VALID_STRATEGIES = ["rsi", "macd", "ema"]

def calculate_rsi(closes, period=14):
    gains = []
    losses = []

    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
        else:
            losses.append(abs(change))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def simulate_rsi_strategy(candles):
    wins = 0
    losses = 0
    entry_price = None
    returns = []

    for i in range(1, len(candles)):
        rsi = candles[i].get("rsi")
        close = candles[i].get("close")
        if rsi is None or close is None:
            continue

        if rsi < 30 and entry_price is None:
            entry_price = close

        elif rsi > 70 and entry_price:
            ret = ((close - entry_price) / entry_price) * 100
            returns.append(ret)

            if ret > 0:
                wins += 1
            else:
                losses += 1

            entry_price = None

    return compute_stats(wins, losses, returns)

def simulate_macd_strategy(candles):
    wins = 0
    losses = 0
    entry_price = None
    returns = []

    for i in range(1, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]

        if not all(k in prev for k in ["macd", "macdSignal", "close"]) or not all(k in curr for k in ["macd", "macdSignal", "close"]):
            continue

        macd_prev = prev["macd"]
        signal_prev = prev["macdSignal"]
        macd = curr["macd"]
        signal = curr["macdSignal"]
        close = curr["close"]

        if macd_prev < signal_prev and macd > signal and entry_price is None:
            entry_price = close

        elif macd_prev > signal_prev and macd < signal and entry_price:
            ret = ((close - entry_price) / entry_price) * 100
            returns.append(ret)

            if ret > 0:
                wins += 1
            else:
                losses += 1

            entry_price = None

    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades else 0
    avg_return = statistics.mean(returns) if returns else 0
    avg_gain = statistics.mean([r for r in returns if r > 0]) if wins else 0
    avg_loss = statistics.mean([abs(r) for r in returns if r < 0]) if losses else 0
    profit_factor = sum(r for r in returns if r > 0) / (sum(abs(r) for r in returns if r < 0) + 1e-6)
    sharpe_ratio = avg_return / (statistics.stdev(returns) + 1e-6) if len(returns) > 1 else 0
    win_loss_ratio = wins / losses if losses else float('inf')

    return {
        "trades": total_trades,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "avg_gain": avg_gain,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "win_loss_ratio": win_loss_ratio,
    }

def simulate_ema_strategy(candles):
    entry_price = None
    returns = []

    for c in candles:
        if "close" not in c or "ema" not in c:
            continue

        price = c["close"]
        ema = c["ema"]

        if entry_price is None and price > ema:
            entry_price = price

        elif entry_price is not None and price < ema:
            ret = ((price - entry_price) / entry_price) * 100
            returns.append(ret)
            entry_price = None

    wins = sum(1 for r in returns if r > 0)
    losses = sum(1 for r in returns if r < 0)
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades else 0
    avg_return = statistics.mean(returns) if returns else 0
    avg_gain = statistics.mean([r for r in returns if r > 0]) if wins else 0
    avg_loss = statistics.mean([abs(r) for r in returns if r < 0]) if losses else 0
    profit_factor = sum(r for r in returns if r > 0) / (sum(abs(r) for r in returns if r < 0) + 1e-6)
    sharpe_ratio = avg_return / (statistics.stdev(returns) + 1e-6) if len(returns) > 1 else 0
    win_loss_ratio = wins / losses if losses else float('inf')

    return {
        "trades": total_trades,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "avg_gain": avg_gain,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "win_loss_ratio": win_loss_ratio,
    }
    
def compute_stats(wins, losses, returns):
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    avg_return = statistics.mean(returns) if returns else 0
    avg_gain = statistics.mean([r for r in returns if r > 0]) if wins else 0
    avg_loss = statistics.mean([abs(r) for r in returns if r < 0]) if losses else 0
    profit_factor = (sum(r for r in returns if r > 0)) / (sum(abs(r) for r in returns if r < 0) + 1e-6)
    sharpe_ratio = avg_return / (statistics.stdev(returns) + 1e-6) if len(returns) > 1 else 0
    win_loss_ratio = wins / losses if losses > 0 else float('inf')

    return {
        "trades": total_trades,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "avg_gain": avg_gain,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "win_loss_ratio": win_loss_ratio,
    }

async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This is a *Pro-only* feature.\nUpgrade to unlock AI backtesting.\n\n👉 /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = context.args
    if len(args) < 1:
        return await update.message.reply_text(
            "❌ Usage: /backtest BTC [timeframe] [strategy]\nExample: /backtest ETH 1h rsi"
        )

    symbol = args[0].upper()
    timeframe = args[1] if len(args) > 1 else "1h"
    strategy_type = args[2].lower() if len(args) > 2 else "rsi"

    if timeframe not in VALID_TIMEFRAMES:
        return await update.message.reply_text(
            "❌ Invalid timeframe. Use one of:\n1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d"
        )

    if strategy_type not in VALID_STRATEGIES:
        return await update.message.reply_text(
            "❌ Invalid strategy. Choose one of: `rsi`, `macd`, `ema`",
            parse_mode=ParseMode.MARKDOWN
        )

    await update.message.reply_text("📊 Fetching historical data for backtest...")

    candles = await fetch_candles(symbol, timeframe)
    


    if not candles or len(candles) < 1900:
        return await update.message.reply_text("⚠️ Failed to fetch enough historical data. Try another coin or timeframe.")

    await update.message.reply_text(f"📈 Backtesting *{strategy_type.upper()}* strategy...", parse_mode=ParseMode.MARKDOWN)

    if strategy_type == "rsi":
        results = simulate_rsi_strategy(candles)
    elif strategy_type == "macd":
        results = simulate_macd_strategy(candles)
    elif strategy_type == "ema":
        results = simulate_ema_strategy(candles)
    
    await update.message.reply_text(
        f"📊 *Backtest Results for {symbol} ({timeframe}):*\n\n"
        f"🎯 Strategy: `{strategy_type.upper()}`\n"
        f"🔁 Trades: {results['trades']}\n"
        f"✅ Win Rate: {results['win_rate']:.2f}%\n"
        f"📈 Avg Return: {results['avg_return']:.2f}%\n"
        f"📊 Profit Factor: {results['profit_factor']:.2f}\n"
        f"📏 Sharpe Ratio: {results['sharpe_ratio']:.2f}\n",
        parse_mode=ParseMode.MARKDOWN
    )

    ai_summary = await get_ai_backtest_summary(
        symbol, timeframe, strategy_type,
        results["trades"], results["win_rate"], results["avg_return"],
        results["avg_gain"], results["avg_loss"],
        results["profit_factor"], results["sharpe_ratio"], results["win_loss_ratio"]
    )
    
    
    if ai_summary:
        await update.message.reply_text(
            f"🤖 *AI Summary:*\n\n{ai_summary}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("⚠️ AI summary failed. Please try again later.")
        



async def get_ai_backtest_summary(
    symbol, timeframe, strategy_type, total_trades, win_rate,
    avg_return, avg_gain, avg_loss, profit_factor, sharpe_ratio, win_loss_ratio
):
    prompt = f"""
You are a crypto trading assistant.

A user just ran a backtest using this data:

- Coin: {symbol}
- Timeframe: {timeframe}
- Strategy: {strategy_type.upper()}

📊 Performance Metrics:
- Total Trades: {total_trades}
- Win Rate: {win_rate:.2f}%
- Avg Return per Trade: {avg_return:.2f}%
- Avg Gain: {avg_gain:.2f}%
- Avg Loss: -{avg_loss:.2f}%
- Profit Factor: {profit_factor:.2f}
- Sharpe Ratio: {sharpe_ratio:.2f}
- Win/Loss Ratio: {win_loss_ratio:.2f}

📈 Give a brief but useful analysis of:
1. What the result says about this strategy’s performance.
2. Whether it seems profitable or risky.
3. Tips for using it in real trading (risk mgmt, when to use, what to avoid).

Be concise, actionable, and realistic. Limit response to 200 words.
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()

        print("AI summary error:", response.status_code, response.text)
        return None

    except Exception as e:
        print("AI summary exception:", e)
        return None
