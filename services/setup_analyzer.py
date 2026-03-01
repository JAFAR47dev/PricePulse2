import asyncio
import httpx
import os
import json
from dotenv import load_dotenv
from services.levels_engine import LevelsEngine
from utils.patterns import detect_all_patterns, patterns_to_strings

load_dotenv()

# ============================================================================
# COINGECKO API CONFIGURATION
# ============================================================================

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"


def load_coingecko_ids() -> dict:
    """Load symbol → CoinGecko ID mapping."""
    try:
        with open("services/top100_coingecko_ids.json", "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading CoinGecko IDs: {e}")
        return {}


COINGECKO_IDS = load_coingecko_ids()

# CoinGecko OHLC endpoint granularity rules (free & demo tier):
#   days=1   → ~30-minute candles  (~48 rows)
#   days=7   → ~4-hour candles     (~42 rows)
#   days=14  → ~4-hour candles     (~84 rows)
#   days=30  → ~4-hour candles     (~180 rows)
#   days=90  → ~daily candles      (~90 rows)
#   days=180 → ~daily candles      (~180 rows)
#
# CoinGecko does NOT let you choose candle size — it picks automatically
# based on the days range. We pick the smallest days value that:
#   (a) returns the right approximate granularity for the timeframe, AND
#   (b) returns enough rows (≥ 50) for our indicator math.
#
# Practical mapping (tested against public API):
#   5m  → use days=1  (returns 30m candles; closest available short-term data)
#   15m → use days=1  (same as above)
#   30m → use days=1  (exactly 30m granularity)
#   1h  → use days=7  (returns 4h candles; downsample not possible, use as-is)
#   2h  → use days=14 (4h candles)
#   4h  → use days=30 (4h candles, ~180 rows — ideal)
#   8h  → use days=30 (4h candles; close enough)
#   1d  → use days=90 (daily candles)

COINGECKO_CANDLE_DAYS = {
    "5m":  1,
    "15m": 1,
    "30m": 1,
    "1h":  7,
    "2h":  14,
    "4h":  30,
    "8h":  30,
    "1d":  90,
}

# Minimum candle rows required per timeframe (lower bar for short-term
# timeframes where CoinGecko returns fewer rows for days=1).
COINGECKO_MIN_CANDLES = {
    "5m":  20,
    "15m": 20,
    "30m": 20,
    "1h":  20,
    "2h":  30,
    "4h":  50,
    "8h":  50,
    "1d":  50,
}


# ============================================================================
# SMART PRICE FORMATTER  (mirrors handler's fmt_price — no import cycle)
# ============================================================================

def _fmt(price: float) -> str:
    """Return a human-readable price string with appropriate decimals."""
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.3f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


# ============================================================================
# DATA FETCHING
# ============================================================================

