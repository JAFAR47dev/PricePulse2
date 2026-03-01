"""
Enhanced coin command handler with collision awareness
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.coin_data import get_coin_data, COINGECKO_IDS
from utils.formatting import format_large_number
from tasks.handlers import handle_streak
from models.user_activity import update_last_active


def get_rank_emoji(rank: int) -> str:
    """
    Get dynamic emoji based on market cap rank
    
    Args:
        rank: Market cap rank (1-10000+)
    
    Returns:
        Emoji string representing rank tier
    """
    if rank == 1:
        return "👑"  # King - #1 spot
    elif rank == 2:
        return "🥈"  # Silver medal
    elif rank == 3:
        return "🥉"  # Bronze medal
    elif rank <= 10:
        return "🏅"  # Top 10
    elif rank <= 50:
        return "⭐"  # Top 50
    elif rank <= 100:
        return "💎"  # Top 100
    elif rank <= 500:
        return "🪙"  # Top 500
    else:
        return "📊"  # Beyond top 500


def _check_for_collision(symbol: str) -> tuple:
    """
    Check if symbol has collisions and return collision info
    
    Returns:
        tuple: (has_collision: bool, num_coins: int, coin_names: list)
    """
    symbol_lower = symbol.lower()
    coin_entries = COINGECKO_IDS.get(symbol_lower, [])
    
    has_collision = len(coin_entries) > 1
    num_coins = len(coin_entries)
    coin_names = [entry.get("name", "Unknown") for entry in coin_entries]
    
    return has_collision, num_coins, coin_names


async def coin_alias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle coin lookup commands with collision awareness.
    Automatically shows the highest market cap coin when collisions exist.
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/coin_alias")
    await handle_streak(update, context)
    
    cmd = update.message.text.strip().lstrip("/")
    
    # Check for collisions before fetching data
    has_collision, num_coins, coin_names = _check_for_collision(cmd)
    
    # Fetch coin data (will automatically resolve to highest market cap)
    coin_data = get_coin_data(cmd)

    if not coin_data:
        await update.message.reply_text(
            f"❌ Coin `{cmd.upper()}` not found.\n\n"
            f"Tip: Try the full coin name or check /coins for supported symbols.",
            parse_mode="Markdown"
        )
        return

    m = coin_data["market_data"]
    
    # Extract price data
    pc_1h = m.get("price_change_percentage_1h_in_currency", {}).get("usd", 0) or 0
    pc_24h = m.get("price_change_percentage_24h_in_currency", {}).get("usd", 0) or 0
    pc_7d = m.get("price_change_percentage_7d_in_currency", {}).get("usd", 0) or 0
    pc_30d = m.get("price_change_percentage_30d_in_currency", {}).get("usd", 0) or 0
    
    price = m.get("current_price", {}).get("usd", 0) or 0
    ath = m.get("ath", {}).get("usd", 0) or 0
    vol = m.get("total_volume", {}).get("usd", 0) or 0
    cap = m.get("market_cap", {}).get("usd", 0) or 0
    high = m.get("high_24h", {}).get("usd", 0) or 0
    low = m.get("low_24h", {}).get("usd", 0) or 0
    
    # Get market cap rank
    rank = coin_data.get("market_cap_rank", 0) or 0
    rank_emoji = get_rank_emoji(rank)

    # Calculate % difference from ATH to current price
    if ath > 0:
        ath_change_pct = ((price - ath) / ath) * 100
    else:
        ath_change_pct = 0

    # Format large numbers
    ath_display = format_large_number(ath)
    vol_display = format_large_number(vol)
    cap_display = format_large_number(cap)

    # Determine price formatting based on value
    if price >= 1:
        price_str = f"${price:,.2f}"
    elif price >= 0.01:
        price_str = f"${price:,.4f}"
    else:
        price_str = f"${price:,.8f}"

    # Format high/low
    if high >= 1:
        high_str = f"${high:,.2f}"
    else:
        high_str = f"${high:,.6f}"
    
    if low >= 1:
        low_str = f"${low:,.2f}"
    else:
        low_str = f"${low:,.6f}"

    # Build main message
    coin_name = coin_data['name']
    coin_symbol = coin_data['symbol'].upper()
    
    # Add collision notice if applicable
    collision_notice = ""
    if has_collision:
        other_coins = [name for name in coin_names if name != coin_name]
        collision_notice = (
            f"\n⚠️ _Note: Multiple coins share '{coin_symbol}' symbol. "
            f"Showing highest market cap: {coin_name}_\n"
        )

    msg = f"""📊 *{coin_name}* (`{coin_symbol}`) {rank_emoji} #{rank}

