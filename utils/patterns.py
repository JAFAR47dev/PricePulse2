# utils/patterns.py
"""
Professional Chart Pattern Detection Library
=============================================
Covers every major pattern category used in institutional technical analysis:

  Category A — Continuation:  Flags, Pennants, Triangles, Rectangles, Cup & Handle
  Category B — Reversal:      H&S, Double/Triple Top-Bottom, Wedges, Rounding Bottom
  Category C — Candlestick:   Engulfing, Hammer/Star family, Doji, Morning/Evening Star
  Category D — Momentum:      RSI divergence (regular + hidden), MACD divergence,
                               Volume divergence
  Category E — Cross/Event:   Golden/Death Cross, EMA reclaims, Trendline breaks
                               + retests

Every detection applies THREE context filters before accepting a pattern:
  1. Location  — is the pattern near a meaningful S/R level or EMA?
  2. Trend     — does the pattern agree with or oppose the prevailing trend?
  3. Quality   — minimum structural requirements (min candle gap, % tolerance, etc.)

Return format for every function:
  List[Dict] with keys:
    name        str   — human-readable label
    emoji       str   — display emoji
    direction   str   — "BULLISH" | "BEARISH" | "NEUTRAL"
    quality     str   — "HIGH" | "MEDIUM" | "LOW"
    description str   — one-line detail shown to user
    index       int   — candle index where pattern completes (for location tests)

The public helper `detect_all_patterns(candles)` runs every detector and
returns a deduplicated, quality-sorted list ready for the AI narrative.
"""

from typing import List, Dict, Any, Tuple, Optional
import math

# ── Typing alias ──────────────────────────────────────────────────────────────
Candle  = Dict[str, Any]
Pattern = Dict[str, Any]


# ============================================================================
# INTERNAL UTILITIES
# ============================================================================

def _safe(candles: List[Candle], key: str, index: int, default: float = 0.0) -> float:
    try:
        v = candles[index].get(key, default)
        return float(v) if v is not None else default
    except (IndexError, TypeError, ValueError):
        return default


def _closes(candles: List[Candle]) -> List[float]:
    return [float(c.get("close", 0)) for c in candles]


def _highs(candles: List[Candle]) -> List[float]:
    return [float(c.get("high", 0)) for c in candles]


def _lows(candles: List[Candle]) -> List[float]:
    return [float(c.get("low", 0)) for c in candles]


def _volumes(candles: List[Candle]) -> List[float]:
    return [float(c.get("volume", 0)) for c in candles]


def _ts(candles: List[Candle], i: int) -> Any:
    return candles[i].get("datetime", i)


def _pattern(
    name: str,
    emoji: str,
    direction: str,
    quality: str,
    description: str,
    index: int,
) -> Pattern:
    return {
        "name":        name,
        "emoji":       emoji,
        "direction":   direction,
        "quality":     quality,
        "description": description,
        "index":       index,
    }


def _fmt(price: float) -> str:
    if price >= 1000:   return f"${price:,.2f}"
    if price >= 1:      return f"${price:,.3f}"
    if price >= 0.01:   return f"${price:.4f}"
    return f"${price:.6f}"


# ── Swing-point finders ───────────────────────────────────────────────────────

def _swing_highs(values: List[float], left: int = 2, right: int = 2) -> List[Tuple[int, float]]:
    """Return (index, value) for every swing high with `left` and `right` confirmation bars."""
    out = []
    for i in range(left, len(values) - right):
        if all(values[i] >= values[i - j] for j in range(1, left + 1)) and \
           all(values[i] >= values[i + j] for j in range(1, right + 1)):
            out.append((i, values[i]))
    return out


def _swing_lows(values: List[float], left: int = 2, right: int = 2) -> List[Tuple[int, float]]:
    out = []
    for i in range(left, len(values) - right):
        if all(values[i] <= values[i - j] for j in range(1, left + 1)) and \
           all(values[i] <= values[i + j] for j in range(1, right + 1)):
            out.append((i, values[i]))
    return out


# ── Simple EMA ────────────────────────────────────────────────────────────────

