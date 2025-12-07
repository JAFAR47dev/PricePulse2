SUPPORTED_INDICATORS = {
    "rsi": {
        "type": "numeric",
        "min": 0,
        "max": 100,
        "example": "RSI < 30"
    },
    "ema20": {
        "type": "numeric",
        "min": 0,
        "max": 999999,
        "example": "EMA20 > 50000"
    },
    "macd": {
        "type": "numeric",
        "example": "MACD > 0"
    },
    "macdSignal": {
        "type": "numeric",
        "example": "MACDSignal < 0"
    },
    "macdHist": {
        "type": "numeric",
        "example": "MACDHist > 0"
    },
    "stochK": {
        "type": "numeric",
        "min": 0,
        "max": 100,
        "example": "StochK < 20"
    },
    "stochD": {
        "type": "numeric",
        "min": 0,
        "max": 100,
        "example": "StochD < 20"
    },
    "cci": {
        "type": "numeric",
        "example": "CCI > 100"
    },
    "atr": {
        "type": "numeric",
        "example": "ATR > 1.5"
    },
    "mfi": {
        "type": "numeric",
        "min": 0,
        "max": 100,
        "example": "MFI < 20"
    },
    "bbUpper": {
        "type": "numeric",
        "example": "BBUpper < 70000"
    },
    "bbMiddle": {
        "type": "numeric",
        "example": "BBMiddle > 30000"
    },
    "bbLower": {
        "type": "numeric",
        "example": "BBLower > 25000"
    },
    "adx": {
        "type": "numeric",
        "min": 0,
        "max": 100,
        "example": "ADX > 20"
    },
    "vwap": {
        "type": "numeric",
        "example": "VWAP < 51000"
    }
}


# Supported Twelve Data intervals
SUPPORTED_INTERVALS = [
    "1min", "5min", "15min", "30min",
    "1h", "2h", "4h", "8h", "12h",
    "1d", "1w", "1mo"
]

def validate_indicator_rule(ind):
    """
    Validates: { indicator, operator, value, timeframe }
    Returns: (ok=True, error=None) or (ok=False, error_string)
    """

    name = ind.get("indicator")
    op = ind.get("operator")
    val = ind.get("value")
    tf = ind.get("timeframe", "1h")  # default to 1h if not provided

    # --- Indicator Name ---
    if name not in SUPPORTED_INDICATORS:
        supported = ", ".join(SUPPORTED_INDICATORS.keys())
        return False, (
            f"❌ Unsupported indicator: *{name}*\n"
            f"Supported indicators:\n{supported}"
        )

    rule = SUPPORTED_INDICATORS[name]

    # --- Operator ---
    if op not in [">", "<", ">=", "<=", "=", "=="]:
        return False, (
            f"❌ Invalid operator for *{name}*.\n"
            f"Use one of: > , < , >= , <= , ="
        )

    # --- Numeric Value ---
    if rule["type"] == "numeric":
        try:
            val = float(val)
        except:
            return False, (
                f"❌ Invalid value for *{name}*.\n"
                f"Correct example:\n`{rule['example']}`"
            )

        # Range validation
        if "min" in rule and val < rule["min"]:
            return False, (
                f"❌ {name.upper()} value is too low.\n"
                f"Minimum allowed is {rule['min']}."
            )
        if "max" in rule and val > rule["max"]:
            return False, (
                f"❌ {name.upper()} value is too high.\n"
                f"Maximum allowed is {rule['max']}."
            )

    # --- Timeframe ---
    if tf not in SUPPORTED_INTERVALS:
        supported = ", ".join(SUPPORTED_INTERVALS)
        return False, (
            f"❌ Unsupported timeframe: *{tf}*\n"
            f"Supported intervals:\n{supported}"
        )

    return True, None
    