async def fetch_candles_from_coingecko(symbol: str, timeframe: str, limit: int = 200) -> list | None:
    """Fetch OHLCV candles from CoinGecko public OHLC endpoint.

    CoinGecko's /ohlc endpoint returns arrays of exactly 5 elements:
        [timestamp_ms, open, high, low, close]
    The candle granularity is chosen automatically by CoinGecko based on
    the requested 'days' range — we cannot specify it directly.

    Returns a list of candle dicts, or None on any failure.
    """
    symbol_upper = symbol.upper()
    coin_id = COINGECKO_IDS.get(symbol_upper)
    if not coin_id:
        print(f"❌ {symbol} not found in CoinGecko ID mapping")
        return None

    days = COINGECKO_CANDLE_DAYS.get(timeframe, 7)
    min_required = COINGECKO_MIN_CANDLES.get(timeframe, 20)
    url = f"{COINGECKO_BASE_URL}/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": days}

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=headers)

        # ── HTTP-level errors ──────────────────────────────────────────
        if resp.status_code == 429:
            print(f"❌ CoinGecko rate limit hit for {symbol} — wait 60s")
            return None
        if resp.status_code != 200:
            print(f"❌ CoinGecko HTTP {resp.status_code} for {symbol}: {resp.text[:200]}")
            return None

        # ── Parse JSON ────────────────────────────────────────────────
        try:
            data = resp.json()
        except Exception as json_err:
            print(f"❌ CoinGecko JSON parse error for {symbol}: {json_err}")
            print(f"   Raw response (first 200 chars): {resp.text[:200]}")
            return None

        # ── Validate top-level shape ──────────────────────────────────
        # CoinGecko returns a list on success, a dict on error
        # e.g. {"error": "coin not found"} or {"status": {"error_code": 429}}
        if isinstance(data, dict):
            err_msg = (
                data.get("error")
                or data.get("status", {}).get("error_message")
                or str(data)
            )
            print(f"❌ CoinGecko API error for {symbol}: {err_msg}")
            return None

        if not isinstance(data, list):
            print(f"❌ Unexpected CoinGecko response type ({type(data)}) for {symbol}")
            return None

        if len(data) == 0:
            print(f"❌ CoinGecko returned empty list for {symbol} days={days}")
            return None

        # ── Parse each row defensively ────────────────────────────────
        candles = []
        skipped = 0
        for i, item in enumerate(data):
            # Every row must be a list/tuple with exactly 5 numeric elements
            if not isinstance(item, (list, tuple)) or len(item) < 5:
                skipped += 1
                continue
            try:
                candles.append({
                    "datetime": int(item[0]),
                    "open":     float(item[1]),
                    "high":     float(item[2]),
                    "low":      float(item[3]),
                    "close":    float(item[4]),
                    "volume":   0.0,   # CoinGecko OHLC endpoint has no volume
                })
            except (TypeError, ValueError) as row_err:
                skipped += 1
                if skipped <= 3:   # Only log first few to avoid spam
                    print(f"   ⚠️  Skipping malformed row {i}: {item} ({row_err})")

        if skipped:
            print(f"   ⚠️  Skipped {skipped}/{len(data)} malformed rows for {symbol}")

        if len(candles) < min_required:
            print(
                f"❌ Only {len(candles)} valid candles for {symbol}/{timeframe} "
                f"(need {min_required}, got {len(data)} raw rows from CoinGecko days={days})"
            )
            return None

        # ── Attach technical indicators ───────────────────────────────
        candles = _attach_indicators(candles)
        print(f"✅ Fetched {len(candles)} candles for {symbol}/{timeframe} (days={days})")
        return candles

    except httpx.TimeoutException:
        print(f"❌ CoinGecko timeout for {symbol}/{timeframe}")
        return None
    except httpx.RequestError as req_err:
        print(f"❌ CoinGecko network error for {symbol}: {req_err}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error fetching {symbol}: {e}")
        import traceback; traceback.print_exc()
        return None


# ============================================================================
# INDICATOR CALCULATION HELPERS
# ============================================================================

def _attach_indicators(candles: list) -> list:
    """Attach EMA20/50/200, RSI-14, and MACD to every candle in-place.

    Each series is guaranteed to be the same length as `candles` by the
    individual series functions. A safe accessor is used as a last-resort
    fallback in case of any future regression.
    """
    if not candles or len(candles) < 2:
        return candles

    n      = len(candles)
    closes = [c["close"] for c in candles]

    ema20  = _ema_series(closes, 20)
    ema50  = _ema_series(closes, 50)
    ema200 = _ema_series(closes, 200)
    rsi14  = _rsi_series(closes, 14)
    macd   = _macd_series(closes)

    # Safety-check lengths — log a warning but never crash
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
    """Return a full-length EMA series (len == len(prices)).

    Leading `period - 1` values are 0.0; index `period - 1` holds the
    seed SMA; subsequent values are the true EMA.
    """
    n = len(prices)
    if n == 0:
        return []
    if n < period:
        return [0.0] * n

    k = 2.0 / (period + 1)
    # Pad with zeros for the warm-up period (indices 0 … period-2)
    out = [0.0] * (period - 1)
    # Seed: SMA of first `period` prices lands at index period-1
    sma = sum(prices[:period]) / period
    out.append(sma)                         # now len(out) == period

    # EMA for indices period … n-1
    for i in range(period, n):
        out.append(prices[i] * k + out[-1] * (1 - k))

    assert len(out) == n, f"_ema_series bug: got {len(out)}, expected {n}"
    return out


