import asyncio
import httpx
import os
import json
from dotenv import load_dotenv
from services.levels_engine import LevelsEngine
from utils.patterns import detect_all_patterns, patterns_to_strings

load_dotenv()


# ============================================================================
# EXCHANGE CONFIGURATION
# ============================================================================

# Bybit → OKX fallback. No API keys required for public market data.
BYBIT_BASE_URL = "https://api.bybit.com"
OKX_BASE_URL   = "https://www.okx.com"

# Map our timeframe labels → Bybit interval strings
BYBIT_INTERVAL = {
    "5m":  "5",
    "15m": "15",
    "30m": "30",
    "1h":  "60",
    "2h":  "120",
    "4h":  "240",
    "8h":  "360",
    "1d":  "D",
}

# Map our timeframe labels → OKX bar strings
OKX_INTERVAL = {
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1H",
    "2h":  "2H",
    "4h":  "4H",
    "8h":  "8H",
    "1d":  "1D",
}

# Higher timeframe to use for multi-timeframe confirmation per timeframe
HTF_MAP = {
    "5m":  "1h",
    "15m": "1h",
    "30m": "4h",
    "1h":  "4h",
    "2h":  "4h",
    "4h":  "1d",
    "8h":  "1d",
    "1d":  "1d",   # no higher TF — self-confirmation
}

MIN_CANDLES = 50   # minimum candles required for reliable indicator math


# ============================================================================
# SMART PRICE FORMATTER
# ============================================================================

def _fmt(price: float) -> str:
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.3f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


# ============================================================================
# DATA FETCHING — BYBIT PRIMARY / OKX FALLBACK
# ============================================================================

def _symbol_to_bybit(symbol: str) -> str:
    """Convert e.g. 'BTC' → 'BTCUSDT'."""
    s = symbol.upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def _symbol_to_okx(symbol: str) -> str:
    """Convert e.g. 'BTC' → 'BTC-USDT'."""
    s = symbol.upper()
    if "-" in s:
        return s
    base = s.replace("USDT", "")
    return f"{base}-USDT"


