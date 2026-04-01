# notifications/detector.py
#
# Compares the live screener cache against every user's active signal alerts
# and returns a list of pending notifications ready to send.
#
# This file has NO Telegram imports — it is pure logic.
# The dispatcher (dispatcher.py) handles all actual sending.
#
# Called from: screener_job.py after every precompute_all_coins() call.

from typing import List, Dict, Any
from services.screener_engine import get_precomputed_results
from notifications.db import (
    get_all_active_alerts,
    was_recently_alerted,
)

# All valid values — used to expand 'ANY' wildcards
_ALL_STRATEGIES = ["strat_1", "strat_2", "strat_3", "strat_4", "strat_5"]
_ALL_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]

STRATEGY_NAMES = {
    "strat_1": "Strong Bounce Setup",
    "strat_2": "Breakout with Momentum",
    "strat_3": "Reversal After Sell-Off",
    "strat_4": "Trend Turning Bullish",
    "strat_5": "Deep Pullback Opportunity",
}


def check_all_alerts() -> List[Dict[str, Any]]:
    """
    Main entry point. Called after every screener precompute.

    Iterates every active signal_alert row, checks it against the
    current precomputed screener cache, and returns all alerts
    that should be sent right now.

    Returns a flat list of dicts, one per notification to send:
    {
        user_id, alert_id, symbol, strategy_key, strategy_name,
        timeframe, score, price, rsi, cooldown_minutes
    }
    """
    alerts = get_all_active_alerts()
    if not alerts:
        return []

    pending = []

    for alert in alerts:
        user_id       = alert["user_id"]
        symbol        = alert["symbol"]        # 'BTC' or 'ANY'
        strategy_key  = alert["strategy_key"]  # 'strat_1' or 'ANY'
        timeframe     = alert["timeframe"]     # '1h' or 'ANY'
        min_score     = alert["min_score"]
        cooldown      = alert["cooldown_minutes"]
        alert_id      = alert["id"]

        # Expand wildcards
        strategies = _ALL_STRATEGIES if strategy_key == "ANY" else [strategy_key]
        timeframes = _ALL_TIMEFRAMES if timeframe == "ANY" else [timeframe]

        for strat in strategies:
            for tf in timeframes:
                results = get_precomputed_results(strat, tf)
                if not results:
                    continue

                for coin in results:
                    coin_symbol = coin.get("symbol", "")

                    # Filter by coin if not wildcard
                    if symbol != "ANY" and coin_symbol != symbol:
                        continue

                    # Filter by minimum score
                    if coin.get("score", 0) < min_score:
                        continue

                    # Cooldown check — skip if already sent recently
                    if was_recently_alerted(
                        user_id, coin_symbol, strat, tf, cooldown
                    ):
                        continue

                    pending.append({
                        "user_id":       user_id,
                        "alert_id":      alert_id,
                        "symbol":        coin_symbol,
                        "strategy_key":  strat,
                        "strategy_name": STRATEGY_NAMES.get(strat, strat),
                        "timeframe":     tf,
                        "score":         coin.get("score"),
                        "price":         coin.get("close"),
                        "rsi":           coin.get("rsi"),
                        "cooldown_minutes": cooldown,
                    })

    return pending