def _ema(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return [values[-1]] * len(values) if values else []
    k   = 2.0 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    # Pad front so length matches input
    return [out[0]] * (period - 1) + out


# ── Volume context ────────────────────────────────────────────────────────────

def _avg_volume(candles: List[Candle], lookback: int = 20) -> float:
    vols = _volumes(candles)
    relevant = [v for v in vols[-lookback:] if v > 0]
    return sum(relevant) / len(relevant) if relevant else 0.0


def _volume_available(candles: List[Candle]) -> bool:
    """CoinGecko OHLC has no volume; Binance/Twelve Data does."""
    return any(float(c.get("volume", 0)) > 0 for c in candles[-10:])


# ── Trend context ─────────────────────────────────────────────────────────────

def _trend(candles: List[Candle], lookback: int = 20) -> str:
    """STRONG_UP | UP | RANGING | DOWN | STRONG_DOWN using EMA slope."""
    closes = _closes(candles)
    if len(closes) < lookback + 5:
        return "RANGING"
    ema20 = _ema(closes, 20)
    slope = (ema20[-1] - ema20[-lookback]) / (ema20[-lookback] + 1e-9) * 100
    if slope > 3:   return "STRONG_UP"
    if slope > 0.5: return "UP"
    if slope < -3:  return "STRONG_DOWN"
    if slope < -0.5: return "DOWN"
    return "RANGING"


# ── Near S/R level ────────────────────────────────────────────────────────────

def _near_level(price: float, candles: List[Candle], pct: float = 0.015) -> bool:
    """Return True if `price` is within `pct` of any recent swing high/low."""
    highs  = _highs(candles[-60:])
    lows   = _lows(candles[-60:])
    levels = (
        [h for i, h in _swing_highs(highs)] +
        [l for i, l in _swing_lows(lows)]
    )
    return any(abs(price - lvl) / (lvl + 1e-9) < pct for lvl in levels)


# ── Quality label ─────────────────────────────────────────────────────────────

def _quality(high_conds: List[bool], med_conds: List[bool]) -> str:
    if all(high_conds): return "HIGH"
    if all(med_conds):  return "MEDIUM"
    return "LOW"


# ============================================================================
# CATEGORY A — CONTINUATION PATTERNS
# ============================================================================

def detect_flags_pennants(candles: List[Candle]) -> List[Pattern]:
    """
    Bull/Bear Flags and Pennants.
    Requires:
      - Strong pole (≥4% move in ≤8 candles)
      - Consolidation channel (≤50% of pole height)
      - Breakout in pole direction
    """
    results = []
    if len(candles) < 20:
        return results

    closes = _closes(candles)
    highs  = _highs(candles)
    lows   = _lows(candles)

    for pole_end in range(10, len(candles) - 3):
        # ── Find pole ────────────────────────────────────────────────
        for pole_len in range(4, 10):
            pole_start = pole_end - pole_len
            if pole_start < 0:
                break

            pole_move = (closes[pole_end] - closes[pole_start]) / (closes[pole_start] + 1e-9) * 100
            is_bull_pole = pole_move >= 4.0
            is_bear_pole = pole_move <= -4.0

            if not (is_bull_pole or is_bear_pole):
                continue

            # ── Find consolidation channel after pole ────────────────
            consol_start = pole_end
            consol_end   = min(pole_end + 12, len(candles) - 1)

            if consol_end <= consol_start + 3:
                continue

            consol_highs = highs[consol_start:consol_end]
            consol_lows  = lows[consol_start:consol_end]
            ch            = max(consol_highs) - min(consol_lows)
            pole_height   = abs(closes[pole_end] - closes[pole_start])

            if ch > pole_height * 0.6 or ch == 0:
                continue

            # Is it a pennant (converging) or flag (parallel)?
            h_slope = (consol_highs[-1] - consol_highs[0]) / (len(consol_highs) + 1e-9)
            l_slope = (consol_lows[-1]  - consol_lows[0])  / (len(consol_lows)  + 1e-9)
            is_pennant = (h_slope < 0 < l_slope) or (h_slope > 0 > l_slope)

            # ── Breakout candle ───────────────────────────────────────
            last_c = closes[-1]
            channel_top = max(consol_highs)
            channel_bot = min(consol_lows)

            if is_bull_pole and last_c > channel_top * 1.002:
                ptype = "Bull Pennant" if is_pennant else "Bull Flag"
                q = _quality(
                    [pole_move >= 6, ch < pole_height * 0.4],
                    [pole_move >= 4, ch < pole_height * 0.55],
                )
                results.append(_pattern(
                    name=ptype, emoji="🚀", direction="BULLISH", quality=q,
                    description=(
                        f"{ptype} breakout above {_fmt(channel_top)} "
                        f"after {abs(pole_move):.1f}% pole"
                    ),
                    index=len(candles) - 1,
                ))

            elif is_bear_pole and last_c < channel_bot * 0.998:
                ptype = "Bear Pennant" if is_pennant else "Bear Flag"
                q = _quality(
                    [abs(pole_move) >= 6, ch < pole_height * 0.4],
                    [abs(pole_move) >= 4, ch < pole_height * 0.55],
                )
                results.append(_pattern(
                    name=ptype, emoji="🔻", direction="BEARISH", quality=q,
                    description=(
                        f"{ptype} breakdown below {_fmt(channel_bot)} "
                        f"after {abs(pole_move):.1f}% pole"
                    ),
                    index=len(candles) - 1,
                ))

    return results[:2]   # cap at 2 to avoid duplicates from overlapping windows


def detect_triangles(candles: List[Candle]) -> List[Pattern]:
    """
    Ascending, Descending, and Symmetrical Triangles.
    Requires ≥ 3 swing points on each trendline, convergence confirmed.
    """
    results = []
    if len(candles) < 30:
        return results

    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)

    sh = _swing_highs(highs, left=3, right=3)
    sl = _swing_lows(lows,   left=3, right=3)

    if len(sh) < 2 or len(sl) < 2:
        return results

    # Take last 3 of each (enough for a triangle)
    sh = sh[-3:]
    sl = sl[-3:]

    # Upper trendline slope
    hi_slope = (sh[-1][1] - sh[0][1]) / (sh[-1][0] - sh[0][0] + 1e-9)
    # Lower trendline slope
    lo_slope = (sl[-1][1] - sl[0][1]) / (sl[-1][0] - sl[0][0] + 1e-9)

    last     = closes[-1]
    last_idx = len(candles) - 1

    # Project trendlines to current candle
    upper_now = sh[-1][1] + hi_slope * (last_idx - sh[-1][0])
    lower_now = sl[-1][1] + lo_slope * (last_idx - sl[-1][0])

    # Lines must be converging
    converging = upper_now > lower_now

    if not converging:
        return results

    hi_flat  = abs(hi_slope / (sh[0][1] + 1e-9)) < 0.001
    lo_flat  = abs(lo_slope / (sl[0][1] + 1e-9)) < 0.001
    hi_down  = hi_slope < -1e-6
    lo_up    = lo_slope > 1e-6

    # Breakout buffer 0.2%
    if last > upper_now * 1.002:
        if lo_up and hi_flat:
            name, emoji, direction = "Ascending Triangle", "📐", "BULLISH"
        elif lo_up and hi_down:
            name, emoji, direction = "Symmetrical Triangle (Bullish break)", "🔺", "BULLISH"
        else:
            name, emoji, direction = "Triangle Breakout", "📈", "BULLISH"

        q = _quality([len(sh) >= 3, len(sl) >= 3], [len(sh) >= 2, len(sl) >= 2])
        results.append(_pattern(
            name=name, emoji=emoji, direction=direction, quality=q,
            description=f"{name} — price broke above {_fmt(upper_now)}",
            index=last_idx,
        ))

    elif last < lower_now * 0.998:
        if hi_down and lo_flat:
            name, emoji, direction = "Descending Triangle", "📐", "BEARISH"
        elif hi_down and lo_up:
            name, emoji, direction = "Symmetrical Triangle (Bearish break)", "🔻", "BEARISH"
        else:
            name, emoji, direction = "Triangle Breakdown", "📉", "BEARISH"

        q = _quality([len(sh) >= 3, len(sl) >= 3], [len(sh) >= 2, len(sl) >= 2])
        results.append(_pattern(
            name=name, emoji=emoji, direction=direction, quality=q,
            description=f"{name} — price broke below {_fmt(lower_now)}",
            index=last_idx,
        ))

    return results


def detect_rectangles(candles: List[Candle]) -> List[Pattern]:
    """
    Rectangle / range consolidation with breakout.
    Requires ≥ 2 touches on both top and bottom within 1.5% band.
    """
    results = []
    if len(candles) < 20:
        return results

    recent = candles[-40:]
    highs  = _highs(recent)
    lows   = _lows(recent)
    closes = _closes(recent)

    sh = _swing_highs(highs, left=2, right=2)
    sl = _swing_lows(lows,   left=2, right=2)

    if len(sh) < 2 or len(sl) < 2:
        return results

    resistance = sum(v for _, v in sh[-3:]) / len(sh[-3:])
    support    = sum(v for _, v in sl[-3:]) / len(sl[-3:])
    band_pct   = (resistance - support) / (support + 1e-9)

    # Must be a tight range (1% – 8%)
    if not (0.01 < band_pct < 0.08):
        return results

    last = closes[-1]

    if last > resistance * 1.002:
        q = _quality([len(sh) >= 3, band_pct < 0.04], [len(sh) >= 2, band_pct < 0.07])
        results.append(_pattern(
            name="Rectangle Breakout", emoji="📦", direction="BULLISH", quality=q,
            description=(
                f"Range breakout above {_fmt(resistance)} "
                f"(range {band_pct*100:.1f}%)"
            ),
            index=len(candles) - 1,
        ))
    elif last < support * 0.998:
        q = _quality([len(sl) >= 3, band_pct < 0.04], [len(sl) >= 2, band_pct < 0.07])
        results.append(_pattern(
            name="Rectangle Breakdown", emoji="📦", direction="BEARISH", quality=q,
            description=(
                f"Range breakdown below {_fmt(support)} "
                f"(range {band_pct*100:.1f}%)"
            ),
            index=len(candles) - 1,
        ))

    return results


