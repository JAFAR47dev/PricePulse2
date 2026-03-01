"""
handlers/aiscan.py

AI-powered chart pattern scanner — Pro only.
Integrates with the professional patterns.py library which returns
structured Pattern dicts:
    {name, emoji, direction, quality, description, index}

Output format:
  1. Pattern summary card (grouped by direction + quality)
  2. AI narrative (OpenRouter) grounded in the detected patterns
"""

import os
import datetime
import logging
import httpx

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils.ohlcv import fetch_candles
from utils.patterns import detect_all_patterns          # returns List[Pattern]
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak

logger = logging.getLogger(__name__)

# ── Valid timeframes ──────────────────────────────────────────────────────────
VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]

# ── Smart price formatter (no import cycle) ───────────────────────────────────
def _fmt(price: float) -> str:
    if price >= 1000:  return f"${price:,.2f}"
    if price >= 1:     return f"${price:,.3f}"
    if price >= 0.01:  return f"${price:.4f}"
    return f"${price:.6f}"


# ============================================================================
# TIMEFRAME CONFIGURATION
# ============================================================================

_TF_CONFIG = {
    "1m":  {"max_patterns": 4,  "lookback": 60,  "horizon": "minutes",       "style": "SCALP"},
    "5m":  {"max_patterns": 5,  "lookback": 100, "horizon": "1-4 hours",     "style": "SCALP"},
    "15m": {"max_patterns": 6,  "lookback": 100, "horizon": "hours",         "style": "INTRADAY"},
    "30m": {"max_patterns": 7,  "lookback": 150, "horizon": "hours/day",     "style": "INTRADAY"},
    "1h":  {"max_patterns": 8,  "lookback": 200, "horizon": "1-3 days",      "style": "SWING"},
    "2h":  {"max_patterns": 8,  "lookback": 200, "horizon": "2-5 days",      "style": "SWING"},
    "4h":  {"max_patterns": 10, "lookback": 250, "horizon": "1-2 weeks",     "style": "SWING"},
    "8h":  {"max_patterns": 10, "lookback": 250, "horizon": "2-4 weeks",     "style": "POSITION"},
    "1d":  {"max_patterns": 12, "lookback": 300, "horizon": "weeks/months",  "style": "POSITION"},
}

_STYLE_LABELS = {
    "SCALP":    "⚡ Scalping",
    "INTRADAY": "📊 Intraday",
    "SWING":    "🔄 Swing",
    "POSITION": "📈 Position",
}

_MIN_CANDLES = {
    "1m": 30, "5m": 40, "15m": 40, "30m": 50,
    "1h": 60, "2h": 60, "4h": 80, "8h": 80, "1d": 80,
}


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

_QUALITY_EMOJI = {"HIGH": "🔥", "MEDIUM": "⚡", "LOW": "💡"}
_DIR_EMOJI     = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "↔️"}
_DIR_LABEL     = {"BULLISH": "Bullish", "BEARISH": "Bearish", "NEUTRAL": "Neutral"}


