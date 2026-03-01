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

setup_analyzer = SetupAnalyzer()
performance_tracker = PerformanceTracker()

VALID_TIMEFRAMES = ["5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]

# ============================================================================
# LOAD TOP 100 COINGECKO COINS
# ============================================================================

def load_supported_coins():
    """Load top 100 CoinGecko coins from JSON file with fallback"""
    try:
        json_path = os.path.join("services", "top100_coingecko_ids.json")
        with open(json_path, "r") as f:
            data = json.load(f)
            symbols = set(symbol.upper() for symbol in data.keys())
            logger.info(f"Loaded {len(symbols)} supported coins")
            return symbols
    except FileNotFoundError:
        logger.error(f"top100_coingecko_ids.json not found at {json_path}")
        return get_fallback_coins()
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in top100_coingecko_ids.json: {e}")
        return get_fallback_coins()
    except Exception as e:
        logger.error(f"Error loading supported coins: {e}")
        return get_fallback_coins()

def get_fallback_coins():
    """Fallback coin list if JSON loading fails"""
    return {
        "BTC", "ETH", "USDT", "BNB", "XRP", "USDC", "SOL", "TRX", "DOGE",
        "ADA", "AVAX", "SHIB", "DOT", "MATIC", "LTC", "LINK", "UNI", "ATOM",
        "TON", "ICP", "FIL", "ARB", "OP", "AAVE", "MKR", "PEPE", "WIF"
    }

SUPPORTED_COINS = load_supported_coins()


# ============================================================================
# SMART PRICE FORMATTING
# ============================================================================

def fmt_price(price: float) -> str:
    """
    Format price intelligently based on magnitude.
    - >= 1000:     2 decimals, comma-separated  e.g. $1,927.52
    - >= 1:        3 decimals                   e.g. $1.234
    - >= 0.01:     4 decimals                   e.g. $0.0312
    - < 0.01:      6 decimals                   e.g. $0.000123
    """
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.3f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


def fmt_price_plain(price: float) -> str:
    """Same as fmt_price but without the $ sign (for inline use)"""
    return fmt_price(price).lstrip("$")


# ============================================================================
# AI NARRATIVE VIA OPENROUTER
# ============================================================================

async def get_ai_narrative(setup_data: dict, symbol: str, timeframe: str) -> dict:
    """
    Call OpenRouter to generate the three-part narrative:
    - analysis paragraph
    - three scenario bullets with probabilities
    Returns dict with keys: 'analysis', 'scenarios'
    Falls back to rule-based text on any error.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set — using rule-based narrative")
        return _rule_based_narrative(setup_data, symbol, timeframe)

    score        = setup_data.get("score", 50)
    direction    = setup_data.get("direction", "NEUTRAL")
    confidence   = setup_data.get("confidence", 50)
    current_price = setup_data.get("current_price", 0)
    trend_context = setup_data.get("trend_context", "RANGING")
    support_levels    = setup_data.get("support_levels", [])
    resistance_levels = setup_data.get("resistance_levels", [])
    bullish_signals   = setup_data.get("bullish_signals", [])
    bearish_signals   = setup_data.get("bearish_signals", [])
    entry_zone   = setup_data.get("entry_zone", [current_price * 0.99, current_price * 1.01])
    stop_loss    = setup_data.get("stop_loss", current_price * 0.97)
    tp1          = setup_data.get("take_profit_1", current_price * 1.03)
    tp2          = setup_data.get("take_profit_2", current_price * 1.06)
    rr           = setup_data.get("risk_reward", 2.0)

    nearest_support    = support_levels[0]["price"]    if support_levels    else current_price * 0.97
    nearest_resistance = resistance_levels[0]["price"] if resistance_levels else current_price * 1.03

    prompt = f"""You are a professional crypto trader writing a concise setup brief for {symbol}/USDT on the {timeframe} timeframe.

Market data:
- Price: {fmt_price(current_price)}
- Direction: {direction}
- Trend: {trend_context}
- Setup score: {score}/100
- Confidence: {confidence}%
- Nearest support: {fmt_price(nearest_support)}
- Nearest resistance: {fmt_price(nearest_resistance)}
- Entry zone: {fmt_price(entry_zone[0])} – {fmt_price(entry_zone[1])}
- Stop loss: {fmt_price(stop_loss)}
- TP1: {fmt_price(tp1)}  TP2: {fmt_price(tp2)}
- Risk:Reward: 1:{rr:.1f}
- Bullish signals: {', '.join(bullish_signals[:4]) if bullish_signals else 'None'}
- Bearish signals: {', '.join(bearish_signals[:4]) if bearish_signals else 'None'}

Write TWO sections — keep it tight, no fluff:

SECTION 1 — ANALYSIS (3-5 plain sentences, no bullet points):
Describe what the chart is saying. Mention the current structure, where price is relative to key levels, momentum state, and what the best/base/worst case outcomes are.
Do not make mention of section 2 in section 1 analysis at all
SECTION 2 — THREE SCENARIOS (strict format, each on its own line):
BREAKOUT|<probability 5-40>%|<1-sentence trigger>|{fmt_price_plain(entry_zone[1])}|{fmt_price_plain(tp1)}|{fmt_price_plain(stop_loss)}
PULLBACK_LONG|<probability 20-70>%|<1-sentence trigger>|{fmt_price_plain(entry_zone[0])}|{fmt_price_plain(tp1)}/{fmt_price_plain(tp2)}|{fmt_price_plain(stop_loss)}
BREAKDOWN|<probability 5-40>%|<1-sentence trigger>|<next major level>

Probabilities must sum to 100. Mark the highest-probability scenario with ✅ Preferred.
Only output the two sections, nothing else."""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/your_bot",  # update as needed
                },
                json={
                    "model": "anthropic/claude-3-haiku",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                }
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        return _parse_ai_response(raw, setup_data, symbol, timeframe)

    except Exception as e:
        logger.warning(f"OpenRouter call failed ({e}) — using rule-based narrative")
        return _rule_based_narrative(setup_data, symbol, timeframe)


def _parse_ai_response(raw: str, setup_data: dict, symbol: str, timeframe: str) -> dict:
    """Parse the structured AI response into analysis + scenarios."""
    try:
        lines = raw.split("\n")
        analysis_lines = []
        scenario_lines = []
        in_scenarios = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("BREAKOUT|", "PULLBACK_LONG|", "PULLBACK SHORT|", "BREAKDOWN|")):
                in_scenarios = True
            if in_scenarios:
                scenario_lines.append(stripped)
            else:
                analysis_lines.append(stripped)

        analysis = " ".join(analysis_lines).replace("SECTION 1 — ANALYSIS", "").strip(" —:")

        scenarios = []
        emoji_map = {"BREAKOUT": "1️⃣", "PULLBACK_LONG": "2️⃣", "PULLBACK SHORT": "2️⃣", "BREAKDOWN": "3️⃣"}
        label_map = {"BREAKOUT": "BREAKOUT", "PULLBACK_LONG": "PULLBACK LONG", "PULLBACK SHORT": "PULLBACK SHORT", "BREAKDOWN": "BREAKDOWN"}

        for sline in scenario_lines:
            parts = sline.split("|")
            if len(parts) < 3:
                continue
            stype    = parts[0].strip()
            prob     = parts[1].strip()
            trigger  = parts[2].strip()
            preferred = "✅ Preferred" in sline
            # Clean preferred marker from trigger
            trigger = trigger.replace("✅ Preferred", "").strip()

            entry = parts[3].strip() if len(parts) > 3 else ""
            tp    = parts[4].strip() if len(parts) > 4 else ""
            sl    = parts[5].strip() if len(parts) > 5 else ""

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
    """Fallback narrative when AI is unavailable."""
    direction     = setup_data.get("direction", "NEUTRAL")
    trend_context = setup_data.get("trend_context", "RANGING")
    current_price = setup_data.get("current_price", 0)
    support_levels    = setup_data.get("support_levels", [])
    resistance_levels = setup_data.get("resistance_levels", [])
    entry_zone   = setup_data.get("entry_zone", [current_price * 0.99, current_price * 1.01])
    stop_loss    = setup_data.get("stop_loss", current_price * 0.97)
    tp1          = setup_data.get("take_profit_1", current_price * 1.03)
    tp2          = setup_data.get("take_profit_2", current_price * 1.06)

    nearest_s = support_levels[0]["price"]    if support_levels    else current_price * 0.97
    nearest_r = resistance_levels[0]["price"] if resistance_levels else current_price * 1.03

    if direction == "BULLISH":
        analysis = (
            f"Structure is bullish with price trading above key support at {fmt_price(nearest_s)}. "
            f"The {trend_context.lower()} trend suggests momentum may continue, though overhead resistance at "
            f"{fmt_price(nearest_r)} could slow progress. "
            f"Best case: clean breakout above {fmt_price(nearest_r)}. "
            f"Base case: consolidation before next leg. "
            f"Worst case: loss of {fmt_price(nearest_s)} triggers deeper correction."
        )
        scenarios = [
            {"emoji": "1️⃣", "label": "BREAKOUT",      "prob": "25%", "trigger": f"Close above {fmt_price(nearest_r)} with volume",        "entry": fmt_price_plain(entry_zone[1]), "tp": fmt_price_plain(tp1),              "sl": fmt_price_plain(stop_loss), "preferred": False},
            {"emoji": "2️⃣", "label": "PULLBACK LONG", "prob": "55%", "trigger": f"Dip to {fmt_price(entry_zone[0])}-{fmt_price(entry_zone[1])} zone", "entry": fmt_price_plain(entry_zone[0]), "tp": f"{fmt_price_plain(tp1)}/{fmt_price_plain(tp2)}", "sl": fmt_price_plain(stop_loss), "preferred": True},
            {"emoji": "3️⃣", "label": "BREAKDOWN",     "prob": "20%", "trigger": f"Loss of {fmt_price(nearest_s)} support",                 "entry": "", "tp": "",                           "sl": "", "preferred": False},
        ]
    elif direction == "BEARISH":
        analysis = (
            f"Structure is bearish with price failing at resistance near {fmt_price(nearest_r)}. "
            f"The {trend_context.lower()} regime puts sellers in control. "
            f"Best case: bounce off {fmt_price(nearest_s)} for a counter-trend trade. "
            f"Base case: continuation lower toward {fmt_price(nearest_s)}. "
            f"Worst case: capitulation through {fmt_price(nearest_s)} opens deeper downside."
        )
        scenarios = [
            {"emoji": "1️⃣", "label": "BREAKDOWN",      "prob": "50%", "trigger": f"Break below {fmt_price(nearest_s)} with volume",    "entry": fmt_price_plain(entry_zone[0]), "tp": fmt_price_plain(stop_loss),              "sl": fmt_price_plain(entry_zone[1]), "preferred": True},
            {"emoji": "2️⃣", "label": "PULLBACK SHORT", "prob": "30%", "trigger": f"Bounce to {fmt_price(entry_zone[0])}-{fmt_price(nearest_r)}", "entry": fmt_price_plain(entry_zone[1]), "tp": f"{fmt_price_plain(tp1)}/{fmt_price_plain(tp2)}", "sl": fmt_price_plain(nearest_r), "preferred": False},
            {"emoji": "3️⃣", "label": "REVERSAL",       "prob": "20%", "trigger": f"Reclaim of {fmt_price(nearest_r)} flips structure",   "entry": "", "tp": "",                             "sl": "", "preferred": False},
        ]
    else:
        analysis = (
            f"{symbol} is in a neutral {trend_context.lower()} range between "
            f"{fmt_price(nearest_s)} and {fmt_price(nearest_r)}. "
            f"No clear directional edge — patience is the best strategy here. "
            f"Best case: range resolves with a clean breakout. "
            f"Base case: continued chop. "
            f"Worst case: false breakout traps traders on both sides."
        )
        scenarios = [
            {"emoji": "1️⃣", "label": "BREAKOUT",   "prob": "35%", "trigger": f"Sustained close above {fmt_price(nearest_r)}",   "entry": fmt_price_plain(nearest_r), "tp": fmt_price_plain(tp1), "sl": fmt_price_plain(nearest_s), "preferred": False},
            {"emoji": "2️⃣", "label": "RANGE PLAY", "prob": "40%", "trigger": f"Fade edges: buy {fmt_price(nearest_s)}, sell {fmt_price(nearest_r)}", "entry": "", "tp": "", "sl": "", "preferred": True},
            {"emoji": "3️⃣", "label": "BREAKDOWN",  "prob": "25%", "trigger": f"Loss of {fmt_price(nearest_s)} support",           "entry": "", "tp": "", "sl": "", "preferred": False},
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
# MESSAGE FORMATTER
# ============================================================================

async def format_setup_message(setup_data: dict, symbol: str, timeframe: str) -> str:
    """Build the new-style setup message with AI narrative."""

    score         = setup_data.get("score", 50)
    confidence    = setup_data.get("confidence", 50)
    direction     = setup_data.get("direction", "NEUTRAL")
    current_price = setup_data.get("current_price", 0)
    trend_context = setup_data.get("trend_context", "RANGING")

    quality_grade = score_to_grade(score)
    timing_grade  = confidence_to_timing_grade(confidence)
    act_signal    = act_now(score, confidence)

    # ── AI narrative ──────────────────────────────────────────────────
    narrative = await get_ai_narrative(setup_data, symbol, timeframe)
    analysis  = narrative.get("analysis", "")
    scenarios = narrative.get("scenarios", [])

    # ── Header ────────────────────────────────────────────────────────
    msg = (
        f"🎯 *Professional Setup — {symbol}/USDT ({timeframe})*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{fmt_price(current_price)} | Regime: {trend_context}\n\n"
        f"🏆 Setup Quality: *{quality_grade}*  |  Entry Timing: *{timing_grade}*\n"
        f"⚡ Act Now: {act_signal}   |  Timeframe Fit: {timeframe} ✓\n\n"
    )

    # ── Analysis ──────────────────────────────────────────────────────
    msg += (
        f"─────────────────────────────\n"
        f"🧠 *ANALYSIS*\n"
        f"─────────────────────────────\n"
        f"{analysis}\n\n"
    )

    # ── Scenarios ─────────────────────────────────────────────────────
    msg += (
        f"─────────────────────────────\n"
        f"🎯 *THREE SCENARIOS*\n"
        f"─────────────────────────────\n"
    )

    for i, s in enumerate(scenarios[:3]):
        preferred_tag = "  ✅ Preferred" if s.get("preferred") else ""
        msg += f"{s['emoji']} *{s['label']}* ({s['prob']} probability){preferred_tag}\n"
        msg += f"   Trigger: {s['trigger']}\n"

        # Build entry/tp/sl line only if we have values
        detail_parts = []
        if s.get("entry"):
            detail_parts.append(f"Entry: ${s['entry']}")
        if s.get("tp"):
            detail_parts.append(f"TP: ${s['tp']}")
        if s.get("sl"):
            detail_parts.append(f"SL: ${s['sl']}")
        if detail_parts:
            msg += f"   {' | '.join(detail_parts)}\n"
        msg += "\n"

    # ── Key Levels (compact) ─────────────────────────────────────────
    support_levels    = setup_data.get("support_levels", [])
    resistance_levels = setup_data.get("resistance_levels", [])

    if support_levels or resistance_levels:
        msg += f"─────────────────────────────\n📍 *KEY LEVELS*\n─────────────────────────────\n"
        if resistance_levels:
            r = resistance_levels[0]
            dist = ((r["price"] - current_price) / current_price) * 100
            msg += f"↑ Resistance: {fmt_price(r['price'])} (+{dist:.1f}%, {r['touches']} touches)\n"
        if support_levels:
            s = support_levels[0]
            dist = ((current_price - s["price"]) / current_price) * 100
            msg += f"↓ Support:    {fmt_price(s['price'])} (-{dist:.1f}%, {s['touches']} touches)\n"
        msg += "\n"

    # ── Signals summary (compact) ──────────────────────────────────────
    bullish_signals = setup_data.get("bullish_signals", [])
    bearish_signals = setup_data.get("bearish_signals", [])

    if bullish_signals or bearish_signals:
        bull_count = len(bullish_signals)
        bear_count = len(bearish_signals)
        msg += f"📊 Signals: ✅ {bull_count} bullish  ❌ {bear_count} bearish\n\n"

    # ── Risk factors (if any) ──────────────────────────────────────────
    risk_factors = setup_data.get("risk_factors", [])
    if risk_factors:
        msg += f"⚠️ *Risks:* {' • '.join(risk_factors[:3])}\n\n"

    # ── Position sizing hint (only for actionable setups) ─────────────
    if score >= 55 and confidence >= 60:
        stop_loss = setup_data.get("stop_loss", current_price * 0.97)
        msg += (
            f"📏 `/risk [account] [risk_%] {entry:.0f} {stop_loss:.0f}`\n\n"
        )

    # ── Disclaimer ────────────────────────────────────────────────────
    msg += (
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Not financial advice. DYOR. Use stop losses."
    )

    return msg


# ============================================================================
# SETUP COMMAND
# ============================================================================

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setup [SYMBOL] [TIMEFRAME] — Professional trade setup analyzer
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/setup")
    await handle_streak(update, context)

    # ── Pro gate ──────────────────────────────────────────────────────
    plan = get_user_plan(user_id)
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 *Pro Feature: Trade Setup Analyzer*\n\n"
            "Get professional-grade trade analysis:\n\n"
            "✅ Setup quality grading (A+ to D)\n"
            "✅ Entry timing score\n"
            "✅ AI-written scenario analysis\n"
            "✅ Three probability-weighted scenarios\n"
            "✅ Smart entry/exit zones\n"
            "✅ Risk-reward optimization\n"
            "✅ Key support/resistance levels\n\n"
            "💎 Upgrade to Pro: /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Args ─────────────────────────────────────────────────────────
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ *Usage:* `/setup [SYMBOL] [TIMEFRAME]`\n\n"
            "*Examples:*\n"
            "`/setup BTC 4h` — Bitcoin 4-hour analysis\n"
            "`/setup ETH 1h` — Ethereum 1-hour analysis\n"
            "`/setup SOL 15m` — Solana 15-minute analysis\n\n"
            "*Valid timeframes:*\n"
            "`5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `1d`\n\n"
            f"*Supported:* Top 100 CoinGecko coins\n"
            f"_(Currently {len(SUPPORTED_COINS)} coins available)_",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    symbol    = context.args[0].upper().strip()
    timeframe = context.args[1].lower().strip() if len(context.args) >= 2 else "4h"

    # ── Validate symbol ───────────────────────────────────────────────
    if symbol not in SUPPORTED_COINS:
        await update.message.reply_text(
            f"❌ *{symbol} not supported*\n\n"
            f"Only top 100 CoinGecko coins are supported.\n\n"
            f"*Popular coins:*\n"
            f"• Layer 1: BTC, ETH, SOL, BNB, ADA, AVAX, DOT\n"
            f"• DeFi: UNI, AAVE, LINK, SUSHI, CRV, MKR\n"
            f"• Layer 2: MATIC, ARB, OP\n"
            f"• Memes: DOGE, SHIB, PEPE, WIF\n\n"
            f"_Currently supporting {len(SUPPORTED_COINS)} coins_",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Validate timeframe ────────────────────────────────────────────
    if timeframe not in VALID_TIMEFRAMES:
        await update.message.reply_text(
            f"❌ Invalid timeframe: `{timeframe}`\n\n"
            f"*Valid options:*\n"
            f"• Scalping: `5m`, `15m`, `30m`\n"
            f"• Intraday: `1h`, `2h`\n"
            f"• Swing: `4h`, `8h`\n"
            f"• Position: `1d`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Loading message ───────────────────────────────────────────────
    loading_msg = await update.message.reply_text(
        f"🔄 *Analyzing {symbol} on {timeframe} timeframe*\n\n"
        f"• Fetching market data from CoinGecko\n"
        f"• Calculating technical indicators\n"
        f"• Detecting support/resistance levels\n"
        f"• Generating AI scenario analysis\n\n"
        f"⏱️ This takes 5-15 seconds...",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        # ── Analyze ───────────────────────────────────────────────────
        setup_data = await setup_analyzer.analyze_setup(symbol, timeframe)

        if not setup_data:
            await loading_msg.edit_text(
                f"❌ *Analysis Failed for {symbol}*\n\n"
                f"Possible reasons:\n"
                f"• Insufficient historical data on {timeframe}\n"
                f"• CoinGecko API temporary error\n"
                f"• Network connectivity issue\n\n"
                f"*Try:*\n"
                f"• Different timeframe (e.g., `/setup {symbol} 4h`)\n"
                f"• Wait a moment and try again",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # ── Format (async — calls AI) ─────────────────────────────────
        message = await format_setup_message(setup_data, symbol, timeframe)

        # ── Store & buttons ───────────────────────────────────────────
        setup_id = f"{symbol}_{timeframe}"
        context.user_data[f"setup_{setup_id}"] = setup_data

        keyboard = [
            [InlineKeyboardButton("🔔 Set Entry Alert", callback_data=f"setup_alert_{setup_id}")],
            [
                InlineKeyboardButton("📊 View Charts",  callback_data=f"setup_charts_{setup_id}"),
                InlineKeyboardButton("🔄 Refresh",      callback_data=f"setup_refresh_{setup_id}"),
            ],
        ]

        await loading_msg.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

        logger.info(f"Setup analysis completed: {symbol} {timeframe} (score: {setup_data['score']})")

    except Exception as e:
        logger.exception(f"Error in /setup command for {symbol} {timeframe}")
        await loading_msg.edit_text(
            f"❌ *Setup Analysis Error*\n\n"
            f"An unexpected error occurred while analyzing {symbol}.\n\n"
            f"Please wait 30-60 seconds and try again.\n"
            f"If the issue persists, try a different timeframe or contact /support",
            parse_mode=ParseMode.MARKDOWN,
        )


# ============================================================================
# CALLBACK HANDLERS
# ============================================================================

async def setup_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle set alert button"""
    query = update.callback_query

    try:
        setup_id   = query.data.replace("setup_alert_", "")
        setup_data = context.user_data.get(f"setup_{setup_id}")

        if not setup_data:
            await query.answer("❌ Setup expired. Run /setup again.", show_alert=True)
            return

        parts     = setup_id.split("_")
        symbol    = parts[0]
        direction = setup_data.get("direction", "NEUTRAL")
        entry_zone    = setup_data["entry_zone"]
        current_price = setup_data["current_price"]

        if direction == "BULLISH":
            recommended_price = entry_zone[0]
            direction_word    = "above"
        elif direction == "BEARISH":
            recommended_price = entry_zone[1]
            direction_word    = "below"
        else:
            recommended_price = current_price
            direction_word    = "above"

        # Keep under 200 chars
        rec_str = fmt_price_plain(recommended_price)
        lo_str  = fmt_price_plain(entry_zone[0])
        hi_str  = fmt_price_plain(entry_zone[1])
        cur_str = fmt_price(current_price)

        message = (
            f"🔔 Alert for {symbol}\n\n"
            f"Use: /set {symbol} {direction_word} {rec_str}\n\n"
            f"Current: {cur_str}\n"
            f"Entry: ${lo_str}-${hi_str}"
        )

        if len(message) > 190:
            message = f"🔔 {symbol}\n/set {symbol} {direction_word} {rec_str}\nEntry: ${lo_str}-${hi_str}"

        await query.answer(message, show_alert=True)

    except Exception:
        logger.exception("Setup alert callback error")
        await query.answer(
            "❌ Alert failed\n\nUse: /set [SYMBOL] above [PRICE]\nExample: /set BTC above 95000",
            show_alert=True,
        )


async def setup_charts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle view charts button"""
    query = update.callback_query

    try:
        setup_id = query.data.replace("setup_charts_", "")
        parts    = setup_id.split("_")
        symbol   = parts[0]
        timeframe = parts[1] if len(parts) > 1 else "4h"

        message = (
            f"📊 {symbol} Chart\n\n"
            f"Use: /c {symbol} {timeframe}\n\n"
            f"Shows TradingView chart with key levels marked"
        )
        await query.answer(message, show_alert=True)

    except Exception:
        logger.exception("Setup charts callback error")
        await query.answer("❌ Chart view failed", show_alert=True)


async def setup_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh button"""
    query = update.callback_query

    try:
        await query.answer("🔄 Refreshing...", show_alert=False)

        setup_id  = query.data.replace("setup_refresh_", "")
        parts     = setup_id.split("_")
        symbol    = parts[0]
        timeframe = parts[1] if len(parts) > 1 else "4h"

        await query.edit_message_text(
            f"🔄 Refreshing {symbol} {timeframe}...\n\n⏱️ Please wait 5-15 seconds...",
            parse_mode=ParseMode.MARKDOWN,
        )

        setup_data = await setup_analyzer.analyze_setup(symbol, timeframe)

        if not setup_data:
            await query.edit_message_text(
                f"❌ Refresh failed for {symbol}.\n\nTry: `/setup {symbol} {timeframe}`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        message = await format_setup_message(setup_data, symbol, timeframe)

        context.user_data[f"setup_{setup_id}"] = setup_data

        keyboard = [
            [InlineKeyboardButton("🔔 Set Entry Alert", callback_data=f"setup_alert_{setup_id}")],
            [
                InlineKeyboardButton("📊 View Charts",  callback_data=f"setup_charts_{setup_id}"),
                InlineKeyboardButton("🔄 Refresh",      callback_data=f"setup_refresh_{setup_id}"),
            ],
        ]

        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

        logger.info(f"Setup refreshed: {symbol} {timeframe}")

    except Exception:
        logger.exception("Setup refresh callback error")
        await query.edit_message_text(
            "❌ Refresh failed. Try `/setup [SYMBOL] [TIMEFRAME]`",
            parse_mode=ParseMode.MARKDOWN,
        )


# ============================================================================
# REGISTER HANDLERS
# ============================================================================

def register_setup_handlers(app):
    """Register all setup command and callback handlers"""
    from telegram.ext import CommandHandler, CallbackQueryHandler

    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CallbackQueryHandler(setup_alert_callback, pattern="^setup_alert_"))
    app.add_handler(CallbackQueryHandler(setup_charts_callback, pattern="^setup_charts_"))
    app.add_handler(CallbackQueryHandler(setup_refresh_callback, pattern="^setup_refresh_"))

    logger.info("Setup handlers registered successfully")
