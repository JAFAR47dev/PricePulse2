# handlers/screener.py
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


async def screener_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/screener")
    await handle_streak(update, context)
    
    plan = get_user_plan(user_id)

    # -------------------------------
    # ❌ Free Plan — Block Access
    # -------------------------------
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

    # -------------------------------
    # ✅ Show strategy list
    # -------------------------------
    keyboard = [
        [InlineKeyboardButton(strategy["name"], callback_data=f"screener_{key}")]
        for key, strategy in STRATEGIES.items()
    ]
    
    # Add cache status indicator
    cache_status = "🟢 Live data" if is_cache_fresh() else "🟡 Initializing"

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

    # -------------------------------
    # ❌ Free Plan — Block Access
    # -------------------------------
    if not is_pro_plan(plan):
        return await query.edit_message_text(
            "🔒 This screener is *Pro only*.\nUpgrade to unlock all advanced features.",
            parse_mode="Markdown"
        )

    # -------------------------------
    # Handle different callback types
    # -------------------------------
    callback_data = query.data
    
    # Handle back button
    if callback_data == "screener_back":
        await screener_back(update, context)
        return
    
    # Check if this is a timeframe selection
    if callback_data.startswith("screener_tf_"):
        # Format: screener_tf_STRATEGY_TIMEFRAME
        # Example: screener_tf_strat_1_1h
        parts = callback_data.replace("screener_tf_", "")  # "strat_1_1h"
        
        # Split from the right to get timeframe (last part)
        # This handles strategy keys with underscores like "strat_1"
        parts_split = parts.rsplit("_", 1)  # ["strat_1", "1h"]
        
        if len(parts_split) != 2:
            return await query.edit_message_text("⚠️ Invalid selection.")
        
        strategy_key, timeframe = parts_split
        await run_screener_scan(query, strategy_key, timeframe)
        return
        
    # Check if this is a strategy selection
    elif callback_data.startswith("screener_"):
        strategy_key = callback_data.replace("screener_", "")
        strategy_info = STRATEGIES.get(strategy_key)

        if not strategy_info:
            return await query.edit_message_text("⚠️ Invalid strategy.")

        # Show timeframe selection
        await show_timeframe_selection(query, strategy_key, strategy_info)
        
async def show_timeframe_selection(query, strategy_key: str, strategy_info: dict):
    """Display timeframe selection buttons"""
    strategy_name = strategy_info["name"]
    strategy_explanation = strategy_info["explanation"]
    
    # Create timeframe buttons (2 per row)
    keyboard = []
    timeframe_items = list(TIMEFRAMES.items())
    
    for i in range(0, len(timeframe_items), 2):
        row = []
        for j in range(2):
            if i + j < len(timeframe_items):
                tf_key, tf_name = timeframe_items[i + j]
                row.append(
                    InlineKeyboardButton(
                        tf_name, 
                        callback_data=f"screener_tf_{strategy_key}_{tf_key}"
                    )
                )
        keyboard.append(row)
    
    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Back to Strategies", callback_data="screener_back")])
    
    await query.edit_message_text(
        f"🔍 *{strategy_name}*\n\n"
        f"_{strategy_explanation}_\n\n"
        "⏱️ Select a timeframe:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def run_screener_scan(query, strategy_key: str, timeframe: str):
    """Execute the screener scan with selected strategy and timeframe"""
    strategy_info = STRATEGIES.get(strategy_key)
    if not strategy_info:
        return await query.edit_message_text("⚠️ Invalid strategy.")
    
    strategy_name = strategy_info["name"]
    strategy_explanation = strategy_info["explanation"]
    timeframe_name = TIMEFRAMES.get(timeframe, timeframe)

    # Check if we have pre-computed results
    has_cache = get_precomputed_results(strategy_key, timeframe) is not None
    
    if has_cache:
        # Instant response from cache
        await query.edit_message_text(
            f"🔍 *{strategy_name}* ({timeframe_name})\n\n"
            f"_{strategy_explanation}_\n\n"
            "⚡ Loading results...",
            parse_mode="Markdown"
        )
    else:
        # First run or cache expired - will take longer
        await query.edit_message_text(
            f"🔍 *{strategy_name}* ({timeframe_name})\n\n"
            f"_{strategy_explanation}_\n\n"
            "🔄 Scanning 100 coins... This may take a few minutes on first run.\n"
            "Future scans will be instant! ⚡",
            parse_mode="Markdown"
        )

    # -------------------------------
    # 🚀 Run screener (uses cache when available)
    # -------------------------------
    try:
        results = await run_screener(strategy_key, timeframe)
    except Exception as e:
        print(f"[screener_handler] Error running screener: {e}")
        return await query.message.reply_text(
            "❌ An error occurred while scanning.\n"
            "Please try again in a moment.",
            parse_mode="Markdown"
        )

    # -------------------------------
    # ❌ No matches
    # -------------------------------
    if not results:
        # Add back button
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

    # -------------------------------
    # ✅ Output top matches
    # -------------------------------
    msg = f"✅ *Top Matches for {strategy_name}*\n"
    msg += f"⏱️ Timeframe: *{timeframe_name}*\n"
    msg += f"Found {len(results)} coin(s)\n\n"

    for i, coin in enumerate(results[:10], 1):
        # Safely handle None values
        symbol = coin.get('symbol', 'Unknown')
        score = coin.get('score', 0)
        close = coin.get('close')
        rsi = coin.get('rsi')
        
        # Format price
        price_str = f"${close:.2f}" if close is not None else "N/A"
        
        # Format RSI
        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
        
        msg += (
            f"{i}. *{symbol}* — Score: `{score}`\n"
            f"   Price: `{price_str}` | RSI: `{rsi_str}`\n\n"
        )
    
    # Add footer with additional info
    if len(results) > 10:
        msg += f"_Showing top 10 of {len(results)} matches_\n"
    
    # Add action buttons
    keyboard = [[
        InlineKeyboardButton("🔄 Try Another Timeframe", callback_data=f"screener_{strategy_key}"),
        InlineKeyboardButton("⬅️ Back", callback_data="screener_back")
    ]]
    
    await query.message.reply_text(
        msg, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# Add handler for back button
async def screener_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button to return to strategy selection"""
    query = update.callback_query
    await query.answer()
    
    # Show strategy list again
    keyboard = [
        [InlineKeyboardButton(strategy["name"], callback_data=f"screener_{key}")]
        for key, strategy in STRATEGIES.items()
    ]
    
    cache_status = "🟢 Live data" if is_cache_fresh() else "🟡 Initializing"

    await query.edit_message_text(
        f"📊 *Multi-Coin Screener* {cache_status}\n\n"
        "Select a strategy to scan 100 coins:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )