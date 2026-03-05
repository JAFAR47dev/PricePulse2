# handlers/movers.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from services.movers_service import MoversService
from models.user_activity import update_last_active
from tasks.handlers import handle_streak
import logging

logger = logging.getLogger(__name__)

movers_service = MoversService()

async def movers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /movers - Show top pumps and dumps in last 1 hour
    
    FREE command for everyone, perfect for groups.
    Shows real-time price movements of top 100 CoinGecko coins.
    
    Usage:
    /movers        - Default (1 hour timeframe)
    /movers 24h    - 24 hour movements
    """
    
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/movers")
    await handle_streak(update, context)
    
    # Parse timeframe argument
    timeframe = "1h"  # Default
    if context.args and len(context.args) > 0:
        arg = context.args[0].lower()
        if arg in ["1h", "24h"]:
            timeframe = arg
    
    # Show loading message
    loading_msg = await update.message.reply_text(
        "🔄 **Checking what's moving right now...**\n\n"
        "⏱️ Scanning top 100 coins...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Fetch movers data
        movers_data = await movers_service.get_top_movers(timeframe=timeframe)
        
        if not movers_data:
            await loading_msg.edit_text(
                "❌ **Failed to load movers**\n\n"
                "CoinGecko API may be temporarily unavailable.\n"
                "Please try again in a moment.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Format message
        message = format_movers_message(movers_data, timeframe)
        
        # Create interactive buttons
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"movers_refresh_{timeframe}"),
                InlineKeyboardButton("📊 Switch View", callback_data=f"movers_switch_{timeframe}")
            ],
            [
                InlineKeyboardButton("📈 Best", callback_data="movers_best"),
                InlineKeyboardButton("📉 Worst", callback_data="movers_worst")
            ]
        ]
        
        # Send result
        await loading_msg.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        logger.info(f"Movers displayed: {timeframe} for user {user_id}")
        
    except Exception as e:
        logger.exception(f"Error in /movers command")
        
        await loading_msg.edit_text(
            "❌ **Movers Error**\n\n"
            "Something went wrong while fetching data.\n"
            "Please try again in a moment.",
            parse_mode=ParseMode.MARKDOWN
        )


def format_movers_message(movers_data: dict, timeframe: str) -> str:
    """Format the movers data into user-friendly message"""
    
    pumping = movers_data['pumping']  # Top 5 gainers
    dumping = movers_data['dumping']  # Top 5 losers
    market_summary = movers_data['market_summary']
    timestamp = movers_data['timestamp']
    
    # Timeframe display
    tf_display = "1 Hour" if timeframe == "1h" else "24 Hours"
    
    # Build message
    message = (
        f"🚀 **Top Movers** (Last {tf_display})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    # ═══════════════════════════════════════════════════════════════
    # PUMPING SECTION
    # ═══════════════════════════════════════════════════════════════
    
    if pumping:
        message += f"🔥 **PUMPING:**\n"
        
        for i, coin in enumerate(pumping, 1):
            symbol = coin['symbol']
            name = coin['name']
            change = coin['price_change_percentage']
            price = coin['current_price']
            volume_change = coin.get('volume_change', 0)
            
            # Emoji based on change magnitude
            if change >= 10:
                emoji = "🚀"
            elif change >= 5:
                emoji = "📈"
            else:
                emoji = "⬆️"
            
            # Volume indicator
            vol_indicator = ""
            if volume_change > 100:
                vol_indicator = " 🔊"  # High volume
            elif volume_change > 50:
                vol_indicator = " 📢"  # Medium volume
            
            message += (
                f"{i}. **{symbol}** {emoji} `+{change:.1f}%`{vol_indicator}\n"
                f"   {name} • ${price:,.4f}\n"
            )
        
        message += "\n"
    else:
        message += f"🔥 **PUMPING:**\nNo significant pumps\n\n"
    
    # ═══════════════════════════════════════════════════════════════
    # DUMPING SECTION
    # ═══════════════════════════════════════════════════════════════
    
    if dumping:
        message += f"❄️ **DUMPING:**\n"
        
        for i, coin in enumerate(dumping, 1):
            symbol = coin['symbol']
            name = coin['name']
            change = coin['price_change_percentage']
            price = coin['current_price']
            volume_change = coin.get('volume_change', 0)
            
            # Emoji based on change magnitude
            if change <= -10:
                emoji = "💥"
            elif change <= -5:
                emoji = "📉"
            else:
                emoji = "⬇️"
            
            # Volume indicator
            vol_indicator = ""
            if volume_change > 100:
                vol_indicator = " 🔊"
            
            message += (
                f"{i}. **{symbol}** {emoji} `{change:.1f}%`{vol_indicator}\n"
                f"   {name} • ${price:,.4f}\n"
            )
        
        message += "\n"
    else:
        message += f"❄️ **DUMPING:**\nNo significant dumps\n\n"
    
    # ═══════════════════════════════════════════════════════════════
    # MARKET SUMMARY
    # ═══════════════════════════════════════════════════════════════
    
    message += (
        f"📊 **Market Summary:**\n"
        f"• Gainers: {market_summary['gainers']} coins\n"
        f"• Losers: {market_summary['losers']} coins\n"
        f"• Neutral: {market_summary['neutral']} coins\n"
        f"• Total scanned: {market_summary['total']} coins\n\n"
    )
    
    # Market mood emoji
    if market_summary['gainers'] > market_summary['losers'] * 2:
        mood = "🟢 Bullish"
    elif market_summary['losers'] > market_summary['gainers'] * 2:
        mood = "🔴 Bearish"
    else:
        mood = "🟡 Mixed"
    
    message += f"**Market Mood:** {mood}\n\n"
    
    
    return message


# ============================================================================
# CALLBACK HANDLERS
# ============================================================================

async def movers_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh button"""
    query = update.callback_query
    
    try:
        await query.answer("🔄 Refreshing...", show_alert=False)
        
        # Extract timeframe from callback data
        timeframe = query.data.replace("movers_refresh_", "")
        
        # Show loading
        await query.edit_message_text(
            "🔄 **Refreshing movers...**\n\n"
            "⏱️ Fetching latest data...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Fetch fresh data
        movers_data = await movers_service.get_top_movers(timeframe=timeframe)
        
        if not movers_data:
            await query.edit_message_text(
                "❌ Refresh failed. Try `/movers` again.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Format message
        message = format_movers_message(movers_data, timeframe)
        
        # Recreate buttons
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"movers_refresh_{timeframe}"),
                InlineKeyboardButton("📊 Switch View", callback_data=f"movers_switch_{timeframe}")
            ],
            [
                InlineKeyboardButton("📈 Best", callback_data="movers_best"),
                InlineKeyboardButton("📉 Worst", callback_data="movers_worst")
            ]
        ]
        
        # Update message
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        logger.info(f"Movers refreshed: {timeframe}")
        
    except Exception as e:
        logger.exception("Movers refresh callback error")
        await query.edit_message_text(
            "❌ Refresh failed. Try `/movers`",
            parse_mode=ParseMode.MARKDOWN
        )