def _rsi_series(prices: list, period: int = 14) -> list:
    """Return a full-length RSI series (len == len(prices)).

    Leading `period` values are 50.0 (neutral placeholder).
    Index `period` holds the first real RSI value.
    """
    n = len(prices)
    if n == 0:
        return []
    if n <= period:
        return [50.0] * n

    # ── Seed average gain/loss over first `period` changes ──────────
    # Changes: prices[1]-prices[0]  …  prices[period]-prices[period-1]
    # That's `period` differences using indices 0..period inclusive.
    gains  = [max(prices[i] - prices[i - 1], 0.0) for i in range(1, period + 1)]
    losses = [max(prices[i - 1] - prices[i], 0.0) for i in range(1, period + 1)]
    avg_gain = sum(gains)  / period
    avg_loss = sum(losses) / period

    # First RSI sits at index `period` (covers prices[0..period])
    if avg_loss == 0:
        first_rsi = 100.0
    else:
        first_rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    # Warm-up placeholders for indices 0 … period-1, then first real value
    out = [50.0] * period + [first_rsi]    # len == period + 1

    # ── Wilder smoothing for remaining prices ────────────────────────
    for i in range(period + 1, n):
        delta    = prices[i] - prices[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta,  0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
        rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        out.append(rsi)

    assert len(out) == n, f"_rsi_series bug: got {len(out)}, expected {n}"
    return out


def _macd_series(prices: list) -> list:
    """Return full-length MACD dicts (len == len(prices)).

    Leading values use zeroed placeholders until enough data exists.
    """
    n = len(prices)
    zero = {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
    if n == 0:
        return []
    if n < 26:
        return [zero] * n

    ema12 = _ema_series(prices, 12)
    ema26 = _ema_series(prices, 26)
    macd_line   = [ema12[i] - ema26[i] for i in range(n)]
    signal_line = _ema_series(macd_line, 9)

    result = [
        {
            "macd":      macd_line[i],
            "signal":    signal_line[i],
            "histogram": macd_line[i] - signal_line[i],
        }
        for i in range(n)
    ]

    assert len(result) == n, f"_macd_series bug: got {len(result)}, expected {n}"
    return result


async def _build_indicators_dict(candles: list) -> dict | None:
    """Extract indicators from the last candle and compute advanced ones."""
    if not candles:
        return None

    latest = candles[-1]
    closes = [c["close"] for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]

    # Advanced indicators from utils.indicators
    try:
        from utils.indicators import (
            calculate_stochastic, calculate_cci, calculate_atr,
            calculate_bbands, calculate_adx, calculate_williams_r, calculate_roc,
        )
        stoch_k, stoch_d            = calculate_stochastic(highs, lows, closes)
        cci                          = calculate_cci(highs, lows, closes)
        atr                          = calculate_atr(highs, lows, closes)
        bb_upper, bb_middle, bb_lower = calculate_bbands(closes)
        adx, plus_di, minus_di       = calculate_adx(highs, lows, closes)
        williams_r                   = calculate_williams_r(highs, lows, closes)
        roc                          = calculate_roc(closes)
    except Exception as e:
        print(f"⚠️  Advanced indicators failed: {e} — using defaults")
        stoch_k = stoch_d = 50.0
        cci = williams_r = roc = 0.0
        atr = latest["close"] * 0.02
        bb_upper = latest["close"] * 1.02
        bb_middle = latest["close"]
        bb_lower  = latest["close"] * 0.98
        adx = plus_di = minus_di = 0.0

    return {
        "price":      latest["close"],
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
# LEVEL NORMALISATION
# ============================================================================

def _normalise_level(raw: dict, fallback_price: float) -> dict:
    """
    Guarantee every level dict has the keys the handler expects:
        price, strength, touches
    and the extra keys the analyzer uses internally:
        price_lower, price_upper

    LevelsEngine may return various shapes; we handle all of them.
    """
    # ── price ─────────────────────────────────────────────────────────
    price = (
        raw.get("price")
        or raw.get("level")
        or raw.get("value")
        or fallback_price
    )
    price = float(price)

    # ── band ──────────────────────────────────────────────────────────
    price_lower = float(raw.get("price_lower") or raw.get("low")  or price * 0.995)
    price_upper = float(raw.get("price_upper") or raw.get("high") or price * 1.005)

    # ── strength ──────────────────────────────────────────────────────
    strength = str(raw.get("strength") or raw.get("type") or "Medium").capitalize()
    if strength not in ("Strong", "Medium", "Weak"):
        strength = "Medium"

    # ── touches ───────────────────────────────────────────────────────
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
    """
    Professional-grade trade setup analyzer.

    Scoring methodology:
    - Unbiased bullish / bearish signal counting
    - Multi-timeframe trend context via EMAs
    - Conservative confidence thresholds
    - ATR-based stop placement
    """

    def __init__(self):
        self.levels_engine = LevelsEngine()

    # ------------------------------------------------------------------ public

    async def analyze_setup(self, symbol: str, timeframe: str) -> dict | None:
        """Run the full analysis pipeline and return a setup dict."""
        try:
            print(f"🔄 Analyzing {symbol}/{timeframe}…")

            # 1. Raw candles
            candles = await fetch_candles_from_coingecko(symbol, timeframe)
            min_required = COINGECKO_MIN_CANDLES.get(timeframe, 20)
            if not candles or len(candles) < min_required:
                print(
                    f"❌ Insufficient candles for {symbol}/{timeframe} "
                    f"({len(candles) if candles else 0} < {min_required} required)"
                )
                return None

            # 2. Indicators
            indicators = await _build_indicators_dict(candles)
            if not indicators:
                print(f"❌ Indicator build failed for {symbol}")
                return None

            current_price = indicators["price"]

            # 3. Support / Resistance levels
            support_levels: list     = []
            resistance_levels: list  = []
            try:
                sr_data = await self.levels_engine.calculate_levels(
                    symbol=symbol, timeframe=timeframe, max_levels=5
                )
                raw_supports    = sr_data.get("support_levels", [])
                raw_resistances = sr_data.get("resistance_levels", [])

                # Override current_price if the engine provides a fresher value
                if sr_data.get("current_price"):
                    current_price = float(sr_data["current_price"])

                support_levels    = [_normalise_level(lvl, current_price) for lvl in raw_supports]
                resistance_levels = [_normalise_level(lvl, current_price) for lvl in raw_resistances]

            except Exception as e:
                print(f"⚠️  S/R levels failed for {symbol}: {e}")

            # 4. Chart patterns — keep as dicts so _score() can use
            #    direction and quality. Convert to strings only in the return.
            try:
                pattern_dicts = detect_all_patterns(candles, max_results=8)
            except Exception as e:
                print(f"⚠️  Pattern detection failed: {e}")
                pattern_dicts = []

            print(f"   Patterns detected: {len(pattern_dicts)}")

            # 5. Score  (pass raw dicts — _score handles List[Pattern])
            score_data = self._score(candles, indicators, support_levels, resistance_levels, pattern_dicts)

            # 6. Direction
            direction = self._direction(score_data)

            # 7. Trade levels
            trade = self._trade_levels(indicators, support_levels, resistance_levels, direction)

            # 8. Confidence
            confidence = self._confidence(score_data, indicators)

            # 9. Wait / entry conditions
            conditions = self._entry_conditions(indicators, direction, timeframe, score_data)

            print(
                f"✅ {symbol}/{timeframe} — score {score_data['score']}/100 "
                f"dir {direction}  conf {confidence}%"
            )

            return {
                # Core
                "score":          score_data["score"],
                "quality":        self._quality_label(score_data["score"]),
                "confidence":     confidence,
                "direction":      direction,
                "current_price":  current_price,
                "trend_context":  score_data["trend_context"],
                # Signals
                "bullish_signals":  score_data["bullish_signals"],
                "bearish_signals":  score_data["bearish_signals"],
                "risk_factors":     score_data["risk_factors"],
                # Levels for the handler
                "support_levels":     support_levels,
                "resistance_levels":  resistance_levels,
                "patterns":           patterns_to_strings(pattern_dicts[:5]),
                # Trade levels
                "entry_zone":      trade["entry_zone"],
                "stop_loss":       trade["stop_loss"],
                "take_profit_1":   trade["tp1"],
                "take_profit_2":   trade["tp2"],
                "risk_reward":     trade["rr_ratio"],
                # Meta
                "wait_for":    conditions,
                "indicators":  indicators,
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

    def _score(
        self,
        candles: list,
        indicators: dict,
        support_levels: list,
        resistance_levels: list,
        patterns: list,
    ) -> dict:
        """
        Unbiased signal scoring.
        Returns a dict with keys:
          score, bullish_score, bearish_score,
          bullish_signals, bearish_signals, risk_factors, trend_context
        """
        bull = 0
        bear = 0
        bull_signals: list[str] = []
        bear_signals: list[str] = []
        risks: list[str]        = []

        price   = self._safe(indicators, "price")
        ema20   = self._safe(indicators, "ema20")
        ema50   = self._safe(indicators, "ema50")
        ema200  = self._safe(indicators, "ema200")
        rsi     = self._safe(indicators, "rsi", 50.0)
        mhist   = self._safe(indicators, "macdHist")
        adx     = self._safe(indicators, "adx")
        plus_di = self._safe(indicators, "plusDI")
        minus_di= self._safe(indicators, "minusDI")
        stoch_k = self._safe(indicators, "stochK", 50.0)
        stoch_d = self._safe(indicators, "stochD", 50.0)
        bb_u    = self._safe(indicators, "bbUpper")
        bb_m    = self._safe(indicators, "bbMiddle")
        bb_l    = self._safe(indicators, "bbLower")
        cci     = self._safe(indicators, "cci")
        roc     = self._safe(indicators, "roc")

        # ── 1. Trend (EMA stack) ──────────────────────────────────────
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

        # ── 2. ADX trend strength ─────────────────────────────────────
        if adx:
            if adx > 25:
                if plus_di and minus_di:
                    if plus_di > minus_di:
                        bull += 10; bull_signals.append(f"Strong bullish trend (ADX {adx:.0f})")
                    else:
                        bear += 10; bear_signals.append(f"Strong bearish trend (ADX {adx:.0f})")
            elif adx < 20:
                risks.append(f"Weak trend (ADX {adx:.0f}) — avoid momentum trades")

        # ── 3. RSI ────────────────────────────────────────────────────
        if rsi:
            if 55 < rsi < 70:
                bull += 12; bull_signals.append(f"Bullish momentum (RSI {rsi:.0f})")
            elif 40 < rsi <= 55:
                bull += 5;  bull_signals.append(f"Neutral-bullish RSI ({rsi:.0f})")
            elif 30 < rsi < 45:
                bear += 5;  bear_signals.append(f"Neutral-bearish RSI ({rsi:.0f})")
            elif rsi <= 30:
                bear += 12; bear_signals.append(f"Bearish momentum (RSI {rsi:.0f})")
                bull_signals.append("Oversold — watch for bounce")
            elif rsi >= 70:
                bull += 12; bull_signals.append(f"Strong bullish RSI ({rsi:.0f})")
                risks.append(f"Overbought RSI ({rsi:.0f}) — pullback risk")

        # ── 4. MACD ───────────────────────────────────────────────────
        if mhist:
            if mhist > 0:
                bull += 10; bull_signals.append("MACD histogram positive")
            else:
                bear += 10; bear_signals.append("MACD histogram negative")

        # ── 5. Stochastic ─────────────────────────────────────────────
        if stoch_k and stoch_d:
            if stoch_k > stoch_d:
                if stoch_k < 80:
                    bull += 5; bull_signals.append(f"Stochastic bullish crossover ({stoch_k:.0f})")
                else:
                    risks.append(f"Stochastic overbought ({stoch_k:.0f})")
            else:
                if stoch_k > 20:
                    bear += 5; bear_signals.append(f"Stochastic bearish crossover ({stoch_k:.0f})")
                else:
                    bull_signals.append(f"Stochastic oversold ({stoch_k:.0f}) — bounce watch")

        # ── 6. CCI ────────────────────────────────────────────────────
        if cci:
            if cci > 100:
                bull += 3; bull_signals.append(f"CCI bullish ({cci:.0f})")
                if cci > 200: risks.append("CCI extremely overbought")
            elif cci < -100:
                bear += 3; bear_signals.append(f"CCI bearish ({cci:.0f})")
                if cci < -200: bull_signals.append("CCI oversold — bounce potential")

        # ── 7. ROC ────────────────────────────────────────────────────
        if roc:
            if roc > 5:
                bull += 5; bull_signals.append(f"Strong upward momentum (ROC {roc:.1f}%)")
            elif roc < -5:
                bear += 5; bear_signals.append(f"Strong downward momentum (ROC {roc:.1f}%)")

        # ── 8. Support / Resistance proximity ────────────────────────
        valid_sup = [lvl for lvl in support_levels    if lvl["price"] < price]
        valid_res = [lvl for lvl in resistance_levels if lvl["price"] > price]

        if valid_sup:
            nearest_s = max(valid_sup, key=lambda x: x["price"])
            dist_s = (price - nearest_s["price"]) / price * 100
            if dist_s < 2:
                bull += 12
                bull_signals.append(
                    f"At {nearest_s['strength'].lower()} support "
                    f"({_fmt(nearest_s['price'])}, -{dist_s:.1f}%)"
                )
            elif dist_s < 5:
                bull += 6; bull_signals.append(f"Near support (-{dist_s:.1f}%)")

        if valid_res:
            nearest_r = min(valid_res, key=lambda x: x["price"])
            dist_r = (nearest_r["price"] - price) / price * 100
            if dist_r < 2:
                bear += 12
                bear_signals.append(
                    f"At {nearest_r['strength'].lower()} resistance "
                    f"({_fmt(nearest_r['price'])}, +{dist_r:.1f}%)"
                )
                risks.append("Price at resistance — rejection risk")
            elif dist_r < 5:
                risks.append(f"Approaching resistance (+{dist_r:.1f}%)")
            else:
                bull += 6; bull_signals.append(f"Clear room to resistance (+{dist_r:.1f}%)")

        # ── 9. Bollinger Bands ────────────────────────────────────────
        if bb_u and bb_l and bb_m:
            if price > bb_u:
                bear += 3; risks.append("Price above upper Bollinger Band")
            elif price < bb_l:
                bull += 5; bull_signals.append("Price below lower Bollinger Band — bounce watch")
            elif price > bb_m:
                bull += 3; bull_signals.append("Price in upper Bollinger half")
            else:
                bear += 3; bear_signals.append("Price in lower Bollinger half")

        # ── 10. Chart patterns (quality + direction aware) ─────────────
        # patterns is List[Pattern] with keys: name, emoji, direction, quality, description
        _QUALITY_BONUS = {"HIGH": 8, "MEDIUM": 5, "LOW": 2}
        for p in patterns[:6]:
            if not isinstance(p, dict):
                continue   # skip if somehow a string slipped in
            direction_flag = p.get("direction", "NEUTRAL")
            quality        = p.get("quality",   "LOW")
            bonus          = _QUALITY_BONUS.get(quality, 2)
            label          = f"{p.get('emoji','•')} {p.get('name','Pattern')}: {p.get('description','')}"[:90]

            if direction_flag == "BULLISH":
                bull += bonus
                bull_signals.append(label)
            elif direction_flag == "BEARISH":
                bear += bonus
                bear_signals.append(label)
            else:
                # NEUTRAL patterns (e.g. Doji) add a small risk note
                risks.append(label)

        # ── Final score ───────────────────────────────────────────────
        net = bull - bear
        if net > 0:
            final = int(min(50 + net, 100))
        else:
            final = int(max(50 + net, 0))

        return {
            "score":           final,
            "bullish_score":   bull,
            "bearish_score":   bear,
            "bullish_signals": bull_signals,
            "bearish_signals": bear_signals,
            "risk_factors":    risks,
            "trend_context":   trend_context,
        }

    # ---------------------------------------------------------------- direction

    @staticmethod
    def _trend_context(price: float, ema20: float, ema50: float, ema200: float) -> str:
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

    @staticmethod
    def _direction(score_data: dict) -> str:
        score   = score_data["score"]
        trend   = score_data["trend_context"]

        if score > 65 and trend in ("STRONG_UPTREND", "UPTREND"):
            return "BULLISH"
        if score < 35 and trend in ("STRONG_DOWNTREND", "DOWNTREND"):
            return "BEARISH"
        if 55 <= score <= 65:
            return "BULLISH"
        if 35 <= score <= 45:
            return "BEARISH"
        return "NEUTRAL"

    # ------------------------------------------------------------- trade levels

    def _trade_levels(
        self,
        indicators: dict,
        support_levels: list,
        resistance_levels: list,
        direction: str,
    ) -> dict:
        """
        ATR-based stop placement with S/R awareness.
        All keys in the returned dict use the normalised level structure,
        so price_lower / price_upper are guaranteed to exist.
        """
        price = self._safe(indicators, "price")
        atr   = self._safe(indicators, "atr") or price * 0.02
        min_stop = atr * 1.5

        valid_sup = [lvl for lvl in support_levels    if lvl["price"] < price]
        valid_res = [lvl for lvl in resistance_levels if lvl["price"] > price]

        nearest_s = max(valid_sup, key=lambda x: x["price"]) if valid_sup else None
        nearest_r = min(valid_res, key=lambda x: x["price"]) if valid_res else None

        if direction == "BULLISH":
            entry_low  = price * 0.998
            entry_high = price * 1.002

            if nearest_s:
                # Stop below the bottom of the support band
                stop_loss = min(nearest_s["price_lower"] * 0.995, price - 2 * atr)
            else:
                stop_loss = price - 2 * atr

            # Enforce minimum distance
            if price - stop_loss < min_stop:
                stop_loss = price - min_stop

            risk = price - stop_loss

            if nearest_r:
                tp1 = min(nearest_r["price_lower"] * 0.995, price + risk * 2)
            else:
                tp1 = price + risk * 2
            tp2 = price + risk * 3

        elif direction == "BEARISH":
            entry_low  = price * 0.998
            entry_high = price * 1.002

            if nearest_r:
                stop_loss = max(nearest_r["price_upper"] * 1.005, price + 2 * atr)
            else:
                stop_loss = price + 2 * atr

            if stop_loss - price < min_stop:
                stop_loss = price + min_stop

            risk = stop_loss - price

            if nearest_s:
                tp1 = max(nearest_s["price_upper"] * 1.005, price - risk * 2)
            else:
                tp1 = price - risk * 2
            tp2 = price - risk * 3

        else:  # NEUTRAL
            entry_low  = price * 0.995
            entry_high = price * 1.005
            stop_loss  = price - 2 * atr
            tp1        = price + 2 * atr
            tp2        = price + 4 * atr

        risk   = abs(price - stop_loss)
        reward = abs(tp1   - price)
        rr     = round(reward / risk, 2) if risk else 0.0

        return {
            "entry_zone": (entry_low, entry_high),
            "stop_loss":  stop_loss,
            "tp1":        tp1,
            "tp2":        tp2,
            "rr_ratio":   rr,
        }

    # ---------------------------------------------------------------- confidence

    def _confidence(self, score_data: dict, indicators: dict) -> int:
        conf = 50

        bull_n = len(score_data["bullish_signals"])
        bear_n = len(score_data["bearish_signals"])
        risk_n = len(score_data["risk_factors"])

        # Signal alignment
        if bull_n > bear_n * 2 or bear_n > bull_n * 2:
            conf += 20
        elif abs(bull_n - bear_n) <= 2:
            conf -= 20

        # Trend context
        if score_data["trend_context"] in ("STRONG_UPTREND", "STRONG_DOWNTREND"):
            conf += 15
        elif score_data["trend_context"] == "RANGING":
            conf -= 15

        # ADX
        adx = self._safe(indicators, "adx")
        if adx:
            if adx > 30:  conf += 10
            elif adx < 20: conf -= 15

        # Risk factors penalise confidence
        if risk_n > 3:
            conf -= 15

        # Extreme scores boost confidence
        score = score_data["score"]
        if score > 75 or score < 25:
            conf += 10
        elif 45 <= score <= 55:
            conf -= 15

        return max(0, min(100, conf))

    # --------------------------------------------------------------- conditions

    def _entry_conditions(
        self,
        indicators: dict,
        direction: str,
        timeframe: str,
        score_data: dict,
    ) -> list[str]:
        conditions: list[str] = []
        price = self._safe(indicators, "price")
        rsi   = self._safe(indicators, "rsi")
        adx   = self._safe(indicators, "adx")

        if score_data["score"] < 60:
            conditions.append("⚠️ Setup quality too low — wait for a better opportunity")
            return conditions

        if direction == "BULLISH":
            conditions.append(f"Wait for {timeframe} close above {_fmt(price * 1.005)}")
            if rsi > 70:
                conditions.append("Wait for RSI to cool to the 60–65 range")
            if adx and adx < 20:
                conditions.append("Wait for trend strength to build (ADX > 20)")
            conditions.append("Confirm with above-average volume on the breakout candle")

        elif direction == "BEARISH":
            conditions.append(f"Wait for {timeframe} close below {_fmt(price * 0.995)}")
            if rsi < 30:
                conditions.append("Wait for RSI relief rally to 35–40 before entering short")
            if adx and adx < 20:
                conditions.append("Wait for trend strength to build (ADX > 20)")
            conditions.append("Confirm with above-average volume on the breakdown candle")

        else:
            conditions.append("⚠️ No clear directional bias — avoid trading this setup")
            conditions.append("Wait for price to break out of the current range with conviction")

        return conditions

    # ------------------------------------------------------------------ labels

    @staticmethod
    def _quality_label(score: int) -> str:
        """Human-readable quality label (used in the handler's legacy path)."""
        if score >= 75: return "EXCELLENT"
        if score >= 65: return "GOOD"
        if score >= 55: return "FAIR"
        if score >= 45: return "NEUTRAL"
        if score >= 35: return "FAIR (Bearish)"
        if score >= 25: return "GOOD (Bearish)"
        return "EXCELLENT (Bearish)"
