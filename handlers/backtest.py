from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from models.user import get_user_plan
from utils.auth import is_pro_plan
from utils.ohlcv import fetch_candles
from utils.formatting import format_large_number
from models.user_activity import update_last_active

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

def simulate_rsi_strategy(candles, stop_loss_pct=3, take_profit_pct=6):
    """
    Simulate an RSI-based trading strategy with stop-loss and take-profit.

    Args:
        candles (list): List of candle dicts with "close" and "rsi".
        stop_loss_pct (float): Stop-loss threshold in percent.
        take_profit_pct (float): Take-profit threshold in percent.

    Returns:
        dict: Summary stats (via compute_stats)
    """

    wins = 0
    losses = 0
    entry_price = None
    returns = []

    for i in range(1, len(candles)):
        rsi = candles[i].get("rsi")
        close = candles[i].get("close")

        if rsi is None or close is None:
            continue

        # === BUY CONDITION ===
        if rsi < 30 and entry_price is None:
            entry_price = close
            entry_index = i

        # === TRADE MANAGEMENT ===
        elif entry_price is not None:
            change_pct = ((close - entry_price) / entry_price) * 100

            # Stop-loss hit
            if change_pct <= -stop_loss_pct:
                returns.append(change_pct)
                losses += 1
                entry_price = None

            # Take-profit hit
            elif change_pct >= take_profit_pct:
                returns.append(change_pct)
                wins += 1
                entry_price = None

            # RSI exit condition (overbought)
            elif rsi > 70:
                returns.append(change_pct)
                if change_pct > 0:
                    wins += 1
                else:
                    losses += 1
                entry_price = None

    # Close unclosed position at last candle
    if entry_price:
        final_close = candles[-1]["close"]
        final_ret = ((final_close - entry_price) / entry_price) * 100
        returns.append(final_ret)
        if final_ret > 0:
            wins += 1
        else:
            losses += 1

    return compute_stats(wins, losses, returns)
    
import statistics

def simulate_macd_strategy(candles, stop_loss_pct=3, take_profit_pct=6):
    """
    Simulate a MACD crossover strategy with stop-loss and take-profit handling.
    
    Args:
        candles (list): List of dicts containing 'macd', 'macdSignal', and 'close'.
        stop_loss_pct (float): Stop-loss threshold in percent.
        take_profit_pct (float): Take-profit threshold in percent.
    """
    wins = 0
    losses = 0
    entry_price = None
    returns = []

    for i in range(1, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]

        # Ensure MACD data exists
        if not all(k in prev for k in ["macd", "macdSignal", "close"]) or not all(k in curr for k in ["macd", "macdSignal", "close"]):
            continue

        macd_prev = prev["macd"]
        signal_prev = prev["macdSignal"]
        macd = curr["macd"]
        signal = curr["macdSignal"]
        close = curr["close"]

        # === BUY SIGNAL === (MACD crosses above Signal)
        if macd_prev < signal_prev and macd > signal and entry_price is None:
            entry_price = close

        # === TRADE MANAGEMENT ===
        elif entry_price is not None:
            change_pct = ((close - entry_price) / entry_price) * 100

            # Stop-loss triggered
            if change_pct <= -stop_loss_pct:
                returns.append(change_pct)
                losses += 1
                entry_price = None

            # Take-profit triggered
            elif change_pct >= take_profit_pct:
                returns.append(change_pct)
                wins += 1
                entry_price = None

            # === SELL SIGNAL === (MACD crosses below Signal)
            elif macd_prev > signal_prev and macd < signal:
                returns.append(change_pct)
                if change_pct > 0:
                    wins += 1
                else:
                    losses += 1
                entry_price = None

    # Close any open trade at the last candle
    if entry_price:
        final_close = candles[-1]["close"]
        final_ret = ((final_close - entry_price) / entry_price) * 100
        returns.append(final_ret)
        if final_ret > 0:
            wins += 1
        else:
            losses += 1

    return compute_stats(wins, losses, returns)

import statistics

def simulate_ema_strategy(candles, stop_loss_pct=3, take_profit_pct=6):
    """
    Simulate a simple EMA crossover strategy:
    - Buy when price crosses above EMA
    - Sell when price crosses below EMA
    - Uses stop-loss and take-profit for realism
    """
    wins = 0
    losses = 0
    entry_price = None
    returns = []

    for i in range(1, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]

        if not all(k in prev for k in ["close", "ema"]) or not all(k in curr for k in ["close", "ema"]):
            continue

        prev_close = prev["close"]
        prev_ema = prev["ema"]
        close = curr["close"]
        ema = curr["ema"]

        # === BUY SIGNAL: price crosses above EMA ===
        if prev_close < prev_ema and close > ema and entry_price is None:
            entry_price = close

        # === TRADE MANAGEMENT ===
        elif entry_price is not None:
            change_pct = ((close - entry_price) / entry_price) * 100

            # Stop-loss hit
            if change_pct <= -stop_loss_pct:
                returns.append(change_pct)
                losses += 1
                entry_price = None

            # Take-profit hit
            elif change_pct >= take_profit_pct:
                returns.append(change_pct)
                wins += 1
                entry_price = None

            # === SELL SIGNAL: price crosses below EMA ===
            elif prev_close > prev_ema and close < ema:
                returns.append(change_pct)
                if change_pct > 0:
                    wins += 1
                else:
                    losses += 1
                entry_price = None

    # === Close remaining trade at the last candle ===
    if entry_price:
        final_close = candles[-1]["close"]
        final_ret = ((final_close - entry_price) / entry_price) * 100
        returns.append(final_ret)
        if final_ret > 0:
            wins += 1
        else:
            losses += 1

    return compute_stats(wins, losses, returns)
    
    
def compute_stats(wins, losses, returns):
    import statistics

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
        "win_rate": round(win_rate, 2),
        "avg_return": round(avg_return, 2),
        "avg_gain": round(avg_gain, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
    }

async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/bt")
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
            "❌ Usage: /bt BTC [timeframe] [strategy]\nExample: /bt ETH 1h rsi"
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

    # ✅ Dynamic candle limits per timeframe
    CANDLE_LIMITS = {
        "1m": 2000,
        "5m": 1500,
        "15m": 1500,
        "30m": 1000,
        "1h": 1000,
        "2h": 800,
        "4h": 600,
        "8h": 500,
        "1d": 400
    }

    limit = CANDLE_LIMITS.get(timeframe, 1000)

    await update.message.reply_text(f"📊 Fetching {limit} candles for {symbol} ({timeframe})...")

    # Pass limit to your fetch_candles() function
    candles = await fetch_candles(symbol, timeframe, limit=limit)

    # Ensure we have enough data
    if not candles or len(candles) < limit * 0.8:
        return await update.message.reply_text(
            "⚠️ Failed to fetch enough historical data. Try another coin or timeframe."
        )

    await update.message.reply_text(
        f"📈 Backtesting *{strategy_type.upper()}* strategy on {symbol} ({timeframe})...",
        parse_mode=ParseMode.MARKDOWN
    )

    # Run selected backtest simulation
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
