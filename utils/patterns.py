# utils/patterns.py

def detect_divergences(candles):
    """
    Detect bullish/bearish divergences using price lows/highs vs RSI lows/highs.
    Looks at recent 30–50 candles.
    Returns list of detected patterns.
    """
    if len(candles) < 20:
        return []

    patterns = []

    recent = candles[-50:]

    # Extract closing prices and RSI values
    prices = [float(c["close"]) for c in recent if "rsi" in c]
    rsis = [float(c["rsi"]) for c in recent if "rsi" in c]

    if len(prices) < 10 or len(rsis) < 10:
        return []

    # Search for bullish divergence (price lower low, RSI higher low)
    for i in range(2, len(prices) - 2):
        p1, p2 = prices[i], prices[i+2]
        r1, r2 = rsis[i], rsis[i+2]

        if p2 < p1 and r2 > r1:
            patterns.append(f"📈 *Bullish Divergence* spotted at candle {i+2}")

        elif p2 > p1 and r2 < r1:
            patterns.append(f"📉 *Bearish Divergence* spotted at candle {i+2}")

    return patterns
    
def detect_engulfing_patterns(candles):
    results = []

    for i in range(1, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]

        prev_open = float(prev["open"])
        prev_close = float(prev["close"])
        curr_open = float(curr["open"])
        curr_close = float(curr["close"])

        # Bullish Engulfing: prev red, curr green & curr engulfs prev
        if prev_close < prev_open and curr_close > curr_open:
            if curr_close > prev_open and curr_open < prev_close:
                results.append(f"🟢 Bullish Engulfing at {curr['datetime']}")

        # Bearish Engulfing: prev green, curr red & curr engulfs prev
        elif prev_close > prev_open and curr_close < curr_open:
            if curr_open > prev_close and curr_close < prev_open:
                results.append(f"🔴 Bearish Engulfing at {curr['datetime']}")

    return results
    
def detect_trendline_breaks(candles):
    results = []

    # Convert OHLC to floats and datetime for processing
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    dates = [c["datetime"] for c in candles]

    # Simple swing detection: swing high if high[i] > high[i-1] and high[i] > high[i+1]
    swing_highs = []
    for i in range(1, len(highs) -1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            swing_highs.append((i, highs[i]))

    # Swing low: low[i] < low[i-1] and low[i] < low[i+1]
    swing_lows = []
    for i in range(1, len(lows) -1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            swing_lows.append((i, lows[i]))

    # Detect downtrend line from last 3 swing highs if available
    if len(swing_highs) >= 3:
        idxs, vals = zip(*swing_highs[-3:])
        # Calculate line slope (m) and intercept (b) for y = mx + b
        x_vals = list(idxs)
        y_vals = list(vals)
        m = (y_vals[2] - y_vals[0]) / (x_vals[2] - x_vals[0] + 1e-9)
        b = y_vals[0] - m * x_vals[0]

        # Check if last close breaks above the downtrend line
        last_idx = len(closes) - 1
        trendline_value = m * last_idx + b
        if closes[-1] > trendline_value:
            results.append(f"🔔 Bullish Trendline Break at {dates[-1]}")

    # Detect uptrend line from last 3 swing lows if available
    if len(swing_lows) >= 3:
        idxs, vals = zip(*swing_lows[-3:])
        m = (vals[2] - vals[0]) / (idxs[2] - idxs[0] + 1e-9)
        b = vals[0] - m * idxs[0]

        trendline_value = m * (len(closes) - 1) + b
        if closes[-1] < trendline_value:
            results.append(f"🔔 Bearish Trendline Break at {dates[-1]}")

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