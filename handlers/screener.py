import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.screener_engine import run_screener, is_cache_fresh, get_precomputed_results
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak

# Beginner-friendly strategy names with explanations
STRATEGIES = {
    "strat_1": {
        "name": "Strong Bounce Setup",
        "explanation": "Finds coins that hit support levels and are bouncing back up with strong buying pressure. Great for catching rebounds."
    },
    "strat_2": {
        "name": "Breakout with Momentum",
        "explanation": "Identifies coins breaking above resistance with high volume. These are strong moves that could continue higher."
    },
    "strat_3": {
        "name": "Reversal After Sell-Off",
        "explanation": "Spots oversold coins showing early signs of recovery. Looks for bottoms after sharp declines."
    },
    "strat_4": {
        "name": "Trend Turning Bullish",
        "explanation": "Detects coins where downtrends are ending and uptrends are beginning. Catches momentum shifts early."
    },
    "strat_5": {
        "name": "Deep Pullback Opportunity",
        "explanation": "Finds healthy corrections in uptrends where coins dip but remain strong. Good entry points in established trends."
    }
}

# Timeframe options
TIMEFRAMES = {
    "5m": "5 Minutes",
    "15m": "15 Minutes",
    "30m": "30 Minutes",
    "1h": "1 Hour",
    "4h": "4 Hours",
    "1d": "1 Day"
}

# Priority timeframes — must match screener_job.py
_PRIORITY_TIMEFRAMES = ["1h", "4h", "1d"]


def _get_overall_cache_status() -> str:
    """
    Returns a status string reflecting how many priority timeframes are warm.
    Checks 1h, 4h, 1d — the most commonly used timeframes.
    Shows green only when all three are ready.
    """
    warm = sum(1 for tf in _PRIORITY_TIMEFRAMES if is_cache_fresh(tf, max_age_seconds=3600))
    total = len(_PRIORITY_TIMEFRAMES)

    if warm == total:
        return "🟢 Live data ready"
    elif warm > 0:
        return f"🟡 Warming up ({warm}/{total} ready)"
    else:
        return "🔴 Initializing — first scan may be slow"


