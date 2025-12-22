def pre_score_coin(c):
    """
    Score a coin based on technical indicators.
    
    Args:
        c: Dictionary containing coin data with required keys:
           - symbol, rsi, macd_norm, price_vs_ema20_pct, trend, volatility
           
    Returns:
        Dictionary with scoring results or None if coin is filtered out
    """
    # Input validation
    if not isinstance(c, dict):
        return None
    
    required_keys = ["symbol", "rsi", "macd_norm", "price_vs_ema20_pct", "trend", "volatility"]
    if not all(key in c for key in required_keys):
        return None
    
    score = 0
    reasons = []

    # -----------------------------
    # Core normalized indicators with safe extraction
    # -----------------------------
    try:
        rsi = float(c["rsi"])
        macd = float(c["macd_norm"])
        ema_dist = float(c["price_vs_ema20_pct"])
        trend = str(c["trend"]).lower()
        volatility = str(c["volatility"]).lower()
    except (ValueError, TypeError):
        return None  # Invalid data types

    # Validate ranges
    if not (0 <= rsi <= 100):
        return None  # Invalid RSI
    if not (-1 <= macd <= 1):  # Assuming normalized MACD
        return None  # Invalid MACD
    
    # -----------------------------
    # Optional indicators (safe extraction)
    # -----------------------------
    extras = c.get("extras", {})
    if not isinstance(extras, dict):
        extras = {}
    
    try:
        adx = float(extras.get("adx", 0)) if extras.get("adx") is not None else 0
        mfi = float(extras.get("mfi", 50)) if extras.get("mfi") is not None else 50
    except (ValueError, TypeError):
        adx = 0
        mfi = 50
    
    # Validate optional indicator ranges
    adx = max(0, min(adx, 100))
    mfi = max(0, min(mfi, 100))

    # -----------------------------
    # HARD REJECTIONS (QUALITY FILTER)
    # -----------------------------
    if adx > 0 and adx < 15:
        return None  # no trend strength

    if trend == "range" and adx < 20:
        return None  # sideways chop

    # Fixed: momentum conflict checks now use consistent thresholds
    if rsi > 55 and macd < -0.1:
        return None  # bullish RSI but bearish MACD

    if rsi < 45 and macd > 0.1:
        return None  # bearish RSI but bullish MACD

    # -----------------------------
    # RSI SCORING
    # -----------------------------
    if 50 <= rsi <= 65:
        score += 18
        reasons.append("RSI bullish zone")
    elif 35 <= rsi <= 45:
        score += 18
        reasons.append("RSI bearish zone")
    elif rsi > 75 or rsi < 25:
        score -= 10
        reasons.append("RSI extreme")
    # Add scoring for moderate zones
    elif 45 < rsi < 50 or 65 < rsi <= 75:
        score += 8

    # -----------------------------
    # MACD MOMENTUM (Fixed: symmetric scoring)
    # -----------------------------
    if macd > 0.15:
        score += 28
        reasons.append("Strong bullish MACD")
    elif macd > 0.05:
        score += 18
        reasons.append("Moderate bullish MACD")
    elif macd < -0.15:
        score += 28
        reasons.append("Strong bearish MACD")
    elif macd < -0.05:
        score += 18
        reasons.append("Moderate bearish MACD")

    # -----------------------------
    # EMA ALIGNMENT (Fixed: better logic)
    # -----------------------------
    if 0 <= ema_dist <= 1.5:
        score += 16
        reasons.append("Price near EMA20")
    elif 1.5 < ema_dist <= 3:
        score += 8
        reasons.append("Price moderately above EMA")
    elif ema_dist < -1 and macd > 0:
        score -= 6  # Price below EMA but bullish momentum
    elif ema_dist < -1.5:
        score -= 4  # Significantly below EMA

    # -----------------------------
    # ADX BOOST (only if ADX is provided)
    # -----------------------------
    if adx >= 30:
        score += 12
        reasons.append("Strong trend (ADX)")
    elif 20 <= adx < 30:
        score += 6
        reasons.append("Moderate trend (ADX)")

    # -----------------------------
    # MFI FILTER
    # -----------------------------
    if 40 <= mfi <= 70:
        score += 12
        reasons.append("Healthy money flow")
    elif (mfi > 80 or mfi < 20) and adx < 20:
        return None  # extreme MFI without trend
    elif mfi > 80:
        score -= 8
        reasons.append("Overbought MFI")
    elif mfi < 20:
        score -= 8
        reasons.append("Oversold MFI")

    # -----------------------------
    # VOLATILITY ADJUSTMENT
    # -----------------------------
    if volatility == "high":
        score -= 4
        reasons.append("High volatility")
    elif volatility == "low":
        score += 4
        reasons.append("Low volatility")

    # -----------------------------
    # FINAL OUTPUT
    # -----------------------------
    # Determine bias based on multiple factors, not just MACD
    bias_score = 0
    if macd > 0:
        bias_score += 1
    if rsi > 50:
        bias_score += 1
    if ema_dist > 0:
        bias_score += 1
    
    bias = "BUY" if bias_score >= 2 else "SELL"

    # Clamp score to valid range
    score = max(0, min(score, 100))

    # Better confidence calculation
    if score >= 70:
        confidence = "strong"
    elif score >= 50:
        confidence = "medium"
    elif score >= 30:
        confidence = "weak"
    else:
        confidence = "very weak"

    return {
        "symbol": str(c["symbol"]),
        "score": score,
        "bias": bias,
        "confidence": confidence,
        "reasons": reasons[:3],  # keep concise
        "rsi": round(rsi, 2),
        "macd": round(macd, 3),
        "adx": round(adx, 2) if adx > 0 else None,
    }


def rank_top_setups(coins, top_n=30):
    """
    Rank coins by score and return top N setups.
    
    Args:
        coins: List of coin dictionaries
        top_n: Number of top coins to return (default: 30)
        
    Returns:
        List of scored coins sorted by score (descending)
    """
    if not isinstance(coins, list):
        return []
    
    if not isinstance(top_n, int) or top_n < 1:
        top_n = 30
    
    scored = []

    for c in coins:
        try:
            result = pre_score_coin(c)
            if result:
                scored.append(result)
        except Exception as e:
            # Log error in production, skip bad data
            continue

    # Sort by score (descending), then by symbol for stability
    scored.sort(key=lambda x: (-x["score"], x["symbol"]))

    return scored[:top_n]