async def _fetch_bybit(symbol: str, timeframe: str, limit: int = 200) -> list | None:
    """
    Fetch OHLCV from Bybit V5 /market/kline.
    Returns list of candle dicts or None on failure.

    Bybit response columns (index):
        0 startTime (ms), 1 open, 2 high, 3 low, 4 close, 5 volume, 6 turnover
    """
    interval = BYBIT_INTERVAL.get(timeframe)
    if not interval:
        print(f"❌ Bybit: unsupported timeframe {timeframe}")
        return None

    params = {
        "category": "spot",
        "symbol":   _symbol_to_bybit(symbol),
        "interval": interval,
        "limit":    limit,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{BYBIT_BASE_URL}/v5/market/kline", params=params)

        if resp.status_code != 200:
            print(f"❌ Bybit HTTP {resp.status_code} for {symbol}/{timeframe}")
            return None

        data = resp.json()
        if data.get("retCode") != 0:
            print(f"❌ Bybit error for {symbol}: {data.get('retMsg')}")
            return None

        rows = data.get("result", {}).get("list", [])
        if not rows:
            print(f"❌ Bybit returned empty list for {symbol}/{timeframe}")
            return None

        # Bybit returns newest-first → reverse to chronological order
        rows = list(reversed(rows))

        candles = []
        for row in rows:
            try:
                candles.append({
                    "datetime": int(row[0]),
                    "open":     float(row[1]),
                    "high":     float(row[2]),
                    "low":      float(row[3]),
                    "close":    float(row[4]),
                    "volume":   float(row[5]),
                })
            except (IndexError, ValueError, TypeError):
                continue

        if len(candles) < MIN_CANDLES:
            print(f"❌ Bybit: only {len(candles)} candles for {symbol}/{timeframe}")
            return None

        print(f"✅ Bybit: {len(candles)} candles for {symbol}/{timeframe}")
        return candles

    except httpx.TimeoutException:
        print(f"❌ Bybit timeout for {symbol}/{timeframe}")
        return None
    except Exception as e:
        print(f"❌ Bybit unexpected error for {symbol}: {e}")
        return None


async def _fetch_okx(symbol: str, timeframe: str, limit: int = 200) -> list | None:
    """
    Fetch OHLCV from OKX /market/candles.
    Returns list of candle dicts or None on failure.

    OKX response columns (index):
        0 ts (ms), 1 open, 2 high, 3 low, 4 close, 5 vol, 6 volCcy, 7 volCcyQuote, 8 confirm
    """
    bar = OKX_INTERVAL.get(timeframe)
    if not bar:
        print(f"❌ OKX: unsupported timeframe {timeframe}")
        return None

    params = {
        "instId": _symbol_to_okx(symbol),
        "bar":    bar,
        "limit":  limit,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{OKX_BASE_URL}/api/v5/market/candles", params=params)

        if resp.status_code != 200:
            print(f"❌ OKX HTTP {resp.status_code} for {symbol}/{timeframe}")
            return None

        data = resp.json()
        if data.get("code") != "0":
            print(f"❌ OKX error for {symbol}: {data.get('msg')}")
            return None

        rows = data.get("data", [])
        if not rows:
            print(f"❌ OKX returned empty list for {symbol}/{timeframe}")
            return None

        # OKX also returns newest-first → reverse
        rows = list(reversed(rows))

        candles = []
        for row in rows:
            try:
                candles.append({
                    "datetime": int(row[0]),
                    "open":     float(row[1]),
                    "high":     float(row[2]),
                    "low":      float(row[3]),
                    "close":    float(row[4]),
                    "volume":   float(row[5]),
                })
            except (IndexError, ValueError, TypeError):
                continue

        if len(candles) < MIN_CANDLES:
            print(f"❌ OKX: only {len(candles)} candles for {symbol}/{timeframe}")
            return None

        print(f"✅ OKX (fallback): {len(candles)} candles for {symbol}/{timeframe}")
        return candles

    except httpx.TimeoutException:
        print(f"❌ OKX timeout for {symbol}/{timeframe}")
        return None
    except Exception as e:
        print(f"❌ OKX unexpected error for {symbol}: {e}")
        return None


async def fetch_candles(symbol: str, timeframe: str, limit: int = 200) -> list | None:
    """
    Fetch OHLCV candles — Bybit first, OKX as fallback.
    Attaches technical indicators before returning.
    """
    candles = await _fetch_bybit(symbol, timeframe, limit)
    if not candles:
        candles = await _fetch_okx(symbol, timeframe, limit)
    if not candles:
        print(f"❌ Both Bybit and OKX failed for {symbol}/{timeframe}")
        return None

    return _attach_indicators(candles)


# ============================================================================
# MULTI-TIMEFRAME CONFIRMATION
# ============================================================================

def _htf_trend(candles: list) -> str:
    """
    Derive a simple trend label from a higher-timeframe candle list.
    Uses the last candle's EMA values (attached by _attach_indicators).
    """
    if not candles:
        return "UNKNOWN"
    last = candles[-1]
    price  = last.get("close", 0)
    ema20  = last.get("ema20",  0)
    ema50  = last.get("ema50",  0)
    ema200 = last.get("ema200", 0)

    if ema20 and ema50 and ema200:
        if price > ema20 > ema50 > ema200:
            return "STRONG_UPTREND"
        if price > ema20 and price > ema50:
            return "UPTREND"
        if price < ema20 < ema50 < ema200:
            return "STRONG_DOWNTREND"
        if price < ema20 and price < ema50:
            return "DOWNTREND"
    return "RANGING"


def _mtf_quality_penalty(ltf_direction: str, htf_trend: str) -> tuple[int, str | None]:
    """
    Return (score_penalty, warning_string | None).

    A setup trading against the higher-timeframe trend is penalised;
    a setup aligned with it gets a bonus.
    """
    bullish_htf = htf_trend in ("STRONG_UPTREND", "UPTREND")
    bearish_htf = htf_trend in ("STRONG_DOWNTREND", "DOWNTREND")

    if ltf_direction == "BULLISH":
        if htf_trend == "STRONG_UPTREND":
            return (-15, None)          # bonus (negative penalty)
        if bullish_htf:
            return (-8, None)
        if bearish_htf:
            return (25, f"⚠️ Counter-trend: HTF is {htf_trend} — lower-quality long")
        return (10, "⚠️ HTF ranging — setup quality reduced")

    if ltf_direction == "BEARISH":
        if htf_trend == "STRONG_DOWNTREND":
            return (-15, None)
        if bearish_htf:
            return (-8, None)
        if bullish_htf:
            return (25, f"⚠️ Counter-trend: HTF is {htf_trend} — lower-quality short")
        return (10, "⚠️ HTF ranging — setup quality reduced")

    return (0, None)   # NEUTRAL direction — no adjustment


# ============================================================================
# INDICATOR CALCULATION
# ============================================================================

def _attach_indicators(candles: list) -> list:
    if not candles or len(candles) < 2:
        return candles

    n      = len(candles)
    closes = [c["close"] for c in candles]

    ema20  = _ema_series(closes, 20)
    ema50  = _ema_series(closes, 50)
    ema200 = _ema_series(closes, 200)
    rsi14  = _rsi_series(closes, 14)
    macd   = _macd_series(closes)

    zero_macd = {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
    for i, candle in enumerate(candles):
        candle["ema20"]      = ema20[i]  if i < len(ema20)  else 0.0
        candle["ema50"]      = ema50[i]  if i < len(ema50)  else 0.0
        candle["ema200"]     = ema200[i] if i < len(ema200) else 0.0
        candle["rsi"]        = rsi14[i]  if i < len(rsi14)  else 50.0
        m = macd[i] if i < len(macd) else zero_macd
        candle["macd"]       = m["macd"]
        candle["macdSignal"] = m["signal"]
        candle["macdHist"]   = m["histogram"]

    return candles


def _ema_series(prices: list, period: int) -> list:
    n = len(prices)
    if n == 0: return []
    if n < period: return [0.0] * n

    k   = 2.0 / (period + 1)
    out = [0.0] * (period - 1)
    out.append(sum(prices[:period]) / period)
    for i in range(period, n):
        out.append(prices[i] * k + out[-1] * (1 - k))
    return out


def _rsi_series(prices: list, period: int = 14) -> list:
    n = len(prices)
    if n == 0: return []
    if n <= period: return [50.0] * n

    gains  = [max(prices[i] - prices[i-1], 0.0) for i in range(1, period+1)]
    losses = [max(prices[i-1] - prices[i], 0.0) for i in range(1, period+1)]
    ag = sum(gains)  / period
    al = sum(losses) / period

    first_rsi = 100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al))
    out = [50.0] * period + [first_rsi]

    for i in range(period + 1, n):
        delta = prices[i] - prices[i-1]
        ag = (ag * (period-1) + max(delta,  0.0)) / period
        al = (al * (period-1) + max(-delta, 0.0)) / period
        out.append(100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al)))
    return out