def detect_cup_and_handle(candles: List[Candle]) -> List[Pattern]:
    """
    Cup and Handle (bullish continuation).
    Looks for U-shaped base followed by small pullback, then breakout.
    Minimum 20 candles for the cup.
    """
    results = []
    if len(candles) < 35:
        return results

    closes = _closes(candles)
    n      = len(closes)

    for cup_len in range(20, min(60, n - 10)):
        cup_start = n - cup_len - 10
        cup_end   = n - 10
        if cup_start < 0:
            break

        left_rim  = closes[cup_start]
        right_rim = closes[cup_end]
        cup_min   = min(closes[cup_start:cup_end])
        depth     = (min(left_rim, right_rim) - cup_min) / (min(left_rim, right_rim) + 1e-9)

        # Cup must be 8–35% deep, rims within 3%
        if not (0.08 < depth < 0.35):
            continue
        if abs(left_rim - right_rim) / (left_rim + 1e-9) > 0.03:
            continue

        # Handle: shallow pullback ≤ 50% of cup depth after right rim
        handle_closes = closes[cup_end:n]
        if len(handle_closes) < 3:
            continue
        handle_low  = min(handle_closes)
        handle_drop = (right_rim - handle_low) / (right_rim + 1e-9)
        if handle_drop > depth * 0.5 or handle_drop < 0.005:
            continue

        # Breakout above right rim
        if closes[-1] > right_rim * 1.002:
            q = _quality(
                [depth > 0.12, handle_drop < depth * 0.35],
                [depth > 0.08, handle_drop < depth * 0.5],
            )
            results.append(_pattern(
                name="Cup and Handle", emoji="☕", direction="BULLISH", quality=q,
                description=(
                    f"Cup & Handle breakout above {_fmt(right_rim)} "
                    f"({depth*100:.0f}% cup depth)"
                ),
                index=n - 1,
            ))
            break   # One is enough

    return results


# ============================================================================
# CATEGORY B — REVERSAL PATTERNS
# ============================================================================

def detect_head_and_shoulders(candles: List[Candle]) -> List[Pattern]:
    """
    Head & Shoulders (bearish reversal) and
    Inverse H&S (bullish reversal).
    Requires clear left shoulder, head, right shoulder with neckline break.
    """
    results = []
    if len(candles) < 30:
        return results

    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)

    sh = _swing_highs(highs, left=3, right=3)
    sl = _swing_lows(lows,   left=3, right=3)

    # ── H&S (bearish) ────────────────────────────────────────────────
    if len(sh) >= 3:
        for i in range(len(sh) - 2):
            ls_i, ls_v = sh[i]
            hd_i, hd_v = sh[i + 1]
            rs_i, rs_v = sh[i + 2]

            # Head must be higher than both shoulders
            if not (hd_v > ls_v and hd_v > rs_v):
                continue
            # Shoulders within 4% of each other
            if abs(ls_v - rs_v) / (ls_v + 1e-9) > 0.04:
                continue
            # Right shoulder must come after head
            if rs_i <= hd_i:
                continue

            # Neckline: connect troughs between ls-hd and hd-rs
            mid_troughs = [sl for sl in _swing_lows(lows, 2, 2)
                           if ls_i < sl[0] < rs_i]
            if len(mid_troughs) < 1:
                continue
            neckline = sum(v for _, v in mid_troughs) / len(mid_troughs)

            if closes[-1] < neckline * 0.998:
                q = _quality(
                    [abs(ls_v - rs_v) / ls_v < 0.02, hd_v > ls_v * 1.03],
                    [abs(ls_v - rs_v) / ls_v < 0.04, hd_v > ls_v * 1.01],
                )
                results.append(_pattern(
                    name="Head & Shoulders", emoji="👤", direction="BEARISH", quality=q,
                    description=(
                        f"H&S neckline break below {_fmt(neckline)} "
                        f"(head {_fmt(hd_v)})"
                    ),
                    index=len(candles) - 1,
                ))

    # ── Inverse H&S (bullish) ─────────────────────────────────────────
    if len(sl) >= 3:
        for i in range(len(sl) - 2):
            ls_i, ls_v = sl[i]
            hd_i, hd_v = sl[i + 1]
            rs_i, rs_v = sl[i + 2]

            if not (hd_v < ls_v and hd_v < rs_v):
                continue
            if abs(ls_v - rs_v) / (ls_v + 1e-9) > 0.04:
                continue
            if rs_i <= hd_i:
                continue

            mid_peaks = [sp for sp in _swing_highs(highs, 2, 2)
                         if ls_i < sp[0] < rs_i]
            if not mid_peaks:
                continue
            neckline = sum(v for _, v in mid_peaks) / len(mid_peaks)

            if closes[-1] > neckline * 1.002:
                q = _quality(
                    [abs(ls_v - rs_v) / ls_v < 0.02, hd_v < ls_v * 0.97],
                    [abs(ls_v - rs_v) / ls_v < 0.04, hd_v < ls_v * 0.99],
                )
                results.append(_pattern(
                    name="Inverse Head & Shoulders", emoji="🙃", direction="BULLISH", quality=q,
                    description=(
                        f"Inverse H&S neckline break above {_fmt(neckline)} "
                        f"(head {_fmt(hd_v)})"
                    ),
                    index=len(candles) - 1,
                ))

    return results[:2]