def _format_pattern_card(patterns: list, symbol: str, tf: str, price: float, change_pct: float) -> str:
    """
    Build the pattern summary card from structured Pattern dicts.

    Layout:
      Header (symbol, price, change)
      ─────────────────────
      [Bullish patterns]
      [Bearish patterns]
      [Neutral patterns]
      ─────────────────────
      Footer (counts + bias)
    """
    cfg         = _TF_CONFIG.get(tf, _TF_CONFIG["1h"])
    style_label = _STYLE_LABELS.get(cfg["style"], "")
    change_sign = "+" if change_pct >= 0 else ""
    change_arrow = "▲" if change_pct >= 0 else "▼"

    # ── Header ────────────────────────────────────────────────────────────
    lines = [
        f"🔍 *Pattern Scan — {symbol}/USDT* ({tf})",
        f"━━━━━━━━━━━━━━━━━━━━━━━",
        f"{_fmt(price)}  {change_arrow} {change_sign}{change_pct:.2f}%  |  {style_label}",
        "",
    ]

    # ── Group patterns by direction ───────────────────────────────────────
    bullish = [p for p in patterns if p["direction"] == "BULLISH"]
    bearish = [p for p in patterns if p["direction"] == "BEARISH"]
    neutral = [p for p in patterns if p["direction"] == "NEUTRAL"]

    def _section(label: str, emoji: str, group: list) -> list:
        if not group:
            return []
        out = [f"{emoji} *{label} Signals ({len(group)})*"]
        for p in group:
            q_tag = _QUALITY_EMOJI.get(p["quality"], "•")
            out.append(f"   {q_tag} {p['emoji']} *{p['name']}*")
            out.append(f"      _{p['description']}_")
        out.append("")
        return out

    lines += _section("Bullish", "📈", bullish)
    lines += _section("Bearish", "📉", bearish)
    lines += _section("Neutral", "↔️",  neutral)

    # ── Bias summary ──────────────────────────────────────────────────────
    total   = len(patterns)
    high_q  = sum(1 for p in patterns if p["quality"] == "HIGH")

    if len(bullish) > len(bearish) * 1.5:
        bias = "🟢 Bullish edge"
    elif len(bearish) > len(bullish) * 1.5:
        bias = "🔴 Bearish edge"
    elif len(bullish) == len(bearish):
        bias = "⚪ Conflicting signals"
    else:
        bias = "🟡 Slight " + ("bullish" if len(bullish) > len(bearish) else "bearish") + " lean"

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 *{total} patterns detected* · {high_q} high-quality",
        f"⚖️ Bias: {bias}",
        f"⏱ Horizon: {cfg['horizon']}",
    ]

    return "\n".join(lines)


def _format_ai_message(ai_text: str, tf: str) -> str:
    """Wrap the AI narrative in a clean message frame."""
    cfg   = _TF_CONFIG.get(tf, _TF_CONFIG["1h"])
    style = _STYLE_LABELS.get(cfg["style"], tf)
    return (
        f"🤖 *AI Analysis* — {style} ({tf})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ai_text}"
    )


# ============================================================================
# AI NARRATIVE (async httpx — no blocking requests.post)
# ============================================================================

async def _get_ai_narrative(
    symbol: str,
    tf: str,
    patterns: list,
    price: float,
    change_pct: float,
) -> str | None:
    """
    Call OpenRouter (async) with a structured prompt grounded in
    the Pattern dicts. Returns the AI text or None on failure.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set")
        return None

    cfg   = _TF_CONFIG.get(tf, _TF_CONFIG["1h"])
    style = cfg["style"]

    # ── Build structured pattern summary for the prompt ───────────────────
    high_patterns = [p for p in patterns if p["quality"] == "HIGH"]
    med_patterns  = [p for p in patterns if p["quality"] == "MEDIUM"]
    low_patterns  = [p for p in patterns if p["quality"] == "LOW"]

    bullish_names = [p["name"] for p in patterns if p["direction"] == "BULLISH"]
    bearish_names = [p["name"] for p in patterns if p["direction"] == "BEARISH"]

    def _list_patterns(group: list) -> str:
        return "\n".join(f"  • {p['name']} ({p['direction']}): {p['description']}" for p in group)

    pattern_block = ""
    if high_patterns:
        pattern_block += f"HIGH QUALITY:\n{_list_patterns(high_patterns)}\n\n"
    if med_patterns:
        pattern_block += f"MEDIUM QUALITY:\n{_list_patterns(med_patterns)}\n\n"
    if low_patterns:
        pattern_block += f"LOW QUALITY (context only):\n{_list_patterns(low_patterns)}\n\n"

    # ── Style-specific instructions ───────────────────────────────────────
    style_instructions = {
        "SCALP": (
            "This is a SCALPING timeframe. Focus on:\n"
            "- Momentum in the next 15–60 minutes only\n"
            "- Quick entry/exit signals from the high-quality patterns\n"
            "- Emphasise reversal risk — scalp moves end fast\n"
            "- Ignore low-quality patterns for trade decisions"
        ),
        "INTRADAY": (
            "This is an INTRADAY timeframe. Focus on:\n"
            "- Today's trend direction\n"
            "- Key levels implied by the patterns\n"
            "- Whether to wait for confirmation or act on breakout\n"
            "- Realistic targets within the trading session"
        ),
        "SWING": (
            "This is a SWING timeframe. Focus on:\n"
            "- 1–5 day trade setup quality\n"
            "- Which patterns confirm or conflict with each other\n"
            "- Whether bulls or bears have structural advantage\n"
            "- Patience guidance — swing setups need confirmation"
        ),
        "POSITION": (
            "This is a POSITION timeframe. Focus on:\n"
            "- Weekly/monthly trend structure\n"
            "- Major reversal vs continuation signals\n"
            "- Which high-quality patterns carry the most weight\n"
            "- Strategic positioning advice, not tactical entries"
        ),
    }

    # ── Token budget by style ─────────────────────────────────────────────
    max_tokens = {"SCALP": 280, "INTRADAY": 320, "SWING": 380, "POSITION": 420}.get(style, 350)

    prompt = f"""You are a professional crypto technical analyst providing a structured pattern analysis.

