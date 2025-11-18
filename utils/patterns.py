# utils/patterns.py
from typing import List, Dict, Any
import math

def detect_divergences(candles):
    """
    Detect true bullish/bearish divergences between price and RSI.
    Identifies local swing highs/lows in the last 50 candles.
    Returns list of detected patterns.
    """
    if len(candles) < 30:
        return []

    patterns = []
    recent = candles[-50:]

    closes = [float(c["close"]) for c in recent if "rsi" in c]
    rsis = [float(c["rsi"]) for c in recent if "rsi" in c]

    # Find swing points
    for i in range(2, len(closes) - 2):
        # Local low (potential bullish divergence)
        if closes[i] < closes[i-1] and closes[i] < closes[i+1]:
            prev_low = closes[i-2]
            if closes[i] < prev_low and rsis[i] > rsis[i-2]:
                patterns.append(f"📈 *Bullish Divergence* near candle {i}")

        # Local high (potential bearish divergence)
        elif closes[i] > closes[i-1] and closes[i] > closes[i+1]:
            prev_high = closes[i-2]
            if closes[i] > prev_high and rsis[i] < rsis[i-2]:
                patterns.append(f"📉 *Bearish Divergence* near candle {i}")

    return patterns
    
def detect_engulfing_patterns(candles):
    """
    Detect bullish and bearish engulfing patterns.
    Adds basic trend context for higher accuracy.
    """
    results = []

    for i in range(2, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]

        prev_open = float(prev["open"])
        prev_close = float(prev["close"])
        curr_open = float(curr["open"])
        curr_close = float(curr["close"])

        # Rough short-term trend direction before pattern
        trend_dir = float(candles[i-2]["close"]) - float(candles[i-3]["close"]) if i >= 3 else 0

        # Bullish Engulfing
        if prev_close < prev_open and curr_close > curr_open:
            if curr_close > prev_open and curr_open < prev_close and trend_dir < 0:
                price = curr_close
                results.append(f"🟢 *Bullish Engulfing* near ${price:.2f} ({curr['datetime']})")

        # Bearish Engulfing
        elif prev_close > prev_open and curr_close < curr_open:
            if curr_open > prev_close and curr_close < prev_open and trend_dir > 0:
                price = curr_close
                results.append(f"🔴 *Bearish Engulfing* near ${price:.2f} ({curr['datetime']})")

    return results
     
def detect_trendline_breaks(candles):
    """
    Detect bullish/bearish trendline breaks using recent swing highs/lows.
    Filters noise by confirming direction and requiring a clean breakout.
    """
    results = []

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    dates = [c["datetime"] for c in candles]

    # Identify swing highs/lows
    swing_highs = [(i, highs[i]) for i in range(1, len(highs) - 1)
                   if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]]
    swing_lows = [(i, lows[i]) for i in range(1, len(lows) - 1)
                  if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]]

    # ---- Downtrend line (bear to bull breakout) ----
    if len(swing_highs) >= 3:
        idxs, vals = zip(*swing_highs[-3:])
        if vals[0] > vals[-1]:  # Ensure it's actually a descending line
            m = (vals[-1] - vals[0]) / (idxs[-1] - idxs[0] + 1e-9)
            b = vals[0] - m * idxs[0]

            last_idx = len(closes) - 1
            trendline_val = m * last_idx + b
            breakout_buffer = trendline_val * 1.003  # +0.3%

            if closes[-1] > breakout_buffer and closes[-2] <= trendline_val:
                results.append(f"📈 Bullish Trendline Break at {dates[-1]}")

    # ---- Uptrend line (bull to bear breakdown) ----
    if len(swing_lows) >= 3:
        idxs, vals = zip(*swing_lows[-3:])
        if vals[0] < vals[-1]:  # Ensure it's actually ascending
            m = (vals[-1] - vals[0]) / (idxs[-1] - idxs[0] + 1e-9)
            b = vals[0] - m * idxs[0]

            last_idx = len(closes) - 1
            trendline_val = m * last_idx + b
            breakout_buffer = trendline_val * 0.997  # -0.3%

            if closes[-1] < breakout_buffer and closes[-2] >= trendline_val:
                results.append(f"📉 Bearish Trendline Break at {dates[-1]}")

    return results
    
def detect_golden_death_crosses(candles):
    patterns = []
    # Assuming candles have 'ema50' and 'ema200' keys calculated beforehand
    for i in range(1, len(candles)):
        prev_short = candles[i - 1].get("ema50")
        prev_long = candles[i - 1].get("ema200")
        curr_short = candles[i].get("ema50")
        curr_long = candles[i].get("ema200")
        if None in (prev_short, prev_long, curr_short, curr_long):
            continue

        # Golden Cross: 50 EMA crosses above 200 EMA
        if prev_short < prev_long and curr_short > curr_long:
            patterns.append(f"Golden Cross detected at {candles[i]['datetime']}")

        # Death Cross: 50 EMA crosses below 200 EMA
        elif prev_short > prev_long and curr_short < curr_long:
            patterns.append(f"Death Cross detected at {candles[i]['datetime']}")

    return patterns
    
def detect_double_top_bottom(candles):
    patterns = []

    closes = [c["close"] for c in candles]
    timestamps = [c["datetime"] for c in candles]

    # Helper to detect local peaks and troughs
    def is_local_peak(i):
        return closes[i-1] < closes[i] > closes[i+1]

    def is_local_trough(i):
        return closes[i-1] > closes[i] < closes[i+1]

    peaks = []
    troughs = []

    for i in range(1, len(closes) - 1):
        if is_local_peak(i):
            peaks.append((i, closes[i], timestamps[i]))
        elif is_local_trough(i):
            troughs.append((i, closes[i], timestamps[i]))

    # Detect Double Top: 2 peaks close in value, small gap
    for i in range(len(peaks) - 1):
        i1, p1, t1 = peaks[i]
        i2, p2, t2 = peaks[i + 1]
        if abs(p1 - p2) / p1 < 0.02 and (i2 - i1) >= 3:  # within 2% and at least 3 candles apart
            patterns.append(f"🔺 Double Top detected between {t1} and {t2}")

    # Detect Double Bottom: 2 troughs close in value, small gap
    for i in range(len(troughs) - 1):
        i1, t1_price, t1_time = troughs[i]
        i2, t2_price, t2_time = troughs[i + 1]
        if abs(t1_price - t2_price) / t1_price < 0.02 and (i2 - i1) >= 3:
            patterns.append(f"🔻 Double Bottom detected between {t1_time} and {t2_time}")

    return patterns