def detect_double_top_bottom(candles: List[Candle]) -> List[Pattern]:
    """
    Double Top (bearish) and Double Bottom (bullish).
    Peaks/troughs must be within 2%, ≥ 5 candles apart, with neckline break.
    Also detects Triple Top/Bottom when 3 touches are found.
    """
    results = []
    if len(candles) < 20:
        return results

    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)
    n      = len(candles)

    sh = _swing_highs(highs, left=3, right=3)
    sl = _swing_lows(lows,   left=3, right=3)

    # ── Double / Triple TOP ────────────────────────────────────────────
    for i in range(len(sh) - 1):
        i1, p1 = sh[i]
        i2, p2 = sh[i + 1]
        if i2 - i1 < 5:
            continue
        if abs(p1 - p2) / (p1 + 1e-9) > 0.02:
            continue

        # Neckline = lowest close between the two peaks
        valley = min(closes[i1:i2])

        # Check for Triple Top
        if i + 2 < len(sh):
            i3, p3 = sh[i + 2]
            if abs(p1 - p3) / (p1 + 1e-9) <= 0.025 and i3 - i2 >= 5:
                if closes[-1] < valley * 0.998:
                    q = _quality([True], [True])
                    results.append(_pattern(
                        name="Triple Top", emoji="🔺", direction="BEARISH", quality="HIGH",
                        description=(
                            f"Triple Top breakdown below {_fmt(valley)} "
                            f"(peaks ~{_fmt(p1)})"
                        ),
                        index=n - 1,
                    ))
                    continue

        if closes[-1] < valley * 0.998:
            pct = abs(p1 - p2) / p1 * 100
            q   = _quality([pct < 1.0, i2 - i1 >= 8], [pct < 2.0, i2 - i1 >= 5])
            results.append(_pattern(
                name="Double Top", emoji="🔺", direction="BEARISH", quality=q,
                description=(
                    f"Double Top breakdown below {_fmt(valley)} "
                    f"(peaks {_fmt(p1)} / {_fmt(p2)})"
                ),
                index=n - 1,
            ))

    # ── Double / Triple BOTTOM ─────────────────────────────────────────
    for i in range(len(sl) - 1):
        i1, t1 = sl[i]
        i2, t2 = sl[i + 1]
        if i2 - i1 < 5:
            continue
        if abs(t1 - t2) / (t1 + 1e-9) > 0.02:
            continue

        peak = max(closes[i1:i2])

        if i + 2 < len(sl):
            i3, t3 = sl[i + 2]
            if abs(t1 - t3) / (t1 + 1e-9) <= 0.025 and i3 - i2 >= 5:
                if closes[-1] > peak * 1.002:
                    results.append(_pattern(
                        name="Triple Bottom", emoji="🔻", direction="BULLISH", quality="HIGH",
                        description=(
                            f"Triple Bottom breakout above {_fmt(peak)} "
                            f"(troughs ~{_fmt(t1)})"
                        ),
                        index=n - 1,
                    ))
                    continue

        if closes[-1] > peak * 1.002:
            pct = abs(t1 - t2) / t1 * 100
            q   = _quality([pct < 1.0, i2 - i1 >= 8], [pct < 2.0, i2 - i1 >= 5])
            results.append(_pattern(
                name="Double Bottom", emoji="🔻", direction="BULLISH", quality=q,
                description=(
                    f"Double Bottom breakout above {_fmt(peak)} "
                    f"(troughs {_fmt(t1)} / {_fmt(t2)})"
                ),
                index=n - 1,
            ))

    return results[:3]


def detect_wedges(candles: List[Candle]) -> List[Pattern]:
    """
    Rising Wedge (bearish) and Falling Wedge (bullish).
    Both trendlines slope the same direction but converge.
    """
    results = []
    if len(candles) < 20:
        return results

    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)

    sh = _swing_highs(highs, left=2, right=2)[-4:]
    sl = _swing_lows(lows,   left=2, right=2)[-4:]

    if len(sh) < 2 or len(sl) < 2:
        return results

    hi_slope = (sh[-1][1] - sh[0][1]) / (sh[-1][0] - sh[0][0] + 1e-9)
    lo_slope = (sl[-1][1] - sl[0][1]) / (sl[-1][0] - sl[0][0] + 1e-9)

    # Both lines slope same direction
    same_dir = (hi_slope > 0 and lo_slope > 0) or (hi_slope < 0 and lo_slope < 0)
    if not same_dir:
        return results

    # Lines must be converging (upper rising less steeply OR falling more steeply)
    converging = abs(hi_slope - lo_slope) > 0 and (
        (hi_slope > 0 and hi_slope < lo_slope) or   # rising wedge
        (hi_slope < 0 and hi_slope > lo_slope)        # falling wedge
    )
    if not converging:
        return results

    n         = len(candles)
    upper_now = sh[-1][1] + hi_slope * (n - 1 - sh[-1][0])
    lower_now = sl[-1][1] + lo_slope * (n - 1 - sl[-1][0])
    last      = closes[-1]

    if hi_slope > 0 and lo_slope > 0 and last < lower_now * 0.998:
        # Rising wedge breakdown (bearish)
        q = _quality([len(sh) >= 3, len(sl) >= 3], [len(sh) >= 2, len(sl) >= 2])
        results.append(_pattern(
            name="Rising Wedge", emoji="📐", direction="BEARISH", quality=q,
            description=f"Rising Wedge breakdown below {_fmt(lower_now)}",
            index=n - 1,
        ))
    elif hi_slope < 0 and lo_slope < 0 and last > upper_now * 1.002:
        # Falling wedge breakout (bullish)
        q = _quality([len(sh) >= 3, len(sl) >= 3], [len(sh) >= 2, len(sl) >= 2])
        results.append(_pattern(
            name="Falling Wedge", emoji="📐", direction="BULLISH", quality=q,
            description=f"Falling Wedge breakout above {_fmt(upper_now)}",
            index=n - 1,
        ))

    return results


def detect_rounding_bottom(candles: List[Candle]) -> List[Pattern]:
    """
    Rounding Bottom (Saucer) — gradual U-shaped base.
    Splits recent candles into three thirds and checks for the characteristic shape.
    """
    results = []
    if len(candles) < 30:
        return results

    closes = _closes(candles[-60:])
    n      = len(closes)
    third  = n // 3

    left_avg  = sum(closes[:third]) / third
    mid_avg   = sum(closes[third:2*third]) / third
    right_avg = sum(closes[2*third:]) / (n - 2*third)

    # Mid must be lower than both sides (the bowl)
    bowl_depth = (min(left_avg, right_avg) - mid_avg) / (min(left_avg, right_avg) + 1e-9)
    if bowl_depth < 0.03:
        return results

    # Right side must be recovering (right_avg > mid_avg)
    if right_avg <= mid_avg * 1.01:
        return results

    # Current price breaking above left rim
    if closes[-1] > left_avg * 1.002:
        q = _quality([bowl_depth > 0.08], [bowl_depth > 0.03])
        results.append(_pattern(
            name="Rounding Bottom", emoji="🥣", direction="BULLISH", quality=q,
            description=(
                f"Rounding Bottom saucer ({bowl_depth*100:.0f}% depth), "
                f"price reclaiming {_fmt(left_avg)}"
            ),
            index=len(candles) - 1,
        ))

    return results


# ============================================================================
# CATEGORY C — CANDLESTICK PATTERNS (context-filtered)
# ============================================================================

