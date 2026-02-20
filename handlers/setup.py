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


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setup [SYMBOL] [TIMEFRAME] - Professional trade setup analyzer
    
    Analyzes market conditions using institutional-grade methodology:
    - Unbiased bullish/bearish scoring
    - Multi-timeframe trend context
    - Professional risk assessment
    - Key support/resistance levels
    - Trading confidence metrics
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/setup")
    await handle_streak(update, context)
    
    # Check Pro status
    plan = get_user_plan(user_id)
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 **Pro Feature: Trade Setup Analyzer**\n\n"
            "Get professional-grade trade analysis:\n\n"
            "✅ Unbiased setup scoring (0-100)\n"
            "✅ Trading confidence metrics\n"
            "✅ Multi-timeframe trend context\n"
            "✅ Professional entry/exit zones\n"
            "✅ Risk-reward optimization\n"
            "✅ Support/resistance levels\n"
            "✅ Chart pattern detection\n\n"
            "💎 Upgrade to Pro: /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Parse arguments
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ **Usage:** `/setup [SYMBOL] [TIMEFRAME]`\n\n"
            "**Examples:**\n"
            "`/setup BTC 4h` — Bitcoin 4-hour analysis\n"
            "`/setup ETH 1h` — Ethereum 1-hour analysis\n"
            "`/setup SOL 15m` — Solana 15-minute analysis\n\n"
            "**Valid timeframes:**\n"
            "`5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `1d`\n\n"
            f"**Supported:** Top 100 CoinGecko coins\n"
            f"_(Currently {len(SUPPORTED_COINS)} coins available)_",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    symbol = context.args[0].upper().strip()
    timeframe = context.args[1].lower().strip() if len(context.args) >= 2 else "4h"
    
    # Validate symbol
    if symbol not in SUPPORTED_COINS:
        await update.message.reply_text(
            f"❌ **{symbol} not supported**\n\n"
            f"Only top 100 CoinGecko coins are supported.\n\n"
            f"**Popular coins:**\n"
            f"• Layer 1: BTC, ETH, SOL, BNB, ADA, AVAX, DOT\n"
            f"• DeFi: UNI, AAVE, LINK, SUSHI, CRV, MKR\n"
            f"• Layer 2: MATIC, ARB, OP\n"
            f"• Memes: DOGE, SHIB, PEPE, WIF\n\n"
            f"_Currently supporting {len(SUPPORTED_COINS)} coins_",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Validate timeframe
    if timeframe not in VALID_TIMEFRAMES:
        await update.message.reply_text(
            f"❌ Invalid timeframe: `{timeframe}`\n\n"
            f"**Valid options:**\n"
            f"• Scalping: `5m`, `15m`, `30m`\n"
            f"• Intraday: `1h`, `2h`\n"
            f"• Swing: `4h`, `8h`\n"
            f"• Position: `1d`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Show loading message
    loading_msg = await update.message.reply_text(
        f"🔄 **Analyzing {symbol} on {timeframe} timeframe**\n\n"
        f"• Fetching market data from CoinGecko\n"
        f"• Calculating 17+ technical indicators\n"
        f"• Detecting support/resistance levels\n"
        f"• Analyzing chart patterns\n"
        f"• Scoring setup quality\n\n"
        f"⏱️ This takes 5-10 seconds...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # ═══════════════════════════════════════════════════════════════
        # ANALYZE SETUP
        # ═══════════════════════════════════════════════════════════════
        
        setup_data = await setup_analyzer.analyze_setup(symbol, timeframe)
        
        if not setup_data:
            await loading_msg.edit_text(
                f"❌ **Analysis Failed for {symbol}**\n\n"
                f"Possible reasons:\n"
                f"• Insufficient historical data on {timeframe}\n"
                f"• CoinGecko API temporary error\n"
                f"• Network connectivity issue\n\n"
                f"**Try:**\n"
                f"• Different timeframe (e.g., `/setup {symbol} 4h`)\n"
                f"• Wait a moment and try again\n"
                f"• Check symbol spelling",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # ═══════════════════════════════════════════════════════════════
        # GET HISTORICAL PERFORMANCE
        # ═══════════════════════════════════════════════════════════════
        
        performance = await performance_tracker.get_similar_setups(
            symbol, 
            timeframe, 
            setup_data['score']
        )
        
        # ═══════════════════════════════════════════════════════════════
        # FORMAT MESSAGE
        # ═══════════════════════════════════════════════════════════════
        
        message = format_setup_message(setup_data, performance, symbol, timeframe)
        
        # ═══════════════════════════════════════════════════════════════
        # STORE SETUP DATA (IMPROVED - Use unique setup_id)
        # ═══════════════════════════════════════════════════════════════
        
        setup_id = f"{symbol}_{timeframe}"
        context.user_data[f'setup_{setup_id}'] = setup_data
        
        # ═══════════════════════════════════════════════════════════════
        # CREATE INTERACTIVE BUTTONS (IMPROVED)
        # ═══════════════════════════════════════════════════════════════
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "🔔 Set Entry Alert", 
                    callback_data=f"setup_alert_{setup_id}"  # Pass setup_id, not price
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 View Charts", 
                    callback_data=f"setup_charts_{setup_id}"
                ),
                InlineKeyboardButton(
                    "🔄 Refresh", 
                    callback_data=f"setup_refresh_{setup_id}"
                )
            ]
        ]
        
        # ═══════════════════════════════════════════════════════════════
        # SEND RESULT
        # ═══════════════════════════════════════════════════════════════
        
        await loading_msg.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        logger.info(f"Setup analysis completed: {symbol} {timeframe} (score: {setup_data['score']})")
        
    except Exception as e:
        logger.exception(f"Error in /setup command for {symbol} {timeframe}")
        
        await loading_msg.edit_text(
            f"❌ **Setup Analysis Error**\n\n"
            f"An unexpected error occurred while analyzing {symbol}.\n\n"
            f"**This could be due to:**\n"
            f"• CoinGecko API rate limiting\n"
            f"• Temporary network issues\n"
            f"• Insufficient market data\n\n"
            f"Please wait 30-60 seconds and try again.\n"
            f"If the issue persists, try:\n"
            f"• Different timeframe\n"
            f"• Different symbol\n"
            f"• Contact support: /support",
            parse_mode=ParseMode.MARKDOWN
        )


def format_setup_message(setup_data: dict, performance: dict, symbol: str, timeframe: str) -> str:
    """Format the professional setup analysis into user-friendly message"""
    
    score = setup_data['score']
    quality = setup_data['quality']
    confidence = setup_data.get('confidence', 50)
    direction = setup_data['direction']
    current_price = setup_data['current_price']
    trend_context = setup_data.get('trend_context', 'RANGING')
    
    # Quality emoji (progressive scale)
    if score >= 75:
        quality_emoji = '🟢'
    elif score >= 65:
        quality_emoji = '🟢'
    elif score >= 55:
        quality_emoji = '🟡'
    elif score >= 45:
        quality_emoji = '⚪'
    elif score >= 35:
        quality_emoji = '🟠'
    else:
        quality_emoji = '🔴'
    
    # Direction emoji
    direction_emoji = '📈' if direction == 'BULLISH' else '📉' if direction == 'BEARISH' else '↔️'
    
    # Confidence emoji
    if confidence >= 75:
        conf_emoji = '🟢'
    elif confidence >= 60:
        conf_emoji = '🟡'
    else:
        conf_emoji = '🔴'
    
    # Build message header
    message = (
        f"🎯 **Professional Setup Analysis**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"📊 **{symbol}/USDT** ({timeframe} timeframe)\n"
        f"Current Price: `${current_price:,.2f}`\n\n"
        
        f"{quality_emoji} **Setup Score: {score}/100** ({quality})\n"
        f"{conf_emoji} **Confidence: {confidence}%**\n"
        f"{direction_emoji} **Direction: {direction}**\n"
        f"📐 **Trend Context: {trend_context}**\n\n"
    )
    
    # ═══════════════════════════════════════════════════════════════
    # KEY LEVELS
    # ═══════════════════════════════════════════════════════════════
    
    support_levels = setup_data.get('support_levels', [])
    resistance_levels = setup_data.get('resistance_levels', [])
    
    if support_levels or resistance_levels:
        message += f"📍 **Key Levels:**\n"
        
        if resistance_levels:
            r = resistance_levels[0]
            distance = ((r['price'] - current_price) / current_price) * 100
            strength_emoji = "🔴" if r['strength'] == "Strong" else "🟡" if r['strength'] == "Medium" else "⚪"
            message += (
                f"   ↑ Resistance {strength_emoji}: `${r['price']:,.2f}` "
                f"(+{distance:.1f}%, {r['touches']} touches)\n"
            )
        
        if support_levels:
            s = support_levels[0]
            distance = ((current_price - s['price']) / current_price) * 100
            strength_emoji = "🔴" if s['strength'] == "Strong" else "🟡" if s['strength'] == "Medium" else "⚪"
            message += (
                f"   ↓ Support {strength_emoji}: `${s['price']:,.2f}` "
                f"(-{distance:.1f}%, {s['touches']} touches)\n"
            )
        
        message += "\n"
    
    # ═══════════════════════════════════════════════════════════════
    # BULLISH SIGNALS
    # ═══════════════════════════════════════════════════════════════
    
    bullish_signals = setup_data.get('bullish_signals', [])
    if bullish_signals:
        message += f"✅ **Bullish Signals ({len(bullish_signals)}):**\n"
        for signal in bullish_signals[:6]:  # Top 6
            message += f"   • {signal}\n"
        message += "\n"
    
    # ═══════════════════════════════════════════════════════════════
    # BEARISH SIGNALS
    # ═══════════════════════════════════════════════════════════════
    
    bearish_signals = setup_data.get('bearish_signals', [])
    if bearish_signals:
        message += f"❌ **Bearish Signals ({len(bearish_signals)}):**\n"
        for signal in bearish_signals[:6]:  # Top 6
            message += f"   • {signal}\n"
        message += "\n"
    
    # ═══════════════════════════════════════════════════════════════
    # RISK FACTORS
    # ═══════════════════════════════════════════════════════════════
    
    risk_factors = setup_data.get('risk_factors', [])
    if risk_factors:
        message += f"⚠️ **Risk Factors ({len(risk_factors)}):**\n"
        for risk in risk_factors[:4]:  # Top 4
            message += f"   • {risk}\n"
        message += "\n"
    
    # ═══════════════════════════════════════════════════════════════
    # TRADE SETUP (Only if score >= 55 AND confidence >= 60)
    # ═══════════════════════════════════════════════════════════════
    
    if score >= 55 and confidence >= 60:
        entry_low, entry_high = setup_data['entry_zone']
        stop_loss = setup_data['stop_loss']
        tp1 = setup_data['take_profit_1']
        tp2 = setup_data['take_profit_2']
        rr_ratio = setup_data['risk_reward']
        
        stop_distance = abs((current_price - stop_loss) / current_price * 100)
        tp1_gain = abs((tp1 - current_price) / current_price * 100)
        tp2_gain = abs((tp2 - current_price) / current_price * 100)
        
        message += (
            f"💰 **Trade Setup** (IF conditions met):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Entry Zone: `${entry_low:,.2f} - ${entry_high:,.2f}`\n"
            f"Stop Loss: `${stop_loss:,.2f}` ({stop_distance:.1f}%)\n"
            f"Take Profit 1: `${tp1:,.2f}` ({tp1_gain:.1f}%)\n"
            f"Take Profit 2: `${tp2:,.2f}` ({tp2_gain:.1f}%)\n\n"
            f"Risk:Reward: **1:{rr_ratio:.1f}** "
            f"{'✅' if rr_ratio >= 2.5 else '🟡' if rr_ratio >= 2.0 else '🟠'}\n\n"
        )
        
        # Level-based plan
        message += f"📐 **Level-Based Plan:**\n"
        
        if direction == "BULLISH" and support_levels:
            nearest_support = support_levels[0]
            message += f"   • Stop below support (${nearest_support['price']:,.2f})\n"
            
            if resistance_levels:
                nearest_resistance = resistance_levels[0]
                message += f"   • TP1 before resistance (${nearest_resistance['price']:,.2f})\n"
        
        elif direction == "BEARISH" and resistance_levels:
            nearest_resistance = resistance_levels[0]
            message += f"   • Stop above resistance (${nearest_resistance['price']:,.2f})\n"
            
            if support_levels:
                nearest_support = support_levels[0]
                message += f"   • TP1 after support (${nearest_support['price']:,.2f})\n"
        
        message += "\n"
        
        # Position sizing
        message += (
            f"📏 **Position Sizing:**\n"
            f"Use: `/risk [account] [risk_%] {current_price:.0f} {stop_loss:.0f}`\n"
            f"Example: `/risk 10000 2 {current_price:.0f} {stop_loss:.0f}`\n\n"
        )
        
    else:
        message += (
            f"🚫 **Trade Setup: NOT RECOMMENDED**\n"
            f"• Score: {score}/100 (need 55+)\n"
            f"• Confidence: {confidence}% (need 60%+)\n\n"
            f"⏰ **Wait for:**\n"
            f"   • Higher quality setup\n"
            f"   • Clear trend confirmation\n"
            f"   • Better risk:reward opportunity\n\n"
        )
    
    # ═══════════════════════════════════════════════════════════════
    # WAIT CONDITIONS
    # ═══════════════════════════════════════════════════════════════
    
    wait_conditions = setup_data.get('wait_for', [])
    if wait_conditions and score >= 55:
        message += f"⏰ **Entry Conditions:**\n"
        for condition in wait_conditions[:4]:
            message += f"   • {condition}\n"
        message += "\n"
    
    # ═══════════════════════════════════════════════════════════════
    # PATTERNS
    # ═══════════════════════════════════════════════════════════════
    
    patterns = setup_data.get('patterns', [])
    if patterns:
        message += f"📊 **Chart Patterns ({len(patterns)}):**\n"
        for pattern in patterns[:3]:
            message += f"   • {pattern}\n"
        message += "\n"
    
    # ═══════════════════════════════════════════════════════════════
    # HISTORICAL PERFORMANCE
    # ═══════════════════════════════════════════════════════════════
    
    if performance:
        win_rate = performance['win_rate']
        expectancy = performance['expectancy']
        total = performance['total_setups']
        
        perf_emoji = '🟢' if win_rate >= 65 else '🟡' if win_rate >= 55 else '🟠'
        
        message += (
            f"📈 **Historical Performance**\n"
            f"{perf_emoji} Similar setups: **{win_rate:.1f}%** win rate ({total} trades)\n"
            f"   • Avg winner: +{performance['avg_win']:.1f}%\n"
            f"   • Avg loser: {performance['avg_loss']:.1f}%\n"
            f"   • Expectancy: **{expectancy:+.2f}%**\n\n"
        )
    
    # ═══════════════════════════════════════════════════════════════
    # DISCLAIMER
    # ═══════════════════════════════════════════════════════════════
    
    message += (
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ **CRITICAL DISCLAIMER:**\n\n"
        f"This analysis is for educational purposes only.\n"
        f"**NOT financial advice.**\n\n"
        f"• Always do your own research (DYOR)\n"
        f"• Never risk more than you can afford to lose\n"
        f"• Past performance ≠ future results\n"
        f"• Use proper risk management\n"
        f"• Always use stop losses\n\n"
        f"💡 Use buttons below for alerts & charts"
    )
    
    return message




# ============================================================================
# CALLBACK HANDLERS (FIXED - Message Too Long)
# ============================================================================

async def setup_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle set alert button - FIXED VERSION (respects 200 char limit)"""
    query = update.callback_query
    
    try:
        # Get setup ID from callback data
        setup_id = query.data.replace("setup_alert_", "")  # e.g., "BTC_4h"
        
        # Retrieve stored setup data
        setup_data = context.user_data.get(f'setup_{setup_id}')
        
        if not setup_data:
            await query.answer(
                "❌ Setup expired. Run /setup again.",
                show_alert=True
            )
            return
        
        # Extract info
        parts = setup_id.split("_")
        symbol = parts[0]
        timeframe = parts[1] if len(parts) > 1 else "4h"
        
        entry_low, entry_high = setup_data['entry_zone']
        current_price = setup_data['current_price']
        direction = setup_data.get('direction', 'NEUTRAL')
        
        # ═══════════════════════════════════════════════════════════════
        # BUILD COMPACT ALERT MESSAGE (Under 200 chars)
        # ═══════════════════════════════════════════════════════════════
        
        if direction == "BULLISH":
            recommended_price = entry_low
            direction_word = "above"
        elif direction == "BEARISH":
            recommended_price = entry_high
            direction_word = "below"
        else:
            recommended_price = current_price
            direction_word = "above"
        
        # Compact message under 200 characters
        message = (
            f"🔔 Alert for {symbol}\n\n"
            f"Use: /set {symbol} {direction_word} {recommended_price:.2f}\n\n"
            f"Current: ${current_price:,.2f}\n"
            f"Entry: ${entry_low:,.2f}-${entry_high:,.2f}"
        )
        
        # Telegram alert messages must be under 200 characters
        if len(message) > 190:  # Leave buffer for safety
            # Even more compact version
            message = (
                f"🔔 {symbol} Alert\n\n"
                f"/set {symbol} {direction_word} {recommended_price:.0f}\n\n"
                f"Entry: ${entry_low:.0f}-${entry_high:.0f}"
            )
        
        await query.answer(message, show_alert=True)
        
        logger.info(f"Alert button clicked: {symbol} {timeframe}")
        
    except Exception as e:
        logger.exception(f"Setup alert callback error")
        
        # Fallback error message (also under 200 chars)
        await query.answer(
            "❌ Alert failed\n\n"
            "Use: /set [SYMBOL] above [PRICE]\n"
            "Example: /set BTC above 95000",
            show_alert=True
        )


async def setup_charts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle view charts button"""
    query = update.callback_query
    
    try:
        setup_id = query.data.replace("setup_charts_", "")
        parts = setup_id.split("_")
        symbol = parts[0]
        timeframe = parts[1] if len(parts) > 1 else "4h"
        
        # Compact message under 200 chars
        message = (
            f"📊 {symbol} Chart\n\n"
            f"Use: /c {symbol} {timeframe}\n\n"
            f"Shows TradingView chart with levels marked"
        )
        
        await query.answer(message, show_alert=True)
        
    except Exception as e:
        logger.exception("Setup charts callback error")
        await query.answer("❌ Chart view failed", show_alert=True)


async def setup_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh button"""
    query = update.callback_query
    
    try:
        # Don't use show_alert=True for refresh (just a quick notification)
        await query.answer("🔄 Refreshing...", show_alert=False)
        
        setup_id = query.data.replace("setup_refresh_", "")
        parts = setup_id.split("_")
        symbol = parts[0]
        timeframe = parts[1] if len(parts) > 1 else "4h"
        
        # Show loading in message
        await query.edit_message_text(
            f"🔄 Refreshing {symbol} {timeframe}...\n\n"
            f"⏱️ Please wait 5-10 seconds...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Re-analyze
        setup_data = await setup_analyzer.analyze_setup(symbol, timeframe)
        
        if not setup_data:
            await query.edit_message_text(
                f"❌ Refresh failed for {symbol}.\n\n"
                f"Try: `/setup {symbol} {timeframe}`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Get performance
        performance = await performance_tracker.get_similar_setups(
            symbol, timeframe, setup_data['score']
        )
        
        # Format message
        message = format_setup_message(setup_data, performance, symbol, timeframe)
        
        # Store fresh data
        context.user_data[f'setup_{setup_id}'] = setup_data
        
        # Recreate buttons
        keyboard = [
            [
                InlineKeyboardButton(
                    "🔔 Set Entry Alert", 
                    callback_data=f"setup_alert_{setup_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 View Charts", 
                    callback_data=f"setup_charts_{setup_id}"
                ),
                InlineKeyboardButton(
                    "🔄 Refresh", 
                    callback_data=f"setup_refresh_{setup_id}"
                )
            ]
        ]
        
        # Update message
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        logger.info(f"Setup refreshed: {symbol} {timeframe}")
        
    except Exception as e:
        logger.exception("Setup refresh callback error")
        await query.edit_message_text(
            "❌ Refresh failed. Try `/setup [SYMBOL] [TIMEFRAME]`",
            parse_mode=ParseMode.MARKDOWN
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