MARKET DATA:
  Symbol:        {symbol}/USDT
  Timeframe:     {tf}
  Current Price: {_fmt(price)}
  Recent Change: {change_pct:+.2f}% (last {cfg['lookback']//10} periods)
  Bull patterns: {', '.join(bullish_names) if bullish_names else 'None'}
  Bear patterns: {', '.join(bearish_names) if bearish_names else 'None'}

DETECTED PATTERNS (use ONLY these — do not invent patterns):
{pattern_block.strip()}

ANALYSIS STYLE FOR {tf.upper()} ({style}):
{style_instructions.get(style, style_instructions['SWING'])}

STRICT OUTPUT RULES:
1. Analyse ONLY the patterns listed above. Do not mention any pattern not in the list.
2. No specific price targets.
3. No guarantees or certainty language ("will", "definitely", "guaranteed").
4. Respect the timeframe — {tf} analysis talks about {cfg['horizon']}, not years.
5. Weight HIGH QUALITY patterns 3× more than LOW QUALITY patterns.
6. If bullish and bearish HIGH patterns conflict, say so explicitly.
7. Be direct and concise. No filler sentences.

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
**Edge:** [Bulls / Bears / Contested] — one sentence why.

**Key Pattern:** [Name the single most significant pattern and what it means for {tf} traders.]

**Confluence:** [Are patterns confirming each other or conflicting? 1-2 sentences.]

**Trader Guidance:** [What should a {style.lower()} trader do — act, wait, or avoid? 2-3 sentences.]

⚠️ Pattern analysis only. Not financial advice."""

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/your_bot",
                },
                json={
                    "model": "mistralai/mixtral-8x7b-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.25,
                    "max_tokens": max_tokens,
                    "top_p": 0.9,
                },
            )

        if resp.status_code != 200:
            logger.error(f"OpenRouter {resp.status_code}: {resp.text[:200]}")
            return None

        ai_text = resp.json()["choices"][0]["message"]["content"].strip()

        # ── Hallucination guard ───────────────────────────────────────────
        forbidden = [
            "will reach", "price target", "guaranteed", "definitely will",
            "100% certain", "investment advice", "will go to",
        ]
        if any(phrase in ai_text.lower() for phrase in forbidden):
            logger.warning("AI response contained forbidden phrase — discarding")
            return None

        return ai_text

    except httpx.TimeoutException:
        logger.warning("OpenRouter timeout for /aiscan")
        return None
    except Exception as e:
        logger.exception(f"OpenRouter error: {e}")
        return None


# ============================================================================
# MAIN COMMAND HANDLER
# ============================================================================

async def aiscan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /aiscan [SYMBOL] [TIMEFRAME]

    Pro-only command. Runs the full 19-detector pattern library against
    recent candle data, displays structured results grouped by direction
    and quality, then sends an AI narrative grounded in the patterns.
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/aiscan")
    await handle_streak(update, context)

    # ── Pro gate ──────────────────────────────────────────────────────────
    plan = get_user_plan(user_id)
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 *Pro Feature: AI Pattern Scanner*\n\n"
            "Unlock professional chart pattern detection:\n\n"
            "✅ 19 pattern detectors across 5 categories\n"
            "✅ Continuation, reversal & candlestick patterns\n"
            "✅ RSI + MACD divergence (regular & hidden)\n"
            "✅ Quality scoring (High / Medium / Low)\n"
            "✅ AI narrative grounded in detected patterns\n\n"
            "💎 Upgrade: /upgrade",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Args ──────────────────────────────────────────────────────────────
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "❌ *Usage:* `/aiscan [SYMBOL] [TIMEFRAME]`\n\n"
            "*Examples:*\n"
            "`/aiscan BTC 4h`\n"
            "`/aiscan ETH 1h`\n"
            "`/aiscan SOL 15m`\n\n"
            f"*Timeframes:* `{'  '.join(VALID_TIMEFRAMES)}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    symbol = args[0].upper().strip()
    tf     = args[1].lower().strip() if len(args) > 1 else "1h"

    if tf not in VALID_TIMEFRAMES:
        await update.message.reply_text(
            f"❌ Invalid timeframe: `{tf}`\n\n"
            f"Valid options: `{'  '.join(VALID_TIMEFRAMES)}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    cfg          = _TF_CONFIG[tf]
    min_candles  = _MIN_CANDLES[tf]
    max_patterns = cfg["max_patterns"]

    # ── Loading message ───────────────────────────────────────────────────
    loading = await update.message.reply_text(
        f"🔍 *Scanning {symbol} on {tf}…*\n\n"
        f"• Running 19 pattern detectors\n"
        f"• Applying quality filters\n"
        f"• Generating AI analysis\n\n"
        f"⏱ ~10–15 seconds…",
        parse_mode=ParseMode.MARKDOWN,
    )

    # ── Typing indicator ──────────────────────────────────────────────────
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # ── Fetch candles ─────────────────────────────────────────────────────
    try:
        candles = await fetch_candles(symbol, tf, limit=cfg["lookback"])
    except Exception as e:
        logger.exception(f"fetch_candles failed for {symbol}/{tf}")
        await loading.edit_text("⚠️ Failed to fetch chart data. Please try again.")
        return

    if not candles or len(candles) < min_candles:
        await loading.edit_text(
            f"⚠️ Insufficient data for *{symbol}* on `{tf}`.\n\n"
            f"Got {len(candles) if candles else 0} candles (need {min_candles}).\n"
            f"Try a longer timeframe like `1h` or `4h`.",
        )
        return

    # ── Current price & change ────────────────────────────────────────────
    price = float(candles[-1]["close"])
    lookback_n = min(cfg["lookback"] // 10, len(candles) - 1)
    ref_price  = float(candles[-lookback_n]["close"]) if lookback_n > 0 else price
    change_pct = (price - ref_price) / (ref_price + 1e-9) * 100

    # ── Detect patterns ───────────────────────────────────────────────────
    try:
        patterns = detect_all_patterns(candles, max_results=max_patterns, min_quality="LOW")
    except Exception as e:
        logger.exception(f"Pattern detection failed for {symbol}/{tf}")
        patterns = []

    # ── Log ───────────────────────────────────────────────────────────────
    logger.info(
        f"/aiscan {symbol}/{tf} — {len(candles)} candles, "
        f"{len(patterns)} patterns, price={_fmt(price)}"
    )

    # ── No patterns found ─────────────────────────────────────────────────
    if not patterns:
        await loading.edit_text(
            f"✅ *{symbol} / {tf} — Clean Chart*\n\n"
            f"No significant patterns detected in the last "
            f"{len(candles)} candles.\n\n"
            f"💡 This often means price is in a tight consolidation with no "
            f"breakout signal yet. Try:\n"
            f"• A different timeframe\n"
            f"• Checking back after the next few candles close",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Pattern card ──────────────────────────────────────────────────────
    card = _format_pattern_card(patterns, symbol, tf, price, change_pct)
    await loading.edit_text(card, parse_mode=ParseMode.MARKDOWN)

    # ── AI narrative ──────────────────────────────────────────────────────
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    ai_text = await _get_ai_narrative(symbol, tf, patterns, price, change_pct)

    if ai_text:
        await update.message.reply_text(
            _format_ai_message(ai_text, tf),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    else:
        # Fallback: rule-based summary built from pattern dicts
        fallback = _rule_based_summary(patterns, symbol, tf)
        await update.message.reply_text(
            _format_ai_message(fallback, tf),
            parse_mode=ParseMode.MARKDOWN,
        )


# ============================================================================
# RULE-BASED FALLBACK SUMMARY (when AI is unavailable)
# ============================================================================

def _rule_based_summary(patterns: list, symbol: str, tf: str) -> str:
    """
    Build a coherent summary from the Pattern dicts without AI.
    Used when OpenRouter is unavailable or times out.
    """
    cfg = _TF_CONFIG.get(tf, _TF_CONFIG["1h"])

    bullish = [p for p in patterns if p["direction"] == "BULLISH"]
    bearish = [p for p in patterns if p["direction"] == "BEARISH"]
    high_q  = [p for p in patterns if p["quality"] == "HIGH"]

    # Edge
    if len(bullish) > len(bearish):
        edge = f"**Edge:** Bulls — {len(bullish)} bullish vs {len(bearish)} bearish signals."
    elif len(bearish) > len(bullish):
        edge = f"**Edge:** Bears — {len(bearish)} bearish vs {len(bullish)} bullish signals."
    else:
        edge = "**Edge:** Contested — equal bullish and bearish signals present."

    # Key pattern
    key = high_q[0] if high_q else patterns[0]
    key_line = (
        f"**Key Pattern:** {key['emoji']} {key['name']} — {key['description']}"
    )

    # Confluence
    if len(high_q) >= 2:
        confluence = (
            f"**Confluence:** {len(high_q)} high-quality patterns detected, "
            f"increasing signal reliability."
        )
    elif len(bullish) > 0 and len(bearish) > 0:
        confluence = (
            "**Confluence:** Mixed signals — bullish and bearish patterns "
            "are conflicting. Wait for resolution."
        )
    else:
        confluence = (
            f"**Confluence:** {len(patterns)} pattern(s) pointing in the same direction — "
            f"moderate confidence."
        )

    # Guidance
    style = cfg["style"]
    if style == "SCALP":
        guidance = (
            "**Trader Guidance:** Scalp in the direction of the dominant signal "
            "with tight stops. High-quality patterns only."
        )
    elif style == "INTRADAY":
        guidance = (
            "**Trader Guidance:** Wait for the current candle to close before "
            "acting. Confirm with volume if available."
        )
    elif style == "SWING":
        guidance = (
            "**Trader Guidance:** Look for entry on the next pullback toward "
            "support. Allow 1–3 days for the setup to develop."
        )
    else:
        guidance = (
            "**Trader Guidance:** Position sizing matters most at this timeframe. "
            "Allow days/weeks for the pattern to play out."
        )

    return "\n\n".join([edge, key_line, confluence, guidance,
                        "⚠️ Pattern analysis only. Not financial advice."])