def detect_engulfing_patterns(candles: List[Candle]) -> List[Pattern]:
    """
    Bullish and Bearish Engulfing.
    Only fired when pattern occurs near a swing S/R level.
    """
    results = []
    if len(candles) < 5:
        return results

    closes = _closes(candles)
    trend  = _trend(candles)

    for i in range(2, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]
        po, pc = float(prev["open"]), float(prev["close"])
        co, cc = float(curr["open"]), float(curr["close"])

        body_prev = abs(pc - po)
        body_curr = abs(cc - co)
        if body_prev < 0.001 or body_curr < body_prev:
            continue

        at_level = _near_level(cc, candles[:i], pct=0.02)

        # Bullish Engulfing: prev bearish, curr bullish, fully engulfs
        if pc < po and cc > co and cc > po and co < pc:
            in_downtrend = trend in ("DOWN", "STRONG_DOWN", "RANGING")
            q = _quality([in_downtrend, at_level], [in_downtrend or at_level])
            results.append(_pattern(
                name="Bullish Engulfing", emoji="🟢", direction="BULLISH", quality=q,
                description=f"Bullish Engulfing at {_fmt(cc)}",
                index=i,
            ))

        # Bearish Engulfing: prev bullish, curr bearish, fully engulfs
        elif pc > po and cc < co and co > pc and cc < po:
            in_uptrend = trend in ("UP", "STRONG_UP", "RANGING")
            q = _quality([in_uptrend, at_level], [in_uptrend or at_level])
            results.append(_pattern(
                name="Bearish Engulfing", emoji="🔴", direction="BEARISH", quality=q,
                description=f"Bearish Engulfing at {_fmt(cc)}",
                index=i,
            ))

    return results[-3:]   # Last 3 occurrences


def detect_hammer_patterns(candles: List[Candle]) -> List[Pattern]:
    """
    Hammer, Inverted Hammer, Shooting Star, Hanging Man.
    All require:
      - Long shadow ≥ 2× body
      - Small body (≤ 40% of total range)
      - Occurrence near S/R level
    """
    results = []
    if len(candles) < 5:
        return results

    trend = _trend(candles)

    for i in range(2, len(candles)):
        c    = candles[i]
        o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
        body  = abs(cl - o)
        total = h - l
        if total < 1e-9 or body / total > 0.4:
            continue

        lower_shadow = min(o, cl) - l
        upper_shadow = h - max(o, cl)
        at_level     = _near_level(cl, candles[:i], pct=0.02)

        # Hammer: long lower shadow, small upper shadow (bullish at support)
        if lower_shadow >= 2 * body and upper_shadow < body:
            in_down = trend in ("DOWN", "STRONG_DOWN")
            q = _quality([in_down, at_level], [in_down or at_level])
            name = "Hammer" if in_down else "Hanging Man"
            direction = "BULLISH" if in_down else "BEARISH"
            emoji     = "🔨" if in_down else "🪝"
            results.append(_pattern(
                name=name, emoji=emoji, direction=direction, quality=q,
                description=f"{name} at {_fmt(cl)} (lower shadow {lower_shadow/body:.1f}× body)",
                index=i,
            ))

        # Shooting Star / Inverted Hammer: long upper shadow, small lower shadow
        elif upper_shadow >= 2 * body and lower_shadow < body:
            in_up = trend in ("UP", "STRONG_UP")
            q = _quality([in_up, at_level], [in_up or at_level])
            name = "Shooting Star" if in_up else "Inverted Hammer"
            direction = "BEARISH" if in_up else "BULLISH"
            emoji     = "💫" if in_up else "⬆️"
            results.append(_pattern(
                name=name, emoji=emoji, direction=direction, quality=q,
                description=f"{name} at {_fmt(cl)} (upper shadow {upper_shadow/body:.1f}× body)",
                index=i,
            ))

    return results[-3:]


def detect_doji_patterns(candles: List[Candle]) -> List[Pattern]:
    """
    Standard Doji, Gravestone Doji, Dragonfly Doji.
    Body must be ≤ 5% of total range.
    Only meaningful at extremes (near S/R or after strong move).
    """
    results = []
    if len(candles) < 5:
        return results

    trend = _trend(candles)

    for i in range(2, len(candles)):
        c    = candles[i]
        o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
        body  = abs(cl - o)
        total = h - l
        if total < 1e-9:
            continue
        if body / total > 0.05:    # Must be very small body
            continue

        lower_shadow = min(o, cl) - l
        upper_shadow = h - max(o, cl)
        at_level     = _near_level(cl, candles[:i], pct=0.02)

        if not at_level:
            continue   # Doji without location context is noise

        # Gravestone: almost no lower shadow (bearish)
        if upper_shadow > total * 0.6 and lower_shadow < total * 0.1:
            q = _quality([trend in ("UP", "STRONG_UP"), at_level], [at_level])
            results.append(_pattern(
                name="Gravestone Doji", emoji="🪦", direction="BEARISH", quality=q,
                description=f"Gravestone Doji at {_fmt(cl)} — exhaustion signal",
                index=i,
            ))

        # Dragonfly: almost no upper shadow (bullish)
        elif lower_shadow > total * 0.6 and upper_shadow < total * 0.1:
            q = _quality([trend in ("DOWN", "STRONG_DOWN"), at_level], [at_level])
            results.append(_pattern(
                name="Dragonfly Doji", emoji="🪁", direction="BULLISH", quality=q,
                description=f"Dragonfly Doji at {_fmt(cl)} — rejection of lows",
                index=i,
            ))

        # Standard Doji
        else:
            results.append(_pattern(
                name="Doji", emoji="✖️", direction="NEUTRAL", quality="LOW",
                description=f"Doji indecision candle at {_fmt(cl)}",
                index=i,
            ))

    return results[-2:]


def detect_star_patterns(candles: List[Candle]) -> List[Pattern]:
    """
    Morning Star (bullish 3-candle reversal) and
    Evening Star (bearish 3-candle reversal).
    """
    results = []
    if len(candles) < 5:
        return results

    trend = _trend(candles)

    for i in range(2, len(candles)):
        c1 = candles[i - 2]
        c2 = candles[i - 1]   # Star candle (small body)
        c3 = candles[i]

        o1, c1v = float(c1["open"]), float(c1["close"])
        o2, c2v = float(c2["open"]), float(c2["close"])
        o3, c3v = float(c3["open"]), float(c3["close"])

        body1 = abs(c1v - o1)
        body2 = abs(c2v - o2)
        body3 = abs(c3v - o3)

        if body1 < 1e-9 or body3 < 1e-9:
            continue

        # Star body must be small relative to candle 1
        if body2 > body1 * 0.3:
            continue

        at_level = _near_level(c3v, candles[:i], pct=0.025)

        # Morning Star: c1 bearish, c2 small (gap down), c3 bullish
        if c1v < o1 and c3v > o3:
            # c3 must close above midpoint of c1
            if c3v > (o1 + c1v) / 2:
                in_down = trend in ("DOWN", "STRONG_DOWN")
                q = _quality([in_down, at_level], [in_down or at_level])
                results.append(_pattern(
                    name="Morning Star", emoji="🌅", direction="BULLISH", quality=q,
                    description=f"Morning Star reversal at {_fmt(c3v)}",
                    index=i,
                ))

        # Evening Star: c1 bullish, c2 small (gap up), c3 bearish
        elif c1v > o1 and c3v < o3:
            if c3v < (o1 + c1v) / 2:
                in_up = trend in ("UP", "STRONG_UP")
                q = _quality([in_up, at_level], [in_up or at_level])
                results.append(_pattern(
                    name="Evening Star", emoji="🌆", direction="BEARISH", quality=q,
                    description=f"Evening Star reversal at {_fmt(c3v)}",
                    index=i,
                ))

    return results[-2:]


