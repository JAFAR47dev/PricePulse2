# handlers/screener.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.screener_engine import run_screener, is_cache_fresh, get_precomputed_results
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active

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


async def screener_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/screener")

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

    # Extract chosen strategy
    strategy_key = query.data.replace("screener_", "")
    strategy_info = STRATEGIES.get(strategy_key)

    if not strategy_info:
        return await query.edit_message_text("⚠️ Invalid strategy.")

    strategy_name = strategy_info["name"]
    strategy_explanation = strategy_info["explanation"]

    # Check if we have pre-computed results
    has_cache = get_precomputed_results(strategy_key) is not None
    
    if has_cache:
        # Instant response from cache
        await query.edit_message_text(
            f"🔍 *{strategy_name}*\n\n"
            f"_{strategy_explanation}_\n\n"
            "⚡ Loading results...",
            parse_mode="Markdown"
        )
    else:
        # First run or cache expired - will take longer
        await query.edit_message_text(
            f"🔍 *{strategy_name}*\n\n"
            f"_{strategy_explanation}_\n\n"
            "🔄 Scanning 100 coins... This may take a few minutes on first run.\n"
            "Future scans will be instant! ⚡",
            parse_mode="Markdown"
        )

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # -------------------------------
    # 🚀 Run screener (uses cache when available)
    # -------------------------------
    try:
        results = await run_screener(strategy_key)
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
        return await query.message.reply_text(
            "❌ No coins matched this strategy right now.\n"
            "Market conditions are constantly changing — try another strategy or check back later.",
            parse_mode="Markdown"
        )

    # -------------------------------
    # ✅ Output top matches
    # -------------------------------
    msg = f"✅ *Top Matches for {strategy_name}*\n"
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
    
    # Add freshness indicator
    if is_cache_fresh():
        msg += "\n🟢 _Data updated in last 5 minutes_"
    else:
        msg += "\n🟡 _Cache updating in background_"

    await query.message.reply_text(msg, parse_mode="Markdown")