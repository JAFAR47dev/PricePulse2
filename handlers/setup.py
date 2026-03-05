from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from services.setup_analyzer import SetupAnalyzer
from services.performance_tracker import PerformanceTracker
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak
import json
import os
import logging
import httpx

logger = logging.getLogger(__name__)

setup_analyzer      = SetupAnalyzer()
performance_tracker = PerformanceTracker()

VALID_TIMEFRAMES = ["5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]

OUTCOME_WINDOWS = {
    "5m":  {"4h": 0.33, "24h": 2,   "72h": 6},
    "15m": {"4h": 1,    "24h": 6,   "72h": 18},
    "30m": {"4h": 2,    "24h": 12,  "72h": 36},
    "1h":  {"4h": 4,    "24h": 24,  "72h": 72},
    "2h":  {"4h": 8,    "24h": 48,  "72h": 96},
    "4h":  {"4h": 16,   "24h": 96,  "72h": 192},
    "8h":  {"4h": 32,   "24h": 192, "72h": 384},
    "1d":  {"4h": 96,   "24h": 480, "72h": 960},
}


# ============================================================================
# HTML HELPERS
# ============================================================================

def h(text: str) -> str:
    """Escape a string for safe use inside an HTML Telegram message."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def b(text: str) -> str:
    """Bold."""
    return f"<b>{h(text)}</b>"


def code(text: str) -> str:
    """Inline code."""
    return f"<code>{h(text)}</code>"


def line(char: str = "─", n: int = 29) -> str:
    return char * n + "\n"


# ============================================================================
# SUPPORTED COINS
# ============================================================================

def load_supported_coins():
    try:
        json_path = os.path.join("services", "top100_coingecko_ids.json")
        with open(json_path, "r") as f:
            data    = json.load(f)
            symbols = set(symbol.upper() for symbol in data.keys())
            logger.info(f"Loaded {len(symbols)} supported coins")
            return symbols
    except FileNotFoundError:
        logger.error("top100_coingecko_ids.json not found")
        return get_fallback_coins()
    except Exception as e:
        logger.error(f"Error loading supported coins: {e}")
        return get_fallback_coins()


def get_fallback_coins():
    return {
        "BTC", "ETH", "USDT", "BNB", "XRP", "USDC", "SOL", "TRX", "DOGE",
        "ADA", "AVAX", "SHIB", "DOT", "MATIC", "LTC", "LINK", "UNI", "ATOM",
        "TON", "ICP", "FIL", "ARB", "OP", "AAVE", "MKR", "PEPE", "WIF",
    }


SUPPORTED_COINS = load_supported_coins()


# ============================================================================
# PRICE FORMATTING
# ============================================================================

def fmt_price(price: float) -> str:
    if price >= 1000:   return f"${price:,.2f}"
    elif price >= 1:    return f"${price:,.3f}"
    elif price >= 0.01: return f"${price:.4f}"
    else:               return f"${price:.6f}"


def fmt_price_plain(price: float) -> str:
    return fmt_price(price).lstrip("$")


# ============================================================================
# AI NARRATIVE
# ============================================================================

async def get_ai_narrative(setup_data: dict, symbol: str, timeframe: str) -> dict:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set — using rule-based narrative")
        return _rule_based_narrative(setup_data, symbol, timeframe)

    score         = setup_data.get("score", 50)
    direction     = setup_data.get("direction", "NEUTRAL")
    confidence    = setup_data.get("confidence", 50)
    current_price = setup_data.get("current_price", 0)
    trend_context = setup_data.get("trend_context", "RANGING")
    htf_trend     = setup_data.get("htf_trend", "UNKNOWN")
    htf_tf        = setup_data.get("htf_timeframe", "")
    support_levels    = setup_data.get("support_levels", [])
    resistance_levels = setup_data.get("resistance_levels", [])
    bullish_signals   = setup_data.get("bullish_signals", [])
    bearish_signals   = setup_data.get("bearish_signals", [])
    entry_zone  = setup_data.get("entry_zone",    [current_price * 0.99, current_price * 1.01])
    stop_loss   = setup_data.get("stop_loss",     current_price * 0.97)
    tp1         = setup_data.get("take_profit_1", current_price * 1.03)
    tp2         = setup_data.get("take_profit_2", current_price * 1.06)

    nearest_support    = support_levels[0]["price"]    if support_levels    else current_price * 0.97
    nearest_resistance = resistance_levels[0]["price"] if resistance_levels else current_price * 1.03

    entry_mid = (entry_zone[0] + entry_zone[1]) / 2.0
    if direction == "BULLISH":
        tp1_safe      = max(tp1, entry_mid * 1.005)
        tp2_safe      = max(tp2, entry_mid * 1.010)
        risk_for_1to2 = (tp1_safe - entry_mid) / 2.0
        sl_tight      = max(entry_mid - risk_for_1to2, entry_mid * 0.90)
        sl_tight      = min(sl_tight, entry_mid - 0.0001)
    elif direction == "BEARISH":
        tp1_safe      = min(tp1, entry_mid * 0.995)
        tp2_safe      = min(tp2, entry_mid * 0.990)
        risk_for_1to2 = (entry_mid - tp1_safe) / 2.0
        sl_tight      = min(entry_mid + risk_for_1to2, entry_mid * 1.10)
        sl_tight      = max(sl_tight, entry_mid + 0.0001)
    else:
        tp1_safe = tp1; tp2_safe = tp2; sl_tight = stop_loss

    sl_side  = "below" if direction != "BEARISH" else "above"
    htf_line = f"- Higher timeframe ({htf_tf}): {htf_trend}" if htf_tf else ""

    prompt = f"""You are a professional crypto trader writing a concise setup brief for {symbol}/USDT on the {timeframe} timeframe.

Market data:
- Price: {fmt_price(current_price)}
- Direction: {direction}
- Trend ({timeframe}): {trend_context}
{htf_line}
- Setup score: {score}/100
- Confidence: {confidence}%
- Nearest support: {fmt_price(nearest_support)}
- Nearest resistance: {fmt_price(nearest_resistance)}
- Entry zone: {fmt_price(entry_zone[0])} - {fmt_price(entry_zone[1])}
- Stop loss (tight, 1:2 rule): {fmt_price(sl_tight)}
- TP1: {fmt_price(tp1_safe)}  TP2: {fmt_price(tp2_safe)}
- Risk:Reward: minimum 1:2 enforced
- Bullish signals: {', '.join(bullish_signals[:4]) if bullish_signals else 'None'}
- Bearish signals: {', '.join(bearish_signals[:4]) if bearish_signals else 'None'}

Write a short analysis paragraph then THREE pipe-delimited scenario lines.
No section headers. No labels. No preamble. No closing remarks.

First: write 3-5 plain sentences (no bullet points, no special characters, no markdown)
describing chart structure, where price sits relative to key levels, momentum, HTF
alignment, and best/base/worst outcomes.

Then immediately output the three scenario lines:
BREAKOUT|<probability 5-40>%|<1-sentence trigger>|{fmt_price_plain(entry_zone[1])}|{fmt_price_plain(tp1_safe)}|{fmt_price_plain(sl_tight)}
PULLBACK_LONG|<probability 20-70>%|<1-sentence trigger>|{fmt_price_plain(entry_zone[0])}|{fmt_price_plain(tp1_safe)}/{fmt_price_plain(tp2_safe)}|{fmt_price_plain(sl_tight)}
BREAKDOWN|<probability 5-40>%|<1-sentence trigger>|<next major level>

Hard rules:
- Probabilities must sum to 100.
- Mark the highest-probability scenario with PREFERRED at the end of its trigger sentence.
- Stop loss {fmt_price(sl_tight)} must be {sl_side} every TP. Never invert this.
- Output ONLY the paragraph + the three scenario lines. Nothing else.
- Use plain text only. No asterisks, underscores, backticks, or any markdown symbols."""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/your_bot",
                },
                json={
                    "model": "anthropic/claude-3-haiku",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        return _parse_ai_response(raw, setup_data, symbol, timeframe)

    except Exception as e:
        logger.warning(f"OpenRouter call failed ({e}) — using rule-based narrative")
        return _rule_based_narrative(setup_data, symbol, timeframe)


def _parse_ai_response(raw: str, setup_data: dict, symbol: str, timeframe: str) -> dict:
    try:
        lines          = raw.split("\n")
        analysis_lines = []
        scenario_lines = []
        in_scenarios   = False

        for line_text in lines:
            stripped = line_text.strip()
            if not stripped:
                continue
            if stripped.startswith(("BREAKOUT|", "PULLBACK_LONG|", "PULLBACK SHORT|", "BREAKDOWN|")):
                in_scenarios = True
            if in_scenarios:
                scenario_lines.append(stripped)
            else:
                analysis_lines.append(stripped)

        analysis = " ".join(analysis_lines).strip()

        scenarios = []
        emoji_map = {
            "BREAKOUT":      "1️⃣",
            "PULLBACK_LONG": "2️⃣",
            "PULLBACK SHORT":"2️⃣",
            "BREAKDOWN":     "3️⃣",
        }
        label_map = {
            "BREAKOUT":      "BREAKOUT",
            "PULLBACK_LONG": "PULLBACK LONG",
            "PULLBACK SHORT":"PULLBACK SHORT",
            "BREAKDOWN":     "BREAKDOWN",
        }

        for sline in scenario_lines:
            parts     = sline.split("|")
            if len(parts) < 3:
                continue
            stype     = parts[0].strip()
            prob      = parts[1].strip()
            trigger   = parts[2].strip()
            preferred = "PREFERRED" in trigger.upper()
            trigger   = trigger.replace("PREFERRED", "").replace("preferred", "").strip(" .-")
            entry     = parts[3].strip() if len(parts) > 3 else ""
            tp        = parts[4].strip() if len(parts) > 4 else ""
            sl        = parts[5].strip() if len(parts) > 5 else ""
            scenarios.append({
                "emoji":     emoji_map.get(stype, "🔹"),
                "label":     label_map.get(stype, stype),
                "prob":      prob,
                "trigger":   trigger,
                "entry":     entry,
                "tp":        tp,
                "sl":        sl,
                "preferred": preferred,
            })

        if not analysis or not scenarios:
            raise ValueError("Incomplete AI parse")

        return {"analysis": analysis, "scenarios": scenarios}

    except Exception as e:
        logger.warning(f"AI response parse failed: {e}")
        return _rule_based_narrative(setup_data, symbol, timeframe)


def _rule_based_narrative(setup_data: dict, symbol: str, timeframe: str) -> dict:
    direction     = setup_data.get("direction", "NEUTRAL")
    trend_context = setup_data.get("trend_context", "RANGING")
    htf_trend     = setup_data.get("htf_trend", "")
    htf_tf        = setup_data.get("htf_timeframe", "")
    current_price = setup_data.get("current_price", 0)
    support_levels    = setup_data.get("support_levels", [])
    resistance_levels = setup_data.get("resistance_levels", [])
    entry_zone = setup_data.get("entry_zone",    [current_price * 0.99, current_price * 1.01])
    stop_loss  = setup_data.get("stop_loss",     current_price * 0.97)
    tp1        = setup_data.get("take_profit_1", current_price * 1.03)
    tp2        = setup_data.get("take_profit_2", current_price * 1.06)

    nearest_s = support_levels[0]["price"]    if support_levels    else current_price * 0.97
    nearest_r = resistance_levels[0]["price"] if resistance_levels else current_price * 1.03

    htf_clause = ""
    if htf_tf and htf_trend:
        aligns = direction.upper() in htf_trend.upper()
        word   = "confirming" if aligns else "conflicting with"
        htf_clause = f" The {htf_tf} trend is {htf_trend.lower().replace('_', ' ')}, {word} this setup."

    if direction == "BULLISH":
        analysis = (
            f"Structure is bullish with price above key support at {fmt_price(nearest_s)}.{htf_clause} "
            f"The {trend_context.lower()} trend suggests momentum may continue, though overhead resistance "
            f"at {fmt_price(nearest_r)} could slow progress. "
            f"Best case: clean breakout above {fmt_price(nearest_r)}. "
            f"Base case: consolidation before next leg. "
            f"Worst case: loss of {fmt_price(nearest_s)} triggers deeper correction."
        )
        scenarios = [
            {"emoji": "1️⃣", "label": "BREAKOUT",      "prob": "25%",
             "trigger": f"Close above {fmt_price(nearest_r)} with volume",
             "entry": fmt_price_plain(entry_zone[1]), "tp": fmt_price_plain(tp1),
             "sl": fmt_price_plain(stop_loss), "preferred": False},
            {"emoji": "2️⃣", "label": "PULLBACK LONG", "prob": "55%",
             "trigger": f"Dip to {fmt_price(entry_zone[0])}-{fmt_price(entry_zone[1])} zone",
             "entry": fmt_price_plain(entry_zone[0]),
             "tp": f"{fmt_price_plain(tp1)}/{fmt_price_plain(tp2)}",
             "sl": fmt_price_plain(stop_loss), "preferred": True},
            {"emoji": "3️⃣", "label": "BREAKDOWN",     "prob": "20%",
             "trigger": f"Loss of {fmt_price(nearest_s)} support",
             "entry": "", "tp": "", "sl": "", "preferred": False},
        ]
    elif direction == "BEARISH":
        analysis = (
            f"Structure is bearish with price failing at resistance near {fmt_price(nearest_r)}.{htf_clause} "
            f"The {trend_context.lower()} regime puts sellers in control. "
            f"Best case: bounce off {fmt_price(nearest_s)} for a counter-trend trade. "
            f"Base case: continuation lower toward {fmt_price(nearest_s)}. "
            f"Worst case: capitulation through {fmt_price(nearest_s)} opens deeper downside."
        )
        scenarios = [
            {"emoji": "1️⃣", "label": "BREAKDOWN",      "prob": "50%",
             "trigger": f"Break below {fmt_price(nearest_s)} with volume",
             "entry": fmt_price_plain(entry_zone[0]), "tp": fmt_price_plain(stop_loss),
             "sl": fmt_price_plain(entry_zone[1]), "preferred": True},
            {"emoji": "2️⃣", "label": "PULLBACK SHORT", "prob": "30%",
             "trigger": f"Bounce to {fmt_price(entry_zone[0])}-{fmt_price(nearest_r)}",
             "entry": fmt_price_plain(entry_zone[1]),
             "tp": f"{fmt_price_plain(tp1)}/{fmt_price_plain(tp2)}",
             "sl": fmt_price_plain(nearest_r), "preferred": False},
            {"emoji": "3️⃣", "label": "REVERSAL",       "prob": "20%",
             "trigger": f"Reclaim of {fmt_price(nearest_r)} flips structure",
             "entry": "", "tp": "", "sl": "", "preferred": False},
        ]
    else:
        analysis = (
            f"{symbol} is in a neutral {trend_context.lower()} range between "
            f"{fmt_price(nearest_s)} and {fmt_price(nearest_r)}.{htf_clause} "
            f"No clear directional edge — patience is the best strategy here. "
            f"Best case: range resolves with a clean breakout. Base case: continued chop. "
            f"Worst case: false breakout traps traders on both sides."
        )
        scenarios = [
            {"emoji": "1️⃣", "label": "BREAKOUT",   "prob": "35%",
             "trigger": f"Sustained close above {fmt_price(nearest_r)}",
             "entry": fmt_price_plain(nearest_r), "tp": fmt_price_plain(tp1),
             "sl": fmt_price_plain(nearest_s), "preferred": False},
            {"emoji": "2️⃣", "label": "RANGE PLAY", "prob": "40%",
             "trigger": f"Fade edges: buy {fmt_price(nearest_s)}, sell {fmt_price(nearest_r)}",
             "entry": "", "tp": "", "sl": "", "preferred": True},
            {"emoji": "3️⃣", "label": "BREAKDOWN",  "prob": "25%",
             "trigger": f"Loss of {fmt_price(nearest_s)} support",
             "entry": "", "tp": "", "sl": "", "preferred": False},
        ]

    return {"analysis": analysis, "scenarios": scenarios}


# ============================================================================
# GRADING HELPERS
# ============================================================================

def score_to_grade(score: int) -> str:
    if score >= 80: return "A+"
    if score >= 75: return "A"
    if score >= 70: return "A-"
    if score >= 65: return "B+"
    if score >= 60: return "B"
    if score >= 55: return "B-"
    if score >= 50: return "C+"
    if score >= 45: return "C"
    if score >= 40: return "C-"
    return "D"


def confidence_to_timing_grade(confidence: int) -> str:
    if confidence >= 80: return "A"
    if confidence >= 70: return "B"
    if confidence >= 60: return "C"
    if confidence >= 50: return "D"
    return "F"


def act_now(score: int, confidence: int) -> str:
    return "✅ Yes" if (score >= 65 and confidence >= 65) else "❌ Wait"


# ============================================================================
# HISTORICAL PERFORMANCE BLOCK
# ============================================================================

async def _build_performance_block(symbol: str, timeframe: str, score: int) -> str:
    perf = await performance_tracker.get_similar_setups(symbol, timeframe, score)
    if not perf:
        return ""

    total = perf["total_setups"]
    if total < 10:
        return ""

    win_rate   = perf["win_rate"]
    wins       = perf["wins"]
    losses     = perf["losses"]
    avg_win    = perf["avg_win"]
    avg_loss   = perf["avg_loss"]
    expectancy = perf["expectancy"]
    avg_rr     = perf["avg_risk_reward"]
    w4h        = perf.get("win_rate_4h")
    w24h       = perf.get("win_rate_24h")
    w72h       = perf.get("win_rate_72h")

    grade_emoji = "🟢" if win_rate >= 60 else "🟡" if win_rate >= 45 else "🔴"
    exp_str     = f"+{expectancy:.1f}%" if expectancy >= 0 else f"{expectancy:.1f}%"

    block  = line()
    block += "📈 <b>HISTORICAL PERFORMANCE</b>\n"
    block += line()
    block += f"{grade_emoji} Win Rate: <b>{win_rate:.0f}%</b> ({wins}W / {losses}L from {total} setups)\n"
    block += f"📊 Avg Win: <b>+{avg_win:.1f}%</b>  |  Avg Loss: <b>{avg_loss:.1f}%</b>\n"
    block += f"⚖️ Expectancy: <b>{h(exp_str)}</b> per trade  |  Avg R:R <b>1:{avg_rr:.1f}</b>\n"

    if any(x is not None for x in (w4h, w24h, w72h)):
        parts = []
        if w4h  is not None: parts.append(f"4h {w4h:.0f}%")
        if w24h is not None: parts.append(f"24h {w24h:.0f}%")
        if w72h is not None: parts.append(f"72h {w72h:.0f}%")
        block += f"⏱️ Outcome windows: {' | '.join(parts)}\n"

    block += "\n"
    return block


# ============================================================================
# MESSAGE FORMATTER  (HTML)
# ============================================================================

async def format_setup_message(setup_data: dict, symbol: str, timeframe: str) -> str:
    score         = setup_data.get("score", 50)
    confidence    = setup_data.get("confidence", 50)
    direction     = setup_data.get("direction", "NEUTRAL")
    current_price = setup_data.get("current_price", 0)
    trend_context = setup_data.get("trend_context", "RANGING")
    htf_trend     = setup_data.get("htf_trend", "")
    htf_tf        = setup_data.get("htf_timeframe", "")

    quality_grade = score_to_grade(score)
    timing_grade  = confidence_to_timing_grade(confidence)
    act_signal    = act_now(score, confidence)

    narrative = await get_ai_narrative(setup_data, symbol, timeframe)
    # h() escapes all dynamic text — safe against any characters the AI returns
    analysis  = h(narrative.get("analysis", ""))
    scenarios = narrative.get("scenarios", [])

    htf_line = f"HTF ({h(htf_tf)}): {h(htf_trend)}  |  " if htf_tf and htf_trend else ""

    # ── Header ────────────────────────────────────────────────────────
    msg  = f"🎯 <b>Professional Setup — {h(symbol)}/USDT ({h(timeframe)})</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"{h(fmt_price(current_price))} | {htf_line}Regime: {h(trend_context)}\n\n"
    msg += f"🏆 Setup Quality: <b>{h(quality_grade)}</b>  |  Entry Timing: <b>{h(timing_grade)}</b>\n"
    msg += f"⚡ Act Now: {h(act_signal)}   |  Timeframe Fit: {h(timeframe)} ✓\n\n"

    # ── Analysis ──────────────────────────────────────────────────────
    msg += line()
    msg += "🧠 <b>ANALYSIS</b>\n"
    msg += line()
    msg += f"{analysis}\n\n"

    # ── Scenarios ─────────────────────────────────────────────────────
    msg += line()
    msg += "🎯 <b>THREE SCENARIOS</b>\n"
    msg += line()

    for s in scenarios[:3]:
        preferred_tag = "  ✅ <b>Preferred</b>" if s.get("preferred") else ""
        msg += f"{s['emoji']} <b>{h(s['label'])}</b> ({h(s['prob'])} probability){preferred_tag}\n"
        msg += f"   Trigger: {h(s['trigger'])}\n"
        detail_parts = []
        if s.get("entry"): detail_parts.append(f"Entry: ${h(s['entry'])}")
        if s.get("tp"):    detail_parts.append(f"TP: ${h(s['tp'])}")
        if s.get("sl"):    detail_parts.append(f"SL: ${h(s['sl'])}")
        if detail_parts:
            msg += f"   {' | '.join(detail_parts)}\n"
        msg += "\n"

    # ── Key Levels ────────────────────────────────────────────────────
    support_levels    = setup_data.get("support_levels", [])
    resistance_levels = setup_data.get("resistance_levels", [])
    if support_levels or resistance_levels:
        msg += line()
        msg += "📍 <b>KEY LEVELS</b>\n"
        msg += line()
        if resistance_levels:
            r    = resistance_levels[0]
            dist = ((r["price"] - current_price) / current_price) * 100
            msg += f"↑ Resistance: {h(fmt_price(r['price']))} (+{dist:.1f}%, {r['touches']} touches)\n"
        if support_levels:
            s    = support_levels[0]
            dist = ((current_price - s["price"]) / current_price) * 100
            msg += f"↓ Support:    {h(fmt_price(s['price']))} (-{dist:.1f}%, {s['touches']} touches)\n"
        msg += "\n"

    # ── Signals summary ───────────────────────────────────────────────
    bullish_signals = setup_data.get("bullish_signals", [])
    bearish_signals = setup_data.get("bearish_signals", [])
    if bullish_signals or bearish_signals:
        msg += f"📊 Signals: ✅ {len(bullish_signals)} bullish  ❌ {len(bearish_signals)} bearish\n\n"

    # ── Risk factors ──────────────────────────────────────────────────
    risk_factors = setup_data.get("risk_factors", [])
    if risk_factors:
        risks_str = " • ".join(h(r) for r in risk_factors[:3])
        msg += f"⚠️ <b>Risks:</b> {risks_str}\n\n"

    # ── Historical performance ────────────────────────────────────────
    perf_block = await _build_performance_block(symbol, timeframe, score)
    if perf_block:
        msg += perf_block

    # ── Position sizing hint ──────────────────────────────────────────
    if score >= 55 and confidence >= 60:
        stop_loss = setup_data.get("stop_loss", current_price * 0.97)
        msg += f"📏 <code>/risk </code>\n\n"

    # ── Disclaimer ────────────────────────────────────────────────────
    msg += "━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "⚠️ Not financial advice. DYOR. Use stop losses."

    return msg


# ============================================================================
# SETUP COMMAND
# ============================================================================

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/setup")
    await handle_streak(update, context)

    plan = get_user_plan(user_id)
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 <b>Pro Feature: Trade Setup Analyzer</b>\n\n"
            "✅ Setup quality grading (A+ to D)\n"
            "✅ Multi-timeframe confirmation\n"
            "✅ Real exchange data (Bybit/OKX)\n"
            "✅ AI-written scenario analysis\n"
            "✅ Historical win rate tracking\n"
            "✅ ATR-based entry/exit zones\n\n"
            "💎 Upgrade to Pro: /upgrade",
            parse_mode=ParseMode.HTML,
        )
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ <b>Usage:</b> <code>/setup [SYMBOL] [TIMEFRAME]</code>\n\n"
            "<b>Examples:</b>\n"
            "<code>/setup BTC 4h</code> — Bitcoin 4-hour analysis\n"
            "<code>/setup ETH 1h</code> — Ethereum 1-hour analysis\n"
            "<code>/setup SOL 15m</code> — Solana 15-minute analysis\n\n"
            "<b>Valid timeframes:</b> <code>5m 15m 30m 1h 2h 4h 8h 1d</code>\n\n"
            f"<b>Supported:</b> Top 100 coins <i>(currently {len(SUPPORTED_COINS)} available)</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    symbol    = context.args[0].upper().strip()
    timeframe = context.args[1].lower().strip() if len(context.args) >= 2 else "4h"

    if symbol not in SUPPORTED_COINS:
        await update.message.reply_text(
            f"❌ <b>{h(symbol)} not supported</b>\n\n"
            f"<b>Popular coins:</b> BTC, ETH, SOL, BNB, ADA, AVAX, MATIC, ARB, DOGE\n\n"
            f"<i>Currently supporting {len(SUPPORTED_COINS)} coins</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    if timeframe not in VALID_TIMEFRAMES:
        await update.message.reply_text(
            f"❌ Invalid timeframe: <code>{h(timeframe)}</code>\n\n"
            f"<b>Valid options:</b> <code>5m 15m 30m 1h 2h 4h 8h 1d</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    loading_msg = await update.message.reply_text(
        f"🔄 <b>Analyzing {h(symbol)} on {h(timeframe)}</b>\n\n"
        f"• Fetching real OHLCV from Bybit/OKX\n"
        f"• Checking {h(_htf_label(timeframe))} confirmation\n"
        f"• Calculating indicators &amp; S/R levels\n"
        f"• Generating AI scenario analysis\n\n"
        f"⏱️ This takes 5–15 seconds…",
        parse_mode=ParseMode.HTML,
    )

    try:
        setup_data = await setup_analyzer.analyze_setup(symbol, timeframe)

        if not setup_data:
            await loading_msg.edit_text(
                f"❌ <b>Analysis Failed for {h(symbol)}</b>\n\n"
                f"• Insufficient data on {h(timeframe)}\n"
                f"• Exchange API temporary error\n\n"
                f"<b>Try:</b> <code>/setup {h(symbol)} 4h</code> or wait a moment",
                parse_mode=ParseMode.HTML,
            )
            return

        try:
            await performance_tracker.track_setup(user_id, symbol, timeframe, setup_data)
        except Exception as pt_err:
            logger.warning(f"performance_tracker.track_setup failed: {pt_err}")

        message  = await format_setup_message(setup_data, symbol, timeframe)
        setup_id = f"{symbol}_{timeframe}"
        context.user_data[f"setup_{setup_id}"] = setup_data

        keyboard = [
            [InlineKeyboardButton("🔔 Set Entry Alert", callback_data=f"setup_alert_{setup_id}")],
            [
                InlineKeyboardButton("📊 View Charts", callback_data=f"setup_charts_{setup_id}"),
                InlineKeyboardButton("🔄 Refresh",     callback_data=f"setup_refresh_{setup_id}"),
            ],
        ]

        await loading_msg.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info(
            f"Setup completed: {symbol}/{timeframe} "
            f"score={setup_data['score']} dir={setup_data['direction']}"
        )

    except Exception:
        logger.exception(f"Error in /setup for {symbol}/{timeframe}")
        await loading_msg.edit_text(
            f"❌ <b>Setup Analysis Error</b>\n\n"
            f"Unexpected error for {h(symbol)}. Please retry in 30–60 seconds.\n"
            f"Persistent issues? Contact /support",
            parse_mode=ParseMode.HTML,
        )


def _htf_label(timeframe: str) -> str:
    from services.setup_analyzer import HTF_MAP
    htf = HTF_MAP.get(timeframe, "1d")
    return htf if htf != timeframe else "self"


# ============================================================================
# CALLBACK HANDLERS
# ============================================================================

async def setup_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        setup_id   = query.data.replace("setup_alert_", "")
        setup_data = context.user_data.get(f"setup_{setup_id}")
        if not setup_data:
            await query.answer("❌ Setup expired. Run /setup again.", show_alert=True)
            return

        symbol        = setup_id.split("_")[0]
        direction     = setup_data.get("direction", "NEUTRAL")
        entry_zone    = setup_data["entry_zone"]
        current_price = setup_data["current_price"]

        if direction == "BULLISH":
            recommended_price = entry_zone[0]; direction_word = "above"
        elif direction == "BEARISH":
            recommended_price = entry_zone[1]; direction_word = "below"
        else:
            recommended_price = current_price; direction_word = "above"

        rec_str = fmt_price_plain(recommended_price)
        lo_str  = fmt_price_plain(entry_zone[0])
        hi_str  = fmt_price_plain(entry_zone[1])
        message = (
            f"🔔 Alert for {symbol}\n\n"
            f"Use: /set {symbol} {direction_word} {rec_str}\n\n"
            f"Current: {fmt_price(current_price)}\n"
            f"Entry: ${lo_str}-${hi_str}"
        )
        if len(message) > 190:
            message = f"🔔 {symbol}\n/set {symbol} {direction_word} {rec_str}\nEntry: ${lo_str}-${hi_str}"

        await query.answer(message, show_alert=True)

    except Exception:
        logger.exception("Setup alert callback error")
        await query.answer(
            "❌ Alert failed\n\nUse: /set [SYMBOL] above [PRICE]",
            show_alert=True,
        )


async def setup_charts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        setup_id  = query.data.replace("setup_charts_", "")
        parts     = setup_id.split("_")
        symbol    = parts[0]
        timeframe = parts[1] if len(parts) > 1 else "4h"
        await query.answer(
            f"📊 {symbol} Chart\n\nUse: /c {symbol} {timeframe}\n\nShows TradingView chart with key levels",
            show_alert=True,
        )
    except Exception:
        logger.exception("Setup charts callback error")
        await query.answer("❌ Chart view failed", show_alert=True)


async def setup_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer("🔄 Refreshing...", show_alert=False)
        setup_id  = query.data.replace("setup_refresh_", "")
        parts     = setup_id.split("_")
        symbol    = parts[0]
        timeframe = parts[1] if len(parts) > 1 else "4h"

        await query.edit_message_text(
            f"🔄 Refreshing {h(symbol)} {h(timeframe)}…\n\n⏱️ Please wait 5–15 seconds…",
            parse_mode=ParseMode.HTML,
        )

        setup_data = await setup_analyzer.analyze_setup(symbol, timeframe)
        if not setup_data:
            await query.edit_message_text(
                f"❌ Refresh failed for {h(symbol)}.\n\n"
                f"Try: <code>/setup {h(symbol)} {h(timeframe)}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        user_id = query.from_user.id
        try:
            await performance_tracker.track_setup(user_id, symbol, timeframe, setup_data)
        except Exception as pt_err:
            logger.warning(f"performance_tracker.track_setup (refresh) failed: {pt_err}")

        message = await format_setup_message(setup_data, symbol, timeframe)
        context.user_data[f"setup_{setup_id}"] = setup_data

        keyboard = [
            [InlineKeyboardButton("🔔 Set Entry Alert", callback_data=f"setup_alert_{setup_id}")],
            [
                InlineKeyboardButton("📊 View Charts", callback_data=f"setup_charts_{setup_id}"),
                InlineKeyboardButton("🔄 Refresh",     callback_data=f"setup_refresh_{setup_id}"),
            ],
        ]
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info(f"Setup refreshed: {symbol}/{timeframe}")

    except Exception:
        logger.exception("Setup refresh callback error")
        await query.edit_message_text(
            "❌ Refresh failed. Try <code>/setup [SYMBOL] [TIMEFRAME]</code>",
            parse_mode=ParseMode.HTML,
        )


# ============================================================================
# REGISTER HANDLERS
# ============================================================================

def register_setup_handlers(app):
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CallbackQueryHandler(setup_alert_callback,   pattern="^setup_alert_"))
    app.add_handler(CallbackQueryHandler(setup_charts_callback,  pattern="^setup_charts_"))
    app.add_handler(CallbackQueryHandler(setup_refresh_callback, pattern="^setup_refresh_"))
    logger.info("Setup handlers registered")