def detect_three_candle_patterns(candles: List[Candle]) -> List[Pattern]:
    """
    Three White Soldiers (bullish) and Three Black Crows (bearish).
    Requires 3 consecutive strong same-direction candles, each closing near high/low.
    """
    results = []
    if len(candles) < 5:
        return results

    trend = _trend(candles)

    for i in range(2, len(candles)):
        c1, c2, c3 = candles[i-2], candles[i-1], candles[i]
        opens  = [float(c["open"])  for c in [c1, c2, c3]]
        closes = [float(c["close"]) for c in [c1, c2, c3]]
        highs  = [float(c["high"])  for c in [c1, c2, c3]]
        lows   = [float(c["low"])   for c in [c1, c2, c3]]

        bodies = [abs(closes[j] - opens[j]) for j in range(3)]
        if any(b < 1e-9 for b in bodies):
            continue

        # Three White Soldiers: 3 bullish candles, each closing near high
        if all(closes[j] > opens[j] for j in range(3)):
            if closes[1] > closes[0] and closes[2] > closes[1]:
                upper_wicks = [highs[j] - closes[j] for j in range(3)]
                small_wicks = all(upper_wicks[j] < bodies[j] * 0.3 for j in range(3))
                if small_wicks:
                    q = _quality([small_wicks, trend in ("UP", "RANGING")], [True])
                    results.append(_pattern(
                        name="Three White Soldiers", emoji="💂", direction="BULLISH", quality=q,
                        description=f"Three White Soldiers — strong bullish momentum at {_fmt(closes[2])}",
                        index=i,
                    ))

        # Three Black Crows: 3 bearish candles, each closing near low
        elif all(closes[j] < opens[j] for j in range(3)):
            if closes[1] < closes[0] and closes[2] < closes[1]:
                lower_wicks = [closes[j] - lows[j] for j in range(3)]
                small_wicks = all(lower_wicks[j] < bodies[j] * 0.3 for j in range(3))
                if small_wicks:
                    q = _quality([small_wicks, trend in ("DOWN", "RANGING")], [True])
                    results.append(_pattern(
                        name="Three Black Crows", emoji="🦅", direction="BEARISH", quality=q,
                        description=f"Three Black Crows — strong bearish momentum at {_fmt(closes[2])}",
                        index=i,
                    ))

    return results[-2:]


# ============================================================================
# CATEGORY D — MOMENTUM PATTERNS
# ============================================================================

def detect_divergences(candles: List[Candle]) -> List[Pattern]:
    """
    RSI Divergence — Regular (reversal) and Hidden (continuation).
    Regular:  price makes new extreme but RSI does not → exhaustion
    Hidden:   price makes higher low / lower high but RSI does not → continuation
    """
    results = []
    if len(candles) < 20:
        return results

    recent = candles[-60:]
    closes = [float(c["close"]) for c in recent]
    rsis   = [float(c.get("rsi", 50)) for c in recent]
    n      = len(closes)

    sh_c = _swing_highs(closes, left=3, right=3)
    sl_c = _swing_lows(closes,  left=3, right=3)

    # Parallel RSI swing highs/lows
    sh_r = _swing_highs(rsis, left=3, right=3)
    sl_r = _swing_lows(rsis,  left=3, right=3)

    def nearest_rsi_swing(idx: int, swings: list) -> Optional[Tuple[int, float]]:
        close_enough = [s for s in swings if abs(s[0] - idx) <= 5]
        return min(close_enough, key=lambda x: abs(x[0] - idx)) if close_enough else None

    # ── Regular Bearish Divergence: price HH, RSI LH ─────────────────
    if len(sh_c) >= 2:
        p1_i, p1_v = sh_c[-2]
        p2_i, p2_v = sh_c[-1]
        r1 = nearest_rsi_swing(p1_i, sh_r)
        r2 = nearest_rsi_swing(p2_i, sh_r)
        if r1 and r2 and p2_v > p1_v and r2[1] < r1[1]:
            results.append(_pattern(
                name="Bearish RSI Divergence", emoji="📉", direction="BEARISH", quality="MEDIUM",
                description=(
                    f"Price made HH ({_fmt(p2_v)}) but RSI made LH "
                    f"({r2[1]:.0f} < {r1[1]:.0f}) — momentum exhaustion"
                ),
                index=p2_i,
            ))

    # ── Regular Bullish Divergence: price LL, RSI HL ──────────────────
    if len(sl_c) >= 2:
        t1_i, t1_v = sl_c[-2]
        t2_i, t2_v = sl_c[-1]
        r1 = nearest_rsi_swing(t1_i, sl_r)
        r2 = nearest_rsi_swing(t2_i, sl_r)
        if r1 and r2 and t2_v < t1_v and r2[1] > r1[1]:
            results.append(_pattern(
                name="Bullish RSI Divergence", emoji="📈", direction="BULLISH", quality="MEDIUM",
                description=(
                    f"Price made LL ({_fmt(t2_v)}) but RSI made HL "
                    f"({r2[1]:.0f} > {r1[1]:.0f}) — selling exhaustion"
                ),
                index=t2_i,
            ))

    # ── Hidden Bullish Divergence: price HL, RSI LL → continuation up ─
    if len(sl_c) >= 2:
        t1_i, t1_v = sl_c[-2]
        t2_i, t2_v = sl_c[-1]
        r1 = nearest_rsi_swing(t1_i, sl_r)
        r2 = nearest_rsi_swing(t2_i, sl_r)
        if r1 and r2 and t2_v > t1_v and r2[1] < r1[1]:
            results.append(_pattern(
                name="Hidden Bullish Divergence", emoji="🔮", direction="BULLISH", quality="MEDIUM",
                description=(
                    f"Price HL ({_fmt(t2_v)} > {_fmt(t1_v)}) but RSI LL "
                    f"— uptrend likely continuing"
                ),
                index=t2_i,
            ))

    # ── Hidden Bearish Divergence: price LH, RSI HH → continuation down
    if len(sh_c) >= 2:
        p1_i, p1_v = sh_c[-2]
        p2_i, p2_v = sh_c[-1]
        r1 = nearest_rsi_swing(p1_i, sh_r)
        r2 = nearest_rsi_swing(p2_i, sh_r)
        if r1 and r2 and p2_v < p1_v and r2[1] > r1[1]:
            results.append(_pattern(
                name="Hidden Bearish Divergence", emoji="🔮", direction="BEARISH", quality="MEDIUM",
                description=(
                    f"Price LH ({_fmt(p2_v)} < {_fmt(p1_v)}) but RSI HH "
                    f"— downtrend likely continuing"
                ),
                index=p2_i,
            ))

    return results