💰 Price: `{price_str}`
📈 24h High: `{high_str}`
📉 24h Low: `{low_str}`
🕐 1h: {pc_1h:+.2f}%
📅 24h: {pc_24h:+.2f}%
📆 7d: {pc_7d:+.2f}%
🗓 30d: {pc_30d:+.2f}%
📛 ATH: `${ath_display}` ({ath_change_pct:+.2f}%)
🔁 24h Volume: `${vol_display}`
🌍 Market Cap: `${cap_display}`
"""

    # Add buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 View Chart", callback_data=f"chart_{coin_symbol}_1h"),
            InlineKeyboardButton("➕ Add Alert", callback_data=f"addalert_{coin_symbol}")
        ]
    ])

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


async def handle_chart_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chart button callback"""
    query = update.callback_query
    await query.answer()

    try:
        parts = query.data.split("_")
        if len(parts) == 3 and parts[0] == "chart":
            symbol = parts[1]
            timeframe = parts[2]

            from .chart import show_chart
            context.args = [symbol, timeframe]
            await show_chart(update, context)
        else:
            await query.message.reply_text("⚠️ Invalid chart data.")
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")


async def handle_add_alert_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add alert button callback"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    if len(parts) == 2 and parts[0] == "addalert":
        symbol = parts[1]
        
        # Import here to avoid circular imports
        from handlers.set_alert.flow_manager import start_set_alert
        
        # Pass symbol to alert flow
        context.user_data['alert_symbol'] = symbol
        await start_set_alert(update, context)


# List of excluded commands (handled by specific handlers)
EXCLUDED_COMMANDS = {
    "start", "help", "menu", "support", "regime", "signals", "today", "tasks", 
    "referral", "referrals", "alerts", "watch", "watchlist", "upgrade", "remove", 
    "removeall", "best", "worst", "news", "trend", "add", "gas", "c", "markets", 
    "links", "set", "portfolio", "pftarget", "pflimit", "myplan", "stats", "conv", 
    "fx", "fxchart", "cod", "funfact", "setplan", "prolist", "calc", "screen", 
    "aiscan", "hmap", "track", "analysis", "levels", "fxsessions", "chart", "bt",
    "backtest", "coins", "compare"
}


async def coin_command_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Route unrecognized commands to coin lookup.
    Filters out known commands to avoid false positives.
    """
    command = update.message.text.strip().lstrip("/").lower()

    # Skip if it's a known command
    if command in EXCLUDED_COMMANDS:
        return

    # Otherwise, treat as potential coin symbol lookup
    await coin_alias_handler(update, context)


# ====== ADMIN DEBUGGING COMMANDS ======

async def collision_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to view collision statistics.
    Usage: /collisions
    """
    from services.coin_data import get_collision_stats
    
    stats = get_collision_stats()
    
    msg = (
        f"📊 *Symbol Collision Statistics*\n\n"
        f"Total Symbols: {stats['total_symbols']:,}\n"
        f"Collisions: {stats['collision_count']:,} "
        f"({stats['collision_percentage']:.1f}%)\n"
        f"Resolved: {stats['resolved_count']:,}\n\n"
        f"*Worst Offenders:*\n"
    )
    
    for symbol, count in stats['worst_collisions']:
        msg += f"• `{symbol.upper()}`: {count} coins\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")


async def clear_collision_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to clear collision cache.
    Usage: /clearcollisions
    """
    from services.coin_data_improved import clear_collision_cache
    
    clear_collision_cache()
    await update.message.reply_text(
        "✅ Collision cache cleared. Fresh resolutions will be fetched on next lookup."
    )