async def movers_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle switch view button (1h ↔ 24h)"""
    query = update.callback_query
    
    try:
        await query.answer("🔄 Switching view...", show_alert=False)
        
        # Get current timeframe and switch it
        current_tf = query.data.replace("movers_switch_", "")
        new_tf = "24h" if current_tf == "1h" else "1h"
        
        # Show loading
        await query.edit_message_text(
            f"🔄 **Loading {new_tf} view...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Fetch data with new timeframe
        movers_data = await movers_service.get_top_movers(timeframe=new_tf)
        
        if not movers_data:
            await query.edit_message_text(
                "❌ Failed to load. Try `/movers`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Format message
        message = format_movers_message(movers_data, new_tf)
        
        # Update buttons with new timeframe
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"movers_refresh_{new_tf}"),
                InlineKeyboardButton("📊 Switch View", callback_data=f"movers_switch_{new_tf}")
            ],
            [
                InlineKeyboardButton("📈 Best", callback_data="movers_best"),
                InlineKeyboardButton("📉 Worst", callback_data="movers_worst")
            ]
        ]
        
        # Update message
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.exception("Movers switch callback error")
        await query.answer("❌ Switch failed", show_alert=True)


async def movers_best_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick link to /best command"""
    query = update.callback_query
    
    message = (
        "📈 Top Gainers (24h)\n\n"
        "Use: `/best`\n\n"
        "Shows top 3 gainers"
    )
    
    await query.answer(message, show_alert=True)


async def movers_worst_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick link to /worst command"""
    query = update.callback_query
    
    message = (
        "📉 Top Losers (24h)\n\n"
        "Use: `/worst`\n\n"
        "Shows top 3 losers"
    )
    
    await query.answer(message, show_alert=True)


# ============================================================================
# REGISTER HANDLERS
# ============================================================================

def register_movers_handlers(app):
    """Register movers command and callbacks"""
    from telegram.ext import CommandHandler, CallbackQueryHandler
    
    app.add_handler(CommandHandler("movers", movers_command))
    app.add_handler(CallbackQueryHandler(movers_refresh_callback, pattern="^movers_refresh_"))
    app.add_handler(CallbackQueryHandler(movers_switch_callback, pattern="^movers_switch_"))
    app.add_handler(CallbackQueryHandler(movers_best_callback, pattern="^movers_best$"))
    app.add_handler(CallbackQueryHandler(movers_worst_callback, pattern="^movers_worst$"))
    