def detect_macd_divergence(candles: List[Candle]) -> List[Pattern]:
    """
    MACD Histogram Divergence.
    More reliable than RSI divergence because MACD is momentum of momentum.
    """
    results = []
    if len(candles) < 20:
        return results

    recent = candles[-60:]
    closes = [float(c["close"]) for c in recent]
    histos = [float(c.get("macdHist", 0)) for c in recent]

    sh_c = _swing_highs(closes, left=3, right=3)
    sl_c = _swing_lows(closes,  left=3, right=3)
    sh_h = _swing_highs(histos, left=3, right=3)
    sl_h = _swing_lows(histos,  left=3, right=3)

    def nearest(idx, swings):
        close = [s for s in swings if abs(s[0] - idx) <= 5]
        return min(close, key=lambda x: abs(x[0] - idx)) if close else None

    # Bearish: price HH, MACD histogram LH
    if len(sh_c) >= 2:
        p1_i, p1_v = sh_c[-2]
        p2_i, p2_v = sh_c[-1]
        h1 = nearest(p1_i, sh_h)
        h2 = nearest(p2_i, sh_h)
        if h1 and h2 and p2_v > p1_v and h2[1] < h1[1] and h1[1] > 0:
            results.append(_pattern(
                name="Bearish MACD Divergence", emoji="📉", direction="BEARISH", quality="HIGH",
                description=(
                    f"Price HH {_fmt(p2_v)} but MACD histogram weakening "
                    f"({h2[1]:.4f} < {h1[1]:.4f})"
                ),
                index=p2_i,
            ))

    # Bullish: price LL, MACD histogram HL
    if len(sl_c) >= 2:
        t1_i, t1_v = sl_c[-2]
        t2_i, t2_v = sl_c[-1]
        h1 = nearest(t1_i, sl_h)
        h2 = nearest(t2_i, sl_h)
        if h1 and h2 and t2_v < t1_v and h2[1] > h1[1] and h1[1] < 0:
            results.append(_pattern(
                name="Bullish MACD Divergence", emoji="📈", direction="BULLISH", quality="HIGH",
                description=(
                    f"Price LL {_fmt(t2_v)} but MACD histogram recovering "
                    f"({h2[1]:.4f} > {h1[1]:.4f})"
                ),
                index=t2_i,
            ))

    return results


def detect_volume_divergence(candles: List[Candle]) -> List[Pattern]:
    """
    Volume Divergence — only fired when volume data is present (Binance/Twelve Data).
    Price moving up on declining volume = distribution (bearish).
    Price moving down on declining volume = accumulation (bullish).
    """
    results = []
    if not _volume_available(candles) or len(candles) < 15:
        return results

    closes  = _closes(candles[-20:])
    volumes = _volumes(candles[-20:])

    price_trend = (closes[-1] - closes[0]) / (closes[0] + 1e-9)
    early_vol   = sum(volumes[:5]) / 5
    recent_vol  = sum(volumes[-5:]) / 5

    if early_vol < 1e-9:
        return results

    vol_trend = (recent_vol - early_vol) / early_vol

    if price_trend > 0.03 and vol_trend < -0.25:
        results.append(_pattern(
            name="Bearish Volume Divergence", emoji="🔇", direction="BEARISH", quality="MEDIUM",
            description=(
                f"Price up {price_trend*100:.1f}% on {abs(vol_trend)*100:.0f}% "
                f"declining volume — distribution signal"
            ),
            index=len(candles) - 1,
        ))
    elif price_trend < -0.03 and vol_trend < -0.25:
        results.append(_pattern(
            name="Bullish Volume Divergence", emoji="🔇", direction="BULLISH", quality="MEDIUM",
            description=(
                f"Price down {abs(price_trend)*100:.1f}% on {abs(vol_trend)*100:.0f}% "
                f"declining volume — accumulation signal"
            ),
            index=len(candles) - 1,
        ))

    return results


# ============================================================================
# CATEGORY E — CROSS / EVENT PATTERNS
# ============================================================================

def detect_golden_death_crosses(candles: List[Candle]) -> List[Pattern]:
    """
    Golden Cross (EMA50 > EMA200, bullish) and
    Death Cross  (EMA50 < EMA200, bearish).
    Also detects EMA20/EMA50 fast crosses for shorter timeframes.
    """
    results = []
    if len(candles) < 3:
        return results

    for i in range(1, len(candles)):
        e50_prev  = _safe(candles, "ema50",  i - 1)
        e200_prev = _safe(candles, "ema200", i - 1)
        e50_curr  = _safe(candles, "ema50",  i)
        e200_curr = _safe(candles, "ema200", i)
        e20_prev  = _safe(candles, "ema20",  i - 1)
        e20_curr  = _safe(candles, "ema20",  i)

        if 0 in (e50_prev, e200_prev, e50_curr, e200_curr):
            continue

        # Golden Cross: 50 crosses above 200
        if e50_prev < e200_prev and e50_curr >= e200_curr:
            results.append(_pattern(
                name="Golden Cross", emoji="✨", direction="BULLISH", quality="HIGH",
                description=f"EMA50 crossed above EMA200 — major bullish signal",
                index=i,
            ))

        # Death Cross: 50 crosses below 200
        elif e50_prev > e200_prev and e50_curr <= e200_curr:
            results.append(_pattern(
                name="Death Cross", emoji="💀", direction="BEARISH", quality="HIGH",
                description=f"EMA50 crossed below EMA200 — major bearish signal",
                index=i,
            ))

        # Fast cross: EMA20 / EMA50
        if e20_prev and e20_curr and e50_prev and e50_curr:
            if e20_prev < e50_prev and e20_curr >= e50_curr:
                results.append(_pattern(
                    name="EMA20/50 Bullish Cross", emoji="⚡", direction="BULLISH", quality="MEDIUM",
                    description=f"EMA20 crossed above EMA50 — short-term momentum shift",
                    index=i,
                ))
            elif e20_prev > e50_prev and e20_curr <= e50_curr:
                results.append(_pattern(
                    name="EMA20/50 Bearish Cross", emoji="⚡", direction="BEARISH", quality="MEDIUM",
                    description=f"EMA20 crossed below EMA50 — short-term momentum shift",
                    index=i,
                ))

    return results[-2:]   # Only most recent