def build_daily_brief(timeframe: str = "1h") -> Dict[str, Any]:
    """
    Aggregates screener results across all 5 strategies for a given timeframe
    into a single composite picture for the daily brief.

    Returns:
    {
        "top": [   top 3 coins by composite score  ],
        "weak": [  bottom 3 coins — lowest/no score ],
        "total_scanned": 100,
        "total_matches": 14,
        "best_timeframe": "4h",   # whichever TF had most matches
        "timeframe": "1h"
    }

    Each coin entry:
    {
        symbol, composite_score, best_strategy, best_strategy_name,
        timeframe, price, rsi, signal_summary
    }
    """
    # ------------------------------------------------------------------
    # Step 1: Collect raw scores across all strategies for this timeframe
    # ------------------------------------------------------------------
    coin_scores: Dict[str, Dict] = {}

    for strat in _ALL_STRATEGIES:
        results = get_precomputed_results(strat, timeframe)
        if not results:
            continue

        for coin in results:
            symbol = coin.get("symbol", "")
            score  = coin.get("score", 0)

            if symbol not in coin_scores:
                coin_scores[symbol] = {
                    "symbol":       symbol,
                    "price":        coin.get("close"),
                    "rsi":          coin.get("rsi"),
                    "scores":       {},   # strat -> score
                    "timeframe":    timeframe,
                }

            coin_scores[symbol]["scores"][strat] = score

    # ------------------------------------------------------------------
    # Step 2: Compute composite score and pick best strategy per coin
    # ------------------------------------------------------------------
    ranked = []

    for symbol, data in coin_scores.items():
        scores = data["scores"]
        composite = sum(scores.values())
        best_strat = max(scores, key=scores.get)
        best_score = scores[best_strat]

        # Build a plain-English signal summary from the best strategy
        signal_summary = _build_signal_summary(best_strat, data.get("rsi"))

        ranked.append({
            "symbol":              symbol,
            "composite_score":     composite,
            "best_strategy":       best_strat,
            "best_strategy_name":  STRATEGY_NAMES.get(best_strat, best_strat),
            "best_score":          best_score,
            "timeframe":           timeframe,
            "price":               data.get("price"),
            "rsi":                 data.get("rsi"),
            "signal_summary":      signal_summary,
        })

    ranked.sort(key=lambda x: -x["composite_score"])

    # ------------------------------------------------------------------
    # Step 3: Find which timeframe had the most total matches today
    #         (used in the brief footer as context)
    # ------------------------------------------------------------------
    best_tf = _find_best_timeframe()

    # ------------------------------------------------------------------
    # Step 4: Build weak list — coins with 0 strategy matches
    #         We don't have the full 100-coin list here so we proxy:
    #         coins that appeared but scored lowest
    # ------------------------------------------------------------------
    if len(ranked) >= 6:
        weak = ranked[-3:]
        weak = list(reversed(weak))  # worst first
    else:
        weak = []

    total_matches = len(ranked)

    return {
        "top":            ranked[:3],
        "weak":           weak,
        "total_scanned":  100,
        "total_matches":  total_matches,
        "best_timeframe": best_tf,
        "timeframe":      timeframe,
    }


def _build_signal_summary(strategy_key: str, rsi: float = None) -> str:
    """
    Returns a one-line plain-English reason string for why this coin scored.
    Used in the daily brief coin entries.
    """
    rsi_note = ""
    if rsi is not None:
        if rsi < 35:
            rsi_note = f", RSI {rsi:.0f} oversold"
        elif rsi > 65:
            rsi_note = f", RSI {rsi:.0f} overbought"
        else:
            rsi_note = f", RSI {rsi:.0f}"

    summaries = {
        "strat_1": f"Near support, bounce signals{rsi_note}",
        "strat_2": f"Breaking above EMA, volume rising{rsi_note}",
        "strat_3": f"Oversold, reversal pattern forming{rsi_note}",
        "strat_4": f"MACD crossover, trend shifting up{rsi_note}",
        "strat_5": f"Healthy pullback in uptrend{rsi_note}",
    }
    return summaries.get(strategy_key, f"Technical setup detected{rsi_note}")


def _find_best_timeframe() -> str:
    """
    Returns the timeframe with the most total strategy matches right now.
    Used as the 'Best timeframe today' line in the daily brief.
    """
    counts = {}
    for tf in _ALL_TIMEFRAMES:
        total = 0
        for strat in _ALL_STRATEGIES:
            results = get_precomputed_results(strat, tf)
            if results:
                total += len(results)
        counts[tf] = total

    if not counts:
        return "1h"

    return max(counts, key=counts.get)