async def screener_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/screener")
    await handle_streak(update, context)

    plan = get_user_plan(user_id)

    # ❌ Free Plan — Block Access
    if not is_pro_plan(plan):
        upgrade_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Upgrade to Pro", callback_data="upgrade_menu")
        ]])
        return await update.message.reply_text(
            "🔒 The *Multi-Coin Screener* is only available to *Pro users*.\n\n"
            "Upgrade now to scan 100 coins in real-time.",
            reply_markup=upgrade_button,
            parse_mode="Markdown"
        )

    # ✅ Show strategy list
    keyboard = [
        [InlineKeyboardButton(strategy["name"], callback_data=f"screener_{key}")]
        for key, strategy in STRATEGIES.items()
    ]

    # FIX: Use _get_overall_cache_status() instead of is_cache_fresh() with no args.
    # Old code only checked 1h, showing 🟢 even when 4h/1d caches were empty.
    cache_status = _get_overall_cache_status()

    await update.message.reply_text(
        f"📊 *Multi-Coin Screener* {cache_status}\n\n"
        "Select a strategy to scan 100 coins:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def screener_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    plan = get_user_plan(user_id)

    # ❌ Free Plan — Block Access
    if not is_pro_plan(plan):
        return await query.edit_message_text(
            "🔒 This screener is *Pro only*.\nUpgrade to unlock all advanced features.",
            parse_mode="Markdown"
        )

    callback_data = query.data

    # Handle back button
    if callback_data == "screener_back":
        await screener_back(update, context)
        return

    # Timeframe selection — format: screener_tf_strat_1_1h
    if callback_data.startswith("screener_tf_"):
        parts = callback_data.replace("screener_tf_", "")
        parts_split = parts.rsplit("_", 1)  # ["strat_1", "1h"]

        if len(parts_split) != 2:
            return await query.edit_message_text("⚠️ Invalid selection.")

        strategy_key, timeframe = parts_split
        await run_screener_scan(query, strategy_key, timeframe)
        return

    # Strategy selection — format: screener_strat_1
    elif callback_data.startswith("screener_"):
        strategy_key = callback_data.replace("screener_", "")
        strategy_info = STRATEGIES.get(strategy_key)

        if not strategy_info:
            return await query.edit_message_text("⚠️ Invalid strategy.")

        await show_timeframe_selection(query, strategy_key, strategy_info)


async def show_timeframe_selection(query, strategy_key: str, strategy_info: dict):
    """Display timeframe selection buttons with per-timeframe cache status."""
    strategy_name = strategy_info["name"]
    strategy_explanation = strategy_info["explanation"]

    # Create timeframe buttons (2 per row) with cache indicator per timeframe
    keyboard = []
    timeframe_items = list(TIMEFRAMES.items())

    for i in range(0, len(timeframe_items), 2):
        row = []
        for j in range(2):
            if i + j < len(timeframe_items):
                tf_key, tf_name = timeframe_items[i + j]
                # FIX: Show ⚡ on button if that specific timeframe cache is warm,
                # so users know which timeframes will respond instantly.
                is_warm = is_cache_fresh(tf_key, max_age_seconds=3600)
                label = f"⚡ {tf_name}" if is_warm else tf_name
                row.append(
                    InlineKeyboardButton(
                        label,
                        callback_data=f"screener_tf_{strategy_key}_{tf_key}"
                    )
                )
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅️ Back to Strategies", callback_data="screener_back")])

    await query.edit_message_text(
        f"🔍 *{strategy_name}*\n\n"
        f"_{strategy_explanation}_\n\n"
        "⏱️ Select a timeframe:\n"
        "_⚡ = instant results available_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def run_screener_scan(query, strategy_key: str, timeframe: str):
    """
    Execute the screener scan with selected strategy and timeframe.

    FIX: Wrapped run_screener() in asyncio.wait_for() with a 30-second timeout.
    Previously, if cache was cold, this would await for 5+ minutes, freezing
    the entire bot for all users. Now it times out gracefully after 30 seconds
    and shows a friendly message. Since cache is warm within ~15 min of deploy,
    users should rarely (if ever) hit this timeout in normal operation.
    """
    strategy_info = STRATEGIES.get(strategy_key)
    if not strategy_info:
        return await query.edit_message_text("⚠️ Invalid strategy.")

    strategy_name = strategy_info["name"]
    strategy_explanation = strategy_info["explanation"]
    timeframe_name = TIMEFRAMES.get(timeframe, timeframe)

    has_cache = get_precomputed_results(strategy_key, timeframe) is not None

    if has_cache:
        await query.edit_message_text(
            f"🔍 *{strategy_name}* ({timeframe_name})\n\n"
            f"_{strategy_explanation}_\n\n"
            "⚡ Loading results...",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"🔍 *{strategy_name}* ({timeframe_name})\n\n"
            f"_{strategy_explanation}_\n\n"
            "🔄 Cache is warming up, scanning now...\n"
            "This only happens once after a fresh deploy — future scans are instant! ⚡",
            parse_mode="Markdown"
        )

    # FIX: asyncio.wait_for prevents this from blocking the event loop indefinitely.
    # 30 seconds is more than enough for a cache hit (returns in <1s).
    # On a cold cache the live scan would take 5+ min — we bail early instead.
    try:
        results = await asyncio.wait_for(
            run_screener(strategy_key, timeframe),
            timeout=30
        )
    except asyncio.TimeoutError:
        keyboard = [[
            InlineKeyboardButton("🔄 Try Again", callback_data=f"screener_tf_{strategy_key}_{timeframe}"),
            InlineKeyboardButton("⬅️ Back", callback_data="screener_back")
        ]]
        return await query.message.reply_text(
            "⏳ *Cache is still warming up.*\n\n"
            "Please try again in a moment — results will be instant once ready! ⚡",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[screener_handler] Error running screener: {e}")
        return await query.message.reply_text(
            "❌ An error occurred while scanning.\n"
            "Please try again in a moment.",
            parse_mode="Markdown"
        )

    # ❌ No matches
    if not results:
        keyboard = [[
            InlineKeyboardButton("🔄 Try Another Timeframe", callback_data=f"screener_{strategy_key}"),
            InlineKeyboardButton("⬅️ Back", callback_data="screener_back")
        ]]
        return await query.message.reply_text(
            f"❌ No coins matched *{strategy_name}* on *{timeframe_name}* timeframe.\n\n"
            "Market conditions are constantly changing — try another timeframe or strategy.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # ✅ Output top matches
    msg = f"✅ *Top Matches for {strategy_name}*\n"
    msg += f"⏱️ Timeframe: *{timeframe_name}*\n"
    msg += f"Found {len(results)} coin(s)\n\n"

    for i, coin in enumerate(results[:10], 1):
        symbol = coin.get("symbol", "Unknown")
        score = coin.get("score", 0)
        close = coin.get("close")
        rsi = coin.get("rsi")

        price_str = f"${close:.2f}" if close is not None else "N/A"
        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"

        msg += (
            f"{i}. *{symbol}* — Score: `{score}`\n"
            f"   Price: `{price_str}` | RSI: `{rsi_str}`\n\n"
        )

    if len(results) > 10:
        msg += f"_Showing top 10 of {len(results)} matches_\n"

    keyboard = [[
        InlineKeyboardButton("🔄 Try Another Timeframe", callback_data=f"screener_{strategy_key}"),
        InlineKeyboardButton("⬅️ Back", callback_data="screener_back")
    ]]

    await query.message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def screener_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button — return to strategy selection."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton(strategy["name"], callback_data=f"screener_{key}")]
        for key, strategy in STRATEGIES.items()
    ]

    # FIX: Same as screener_command — use _get_overall_cache_status() not is_cache_fresh()
    cache_status = _get_overall_cache_status()

    await query.edit_message_text(
        f"📊 *Multi-Coin Screener* {cache_status}\n\n"
        "Select a strategy to scan 100 coins:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