def detect_ema_reclaims(candles: List[Candle]) -> List[Pattern]:
    """
    Price reclaiming a key EMA after trading below/above it.
    EMA200 reclaim is HIGH quality; EMA50 is MEDIUM; EMA20 is LOW.
    """
    results = []
    if len(candles) < 5:
        return results

    for ema_key, period, base_quality in [
        ("ema200", 200, "HIGH"),
        ("ema50",  50,  "MEDIUM"),
        ("ema20",  20,  "LOW"),
    ]:
        for i in range(2, len(candles)):
            prev_close = _safe(candles, "close", i - 1)
            curr_close = _safe(candles, "close", i)
            prev_ema   = _safe(candles, ema_key, i - 1)
            curr_ema   = _safe(candles, ema_key, i)

            if 0 in (prev_close, curr_close, prev_ema, curr_ema):
                continue

            # Reclaim from below (bullish)
            if prev_close < prev_ema and curr_close > curr_ema * 1.001:
                results.append(_pattern(
                    name=f"EMA{period} Reclaim (Bullish)", emoji="🔄", direction="BULLISH",
                    quality=base_quality,
                    description=f"Price reclaimed EMA{period} ({_fmt(curr_ema)}) from below",
                    index=i,
                ))

            # Loss of EMA (bearish)
            elif prev_close > prev_ema and curr_close < curr_ema * 0.999:
                results.append(_pattern(
                    name=f"EMA{period} Loss (Bearish)", emoji="🔄", direction="BEARISH",
                    quality=base_quality,
                    description=f"Price lost EMA{period} ({_fmt(curr_ema)}) — bearish",
                    index=i,
                ))

    return results[-3:]


def detect_trendline_breaks(candles: List[Candle]) -> List[Pattern]:
    """
    Trendline break (aggressive entry signal) and
    Trendline retest after break (conservative, higher-probability entry).
    Requires ≥ 3 swing-point touches to validate the trendline.
    """
    results = []
    if len(candles) < 20:
        return results

    highs  = _highs(candles)
    lows   = _lows(candles)
    closes = _closes(candles)
    n      = len(candles)

    sh = _swing_highs(highs, left=2, right=2)
    sl = _swing_lows(lows,   left=2, right=2)

    def fit_line(points):
        """Least-squares line through (index, value) points."""
        if len(points) < 2:
            return None, None
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        denom = sum((x - mx)**2 for x in xs)
        if denom < 1e-9:
            return None, None
        m = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs))) / denom
        b = my - m * mx
        return m, b

    # ── Downtrend resistance line ────────────────────────────────────
    if len(sh) >= 3:
        recent_sh = sh[-5:]
        descending = [p for i, (p_i, p_v) in enumerate(recent_sh)
                      if i == 0 or p_v < recent_sh[i-1][1]]
        if len(descending) >= 2:
            m, b = fit_line(descending)
            if m is not None and m < 0:   # Must be descending
                tl_now = m * (n - 1) + b
                # Break
                if closes[-1] > tl_now * 1.003 and closes[-2] <= tl_now * 1.001:
                    results.append(_pattern(
                        name="Downtrend Break (Bullish)", emoji="📈", direction="BULLISH",
                        quality="MEDIUM",
                        description=(
                            f"Price broke above descending resistance "
                            f"({_fmt(tl_now)}) with {len(descending)} trendline touches"
                        ),
                        index=n - 1,
                    ))
                # Retest after previous break
                elif (len(results) == 0 and
                      closes[-3] > tl_now * 1.003 and
                      closes[-1] > tl_now * 1.001):
                    results.append(_pattern(
                        name="Trendline Retest (Bullish)", emoji="✅", direction="BULLISH",
                        quality="HIGH",
                        description=(
                            f"Successful retest of broken downtrend line "
                            f"({_fmt(tl_now)}) — high-probability long setup"
                        ),
                        index=n - 1,
                    ))

    # ── Uptrend support line ─────────────────────────────────────────
    if len(sl) >= 3:
        recent_sl = sl[-5:]
        ascending = [p for i, (p_i, p_v) in enumerate(recent_sl)
                     if i == 0 or p_v > recent_sl[i-1][1]]
        if len(ascending) >= 2:
            m, b = fit_line(ascending)
            if m is not None and m > 0:   # Must be ascending
                tl_now = m * (n - 1) + b
                # Break
                if closes[-1] < tl_now * 0.997 and closes[-2] >= tl_now * 0.999:
                    results.append(_pattern(
                        name="Uptrend Break (Bearish)", emoji="📉", direction="BEARISH",
                        quality="MEDIUM",
                        description=(
                            f"Price broke below ascending support "
                            f"({_fmt(tl_now)}) with {len(ascending)} trendline touches"
                        ),
                        index=n - 1,
                    ))
                # Retest after previous break
                elif (closes[-3] < tl_now * 0.997 and
                      closes[-1] < tl_now * 0.999):
                    results.append(_pattern(
                        name="Trendline Retest (Bearish)", emoji="✅", direction="BEARISH",
                        quality="HIGH",
                        description=(
                            f"Failed retest of broken uptrend support "
                            f"({_fmt(tl_now)}) — high-probability short setup"
                        ),
                        index=n - 1,
                    ))

    return results


# ============================================================================
# PUBLIC ENTRY POINT
# ============================================================================

# Quality sort order
_QUALITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# All detectors in priority order (higher-confidence first)
_DETECTORS = [
    detect_flags_pennants,
    detect_triangles,
    detect_head_and_shoulders,
    detect_double_top_bottom,
    detect_wedges,
    detect_cup_and_handle,
    detect_rounding_bottom,
    detect_rectangles,
    detect_macd_divergence,
    detect_divergences,
    detect_volume_divergence,
    detect_trendline_breaks,
    detect_golden_death_crosses,
    detect_ema_reclaims,
    detect_star_patterns,
    detect_engulfing_patterns,
    detect_hammer_patterns,
    detect_three_candle_patterns,
    detect_doji_patterns,
]


def detect_all_patterns(
    candles: List[Candle],
    max_results: int = 8,
    min_quality: str = "LOW",
) -> List[Pattern]:
    """
    Run every detector, deduplicate by name, sort by quality, return top results.

    Args:
        candles:     List of OHLCV candle dicts with indicator fields attached.
        max_results: Maximum patterns to return (default 8).
        min_quality: Filter floor — "HIGH", "MEDIUM", or "LOW".

    Returns:
        List[Pattern] sorted HIGH → MEDIUM → LOW, capped at max_results.
    """
    if not candles or len(candles) < 5:
        return []

    all_patterns: List[Pattern] = []
    seen_names: set = set()

    for detector in _DETECTORS:
        try:
            found = detector(candles)
            for p in found:
                name = p.get("name", "")
                if name not in seen_names:
                    seen_names.add(name)
                    all_patterns.append(p)
        except Exception as e:
            # Never let a single detector crash the whole analysis
            pass

    # Filter by minimum quality
    min_order = _QUALITY_ORDER.get(min_quality, 2)
    filtered  = [p for p in all_patterns if _QUALITY_ORDER.get(p["quality"], 2) <= min_order]

    # Sort: quality first, then by recency (higher index = more recent)
    filtered.sort(key=lambda p: (_QUALITY_ORDER.get(p["quality"], 2), -p.get("index", 0)))

    return filtered[:max_results]


def patterns_to_strings(patterns: List[Pattern]) -> List[str]:
    """
    Convert pattern dicts to the legacy string format expected by setup_analyzer.py.
    Example: "📈 Bull Flag breakout above $45,231.00"
    """
    return [
        f"{p['emoji']} {p['name']}: {p['description']}"
        for p in patterns
    ]