def _macd_series(prices: list) -> list:
    n    = len(prices)
    zero = {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
    if n < 26: return [zero] * n

    ema12 = _ema_series(prices, 12)
    ema26 = _ema_series(prices, 26)
    macd_line   = [ema12[i] - ema26[i] for i in range(n)]
    signal_line = _ema_series(macd_line, 9)
    return [
        {"macd": macd_line[i], "signal": signal_line[i],
         "histogram": macd_line[i] - signal_line[i]}
        for i in range(n)
    ]


async def _build_indicators_dict(candles: list) -> dict | None:
    if not candles:
        return None

    latest = candles[-1]
    closes = [c["close"] for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]

    try:
        from utils.indicators import (
            calculate_stochastic, calculate_cci, calculate_atr,
            calculate_bbands, calculate_adx, calculate_williams_r, calculate_roc,
        )
        stoch_k, stoch_d              = calculate_stochastic(highs, lows, closes)
        cci                            = calculate_cci(highs, lows, closes)
        atr                            = calculate_atr(highs, lows, closes)
        bb_upper, bb_middle, bb_lower  = calculate_bbands(closes)
        adx, plus_di, minus_di         = calculate_adx(highs, lows, closes)
        williams_r                     = calculate_williams_r(highs, lows, closes)
        roc                            = calculate_roc(closes)
    except Exception as e:
        print(f"⚠️  Advanced indicators failed: {e} — using defaults")
        stoch_k = stoch_d = 50.0
        cci = williams_r = roc = 0.0
        atr       = latest["close"] * 0.02
        bb_upper  = latest["close"] * 1.02
        bb_middle = latest["close"]
        bb_lower  = latest["close"] * 0.98
        adx = plus_di = minus_di = 0.0

    return {
        "price":      latest["close"],
        "volume":     latest.get("volume", 0.0),
        "ema20":      latest.get("ema20", 0.0),
        "ema50":      latest.get("ema50", 0.0),
        "ema200":     latest.get("ema200", 0.0),
        "rsi":        latest.get("rsi", 50.0),
        "macd":       latest.get("macd", 0.0),
        "macdSignal": latest.get("macdSignal", 0.0),
        "macdHist":   latest.get("macdHist", 0.0),
        "stochK":     stoch_k,
        "stochD":     stoch_d,
        "cci":        cci,
        "atr":        atr,
        "bbUpper":    bb_upper,
        "bbMiddle":   bb_middle,
        "bbLower":    bb_lower,
        "adx":        adx,
        "plusDI":     plus_di,
        "minusDI":    minus_di,
        "williamsR":  williams_r,
        "roc":        roc,
    }


# ============================================================================
# LEVEL NORMALISATION  (unchanged)
# ============================================================================

def _normalise_level(raw: dict, fallback_price: float) -> dict:
    price = float(raw.get("price") or raw.get("level") or raw.get("value") or fallback_price)
    price_lower = float(raw.get("price_lower") or raw.get("low")  or price * 0.995)
    price_upper = float(raw.get("price_upper") or raw.get("high") or price * 1.005)
    strength    = str(raw.get("strength") or raw.get("type") or "Medium").capitalize()
    if strength not in ("Strong", "Medium", "Weak"):
        strength = "Medium"
    touches = int(raw.get("touches") or raw.get("hits") or raw.get("count") or 1)
    return {
        "price":       price,
        "price_lower": price_lower,
        "price_upper": price_upper,
        "strength":    strength,
        "touches":     touches,
    }


# ============================================================================
# SETUP ANALYZER
# ============================================================================

class SetupAnalyzer:

    def __init__(self):
        self.levels_engine = LevelsEngine()

    # ------------------------------------------------------------------ public

    async def analyze_setup(self, symbol: str, timeframe: str) -> dict | None:
        try:
            print(f"🔄 Analyzing {symbol}/{timeframe}…")

            # ── 1. Fetch LTF + HTF candles concurrently ───────────────
            htf = HTF_MAP.get(timeframe, "1d")
            same_tf = (htf == timeframe)

            if same_tf:
                # No higher TF available — only one fetch needed
                ltf_candles = await fetch_candles(symbol, timeframe)
                htf_candles = ltf_candles
            else:
                ltf_candles, htf_candles = await asyncio.gather(
                    fetch_candles(symbol, timeframe),
                    fetch_candles(symbol, htf),
                )

            if not ltf_candles or len(ltf_candles) < MIN_CANDLES:
                print(f"❌ Insufficient LTF candles for {symbol}/{timeframe}")
                return None

            # ── 2. HTF trend ──────────────────────────────────────────
            htf_trend_label = _htf_trend(htf_candles) if htf_candles else "UNKNOWN"
            print(f"   HTF ({htf}) trend: {htf_trend_label}")

            # ── 3. Indicators from LTF ────────────────────────────────
            indicators = await _build_indicators_dict(ltf_candles)
            if not indicators:
                print(f"❌ Indicator build failed for {symbol}")
                return None

            current_price = indicators["price"]

            # ── 4. Support / Resistance ───────────────────────────────
            support_levels: list    = []
            resistance_levels: list = []
            try:
                sr_data = await self.levels_engine.calculate_levels(
                    symbol=symbol, timeframe=timeframe, max_levels=5
                )
                if sr_data.get("current_price"):
                    current_price = float(sr_data["current_price"])
                support_levels    = [_normalise_level(l, current_price) for l in sr_data.get("support_levels", [])]
                resistance_levels = [_normalise_level(l, current_price) for l in sr_data.get("resistance_levels", [])]
            except Exception as e:
                print(f"⚠️  S/R levels failed for {symbol}: {e}")

            # ── 5. Patterns ───────────────────────────────────────────
            try:
                pattern_dicts = detect_all_patterns(ltf_candles, max_results=8)
            except Exception as e:
                print(f"⚠️  Pattern detection failed: {e}")
                pattern_dicts = []

            # ── 6. Score ──────────────────────────────────────────────
            score_data = self._score(
                ltf_candles, indicators, support_levels, resistance_levels, pattern_dicts
            )

            # ── 7. Direction ──────────────────────────────────────────
            direction = self._direction(score_data)

            # ── 8. MTF penalty / bonus ────────────────────────────────
            penalty, mtf_warning = _mtf_quality_penalty(direction, htf_trend_label)
            adjusted_score = max(0, min(100, score_data["score"] - penalty))
            score_data["score"] = adjusted_score
            if mtf_warning:
                score_data["risk_factors"].insert(0, mtf_warning)

            # ── 9. Trade levels ───────────────────────────────────────
            trade = self._trade_levels(indicators, support_levels, resistance_levels, direction)

            # ── 10. Confidence ────────────────────────────────────────
            confidence = self._confidence(score_data, indicators)

            # ── 11. Entry conditions ──────────────────────────────────
            conditions = self._entry_conditions(indicators, direction, timeframe, score_data)

            print(
                f"✅ {symbol}/{timeframe} — score {adjusted_score}/100 "
                f"dir {direction}  conf {confidence}%  HTF {htf_trend_label}"
            )

            return {
                "score":          adjusted_score,
                "quality":        self._quality_label(adjusted_score),
                "confidence":     confidence,
                "direction":      direction,
                "current_price":  current_price,
                "trend_context":  score_data["trend_context"],
                "htf_timeframe":  htf,
                "htf_trend":      htf_trend_label,
                "bullish_signals":  score_data["bullish_signals"],
                "bearish_signals":  score_data["bearish_signals"],
                "risk_factors":     score_data["risk_factors"],
                "support_levels":     support_levels,
                "resistance_levels":  resistance_levels,
                "patterns":           patterns_to_strings(pattern_dicts[:5]),
                "entry_zone":    trade["entry_zone"],
                "stop_loss":     trade["stop_loss"],
                "take_profit_1": trade["tp1"],
                "take_profit_2": trade["tp2"],
                "risk_reward":   trade["rr_ratio"],
                "wait_for":   conditions,
                "indicators": indicators,
            }

        except Exception as e:
            print(f"❌ SetupAnalyzer error for {symbol}/{timeframe}: {e}")
            import traceback; traceback.print_exc()
            return None

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _safe(indicators: dict, key: str, default: float = 0.0) -> float:
        v = indicators.get(key, default)
        return float(v) if v is not None else default

    # ----------------------------------------------------------------- scoring
    # (scoring, direction, trade_levels, confidence, entry_conditions, quality_label
    #  are all UNCHANGED from your original — copied verbatim below)

    def _score(self, candles, indicators, support_levels, resistance_levels, patterns):
        bull = 0; bear = 0
        bull_signals: list[str] = []; bear_signals: list[str] = []; risks: list[str] = []

        price    = self._safe(indicators, "price")
        ema20    = self._safe(indicators, "ema20")
        ema50    = self._safe(indicators, "ema50")
        ema200   = self._safe(indicators, "ema200")
        rsi      = self._safe(indicators, "rsi", 50.0)
        mhist    = self._safe(indicators, "macdHist")
        adx      = self._safe(indicators, "adx")
        plus_di  = self._safe(indicators, "plusDI")
        minus_di = self._safe(indicators, "minusDI")
        stoch_k  = self._safe(indicators, "stochK", 50.0)
        stoch_d  = self._safe(indicators, "stochD", 50.0)
        bb_u     = self._safe(indicators, "bbUpper")
        bb_m     = self._safe(indicators, "bbMiddle")
        bb_l     = self._safe(indicators, "bbLower")
        cci      = self._safe(indicators, "cci")
        roc      = self._safe(indicators, "roc")

        trend_context = self._trend_context(price, ema20, ema50, ema200)

        if trend_context == "STRONG_UPTREND":
            bull += 20; bull_signals.append("Strong uptrend — all EMAs stacked bullish")
        elif trend_context == "UPTREND":
            bull += 15; bull_signals.append("Uptrend — price above key EMAs")
        elif trend_context == "STRONG_DOWNTREND":
            bear += 20; bear_signals.append("Strong downtrend — all EMAs stacked bearish")
        elif trend_context == "DOWNTREND":
            bear += 15; bear_signals.append("Downtrend — price below key EMAs")
        else:
            risks.append("No clear trend — range-bound market")

        if adx:
            if adx > 25:
                if plus_di and minus_di:
                    if plus_di > minus_di:
                        bull += 10; bull_signals.append(f"Strong bullish trend (ADX {adx:.0f})")
                    else:
                        bear += 10; bear_signals.append(f"Strong bearish trend (ADX {adx:.0f})")
            elif adx < 20:
                risks.append(f"Weak trend (ADX {adx:.0f}) — avoid momentum trades")

        if rsi:
            if 55 < rsi < 70:   bull += 12; bull_signals.append(f"Bullish momentum (RSI {rsi:.0f})")
            elif 40 < rsi <= 55: bull += 5;  bull_signals.append(f"Neutral-bullish RSI ({rsi:.0f})")
            elif 30 < rsi < 45:  bear += 5;  bear_signals.append(f"Neutral-bearish RSI ({rsi:.0f})")
            elif rsi <= 30:
                bear += 12; bear_signals.append(f"Bearish momentum (RSI {rsi:.0f})")
                bull_signals.append("Oversold — watch for bounce")
            elif rsi >= 70:
                bull += 12; bull_signals.append(f"Strong bullish RSI ({rsi:.0f})")
                risks.append(f"Overbought RSI ({rsi:.0f}) — pullback risk")

        if mhist:
            if mhist > 0: bull += 10; bull_signals.append("MACD histogram positive")
            else:         bear += 10; bear_signals.append("MACD histogram negative")

        if stoch_k and stoch_d:
            if stoch_k > stoch_d:
                if stoch_k < 80: bull += 5; bull_signals.append(f"Stochastic bullish crossover ({stoch_k:.0f})")
                else:            risks.append(f"Stochastic overbought ({stoch_k:.0f})")
            else:
                if stoch_k > 20: bear += 5; bear_signals.append(f"Stochastic bearish crossover ({stoch_k:.0f})")
                else:            bull_signals.append(f"Stochastic oversold ({stoch_k:.0f}) — bounce watch")

        if cci:
            if cci > 100:
                bull += 3; bull_signals.append(f"CCI bullish ({cci:.0f})")
                if cci > 200: risks.append("CCI extremely overbought")
            elif cci < -100:
                bear += 3; bear_signals.append(f"CCI bearish ({cci:.0f})")
                if cci < -200: bull_signals.append("CCI oversold — bounce potential")

        if roc:
            if roc > 5:  bull += 5; bull_signals.append(f"Strong upward momentum (ROC {roc:.1f}%)")
            elif roc < -5: bear += 5; bear_signals.append(f"Strong downward momentum (ROC {roc:.1f}%)")

        valid_sup = [l for l in support_levels    if l["price"] < price]
        valid_res = [l for l in resistance_levels if l["price"] > price]

        if valid_sup:
            nearest_s = max(valid_sup, key=lambda x: x["price"])
            dist_s = (price - nearest_s["price"]) / price * 100
            if dist_s < 2:
                bull += 12; bull_signals.append(f"At {nearest_s['strength'].lower()} support ({_fmt(nearest_s['price'])}, -{dist_s:.1f}%)")
            elif dist_s < 5:
                bull += 6;  bull_signals.append(f"Near support (-{dist_s:.1f}%)")

        if valid_res:
            nearest_r = min(valid_res, key=lambda x: x["price"])
            dist_r = (nearest_r["price"] - price) / price * 100
            if dist_r < 2:
                bear += 12; bear_signals.append(f"At {nearest_r['strength'].lower()} resistance ({_fmt(nearest_r['price'])}, +{dist_r:.1f}%)")
                risks.append("Price at resistance — rejection risk")
            elif dist_r < 5:
                risks.append(f"Approaching resistance (+{dist_r:.1f}%)")
            else:
                bull += 6;  bull_signals.append(f"Clear room to resistance (+{dist_r:.1f}%)")

        if bb_u and bb_l and bb_m:
            if price > bb_u:   bear += 3; risks.append("Price above upper Bollinger Band")
            elif price < bb_l: bull += 5; bull_signals.append("Price below lower Bollinger Band — bounce watch")
            elif price > bb_m: bull += 3; bull_signals.append("Price in upper Bollinger half")
            else:              bear += 3; bear_signals.append("Price in lower Bollinger half")

        _QUALITY_BONUS = {"HIGH": 8, "MEDIUM": 5, "LOW": 2}
        for p in patterns[:6]:
            if not isinstance(p, dict): continue
            direction_flag = p.get("direction", "NEUTRAL")
            quality        = p.get("quality",   "LOW")
            bonus          = _QUALITY_BONUS.get(quality, 2)
            label          = f"{p.get('emoji','•')} {p.get('name','Pattern')}: {p.get('description','')}"[:90]
            if direction_flag == "BULLISH":   bull += bonus; bull_signals.append(label)
            elif direction_flag == "BEARISH": bear += bonus; bear_signals.append(label)
            else:                             risks.append(label)

        net   = bull - bear
        final = int(min(50 + net, 100)) if net > 0 else int(max(50 + net, 0))

        return {
            "score":           final,
            "bullish_score":   bull,
            "bearish_score":   bear,
            "bullish_signals": bull_signals,
            "bearish_signals": bear_signals,
            "risk_factors":    risks,
            "trend_context":   trend_context,
        }

    @staticmethod
    def _trend_context(price, ema20, ema50, ema200):
        if ema20 and ema50 and ema200:
            if price > ema20 > ema50 > ema200: return "STRONG_UPTREND"
            if price > ema20 and price > ema50: return "UPTREND"
            if price < ema20 < ema50 < ema200: return "STRONG_DOWNTREND"
            if price < ema20 and price < ema50: return "DOWNTREND"
        return "RANGING"

    @staticmethod
    def _direction(score_data):
        score = score_data["score"]; trend = score_data["trend_context"]
        if score > 65 and trend in ("STRONG_UPTREND", "UPTREND"):   return "BULLISH"
        if score < 35 and trend in ("STRONG_DOWNTREND", "DOWNTREND"): return "BEARISH"
        if 55 <= score <= 65: return "BULLISH"
        if 35 <= score <= 45: return "BEARISH"
        return "NEUTRAL"

    def _trade_levels(self, indicators, support_levels, resistance_levels, direction):
        price = self._safe(indicators, "price")
        atr   = self._safe(indicators, "atr") or price * 0.02
        min_stop = atr * 1.5

        valid_sup = [l for l in support_levels    if l["price"] < price]
        valid_res = [l for l in resistance_levels if l["price"] > price]
        nearest_s = max(valid_sup, key=lambda x: x["price"]) if valid_sup else None
        nearest_r = min(valid_res, key=lambda x: x["price"]) if valid_res else None

        if direction == "BULLISH":
            entry_low = price * 0.998; entry_high = price * 1.002
            stop_loss = min(nearest_s["price_lower"] * 0.995, price - 2*atr) if nearest_s else price - 2*atr
            if price - stop_loss < min_stop: stop_loss = price - min_stop
            risk = price - stop_loss
            tp1  = min(nearest_r["price_lower"] * 0.995, price + risk*2) if nearest_r else price + risk*2
            tp2  = price + risk * 3

        elif direction == "BEARISH":
            entry_low = price * 0.998; entry_high = price * 1.002
            stop_loss = max(nearest_r["price_upper"] * 1.005, price + 2*atr) if nearest_r else price + 2*atr
            if stop_loss - price < min_stop: stop_loss = price + min_stop
            risk = stop_loss - price
            tp1  = max(nearest_s["price_upper"] * 1.005, price - risk*2) if nearest_s else price - risk*2
            tp2  = price - risk * 3

        else:
            entry_low = price * 0.995; entry_high = price * 1.005
            stop_loss = price - 2*atr; tp1 = price + 2*atr; tp2 = price + 4*atr

        risk   = abs(price - stop_loss)
        reward = abs(tp1   - price)
        rr     = round(reward / risk, 2) if risk else 0.0
        return {"entry_zone": (entry_low, entry_high), "stop_loss": stop_loss,
                "tp1": tp1, "tp2": tp2, "rr_ratio": rr}

    def _confidence(self, score_data, indicators):
        conf   = 50
        bull_n = len(score_data["bullish_signals"])
        bear_n = len(score_data["bearish_signals"])
        risk_n = len(score_data["risk_factors"])

        if bull_n > bear_n * 2 or bear_n > bull_n * 2: conf += 20
        elif abs(bull_n - bear_n) <= 2:                 conf -= 20

        if score_data["trend_context"] in ("STRONG_UPTREND", "STRONG_DOWNTREND"): conf += 15
        elif score_data["trend_context"] == "RANGING":                             conf -= 15

        adx = self._safe(indicators, "adx")
        if adx:
            if adx > 30: conf += 10
            elif adx < 20: conf -= 15

        if risk_n > 3: conf -= 15

        score = score_data["score"]
        if score > 75 or score < 25: conf += 10
        elif 45 <= score <= 55:      conf -= 15

        return max(0, min(100, conf))

    def _entry_conditions(self, indicators, direction, timeframe, score_data):
        conditions: list[str] = []
        price = self._safe(indicators, "price")
        rsi   = self._safe(indicators, "rsi")
        adx   = self._safe(indicators, "adx")

        if score_data["score"] < 60:
            conditions.append("⚠️ Setup quality too low — wait for a better opportunity")
            return conditions

        if direction == "BULLISH":
            conditions.append(f"Wait for {timeframe} close above {_fmt(price * 1.005)}")
            if rsi > 70:     conditions.append("Wait for RSI to cool to the 60–65 range")
            if adx and adx < 20: conditions.append("Wait for trend strength to build (ADX > 20)")
            conditions.append("Confirm with above-average volume on the breakout candle")

        elif direction == "BEARISH":
            conditions.append(f"Wait for {timeframe} close below {_fmt(price * 0.995)}")
            if rsi < 30:     conditions.append("Wait for RSI relief rally to 35–40 before entering short")
            if adx and adx < 20: conditions.append("Wait for trend strength to build (ADX > 20)")
            conditions.append("Confirm with above-average volume on the breakdown candle")

        else:
            conditions.append("⚠️ No clear directional bias — avoid trading this setup")
            conditions.append("Wait for price to break out of the current range with conviction")

        return conditions

    @staticmethod
    def _quality_label(score):
        if score >= 75: return "EXCELLENT"
        if score >= 65: return "GOOD"
        if score >= 55: return "FAIR"
        if score >= 45: return "NEUTRAL"
        if score >= 35: return "FAIR (Bearish)"
        if score >= 25: return "GOOD (Bearish)"
        return "EXCELLENT (Bearish)"
