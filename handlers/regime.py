from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from services.regime_engine import RegimeEngine
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from utils.regime_cache import RegimeCache
import asyncio
import logging
import json
from tasks.handlers import handle_streak

# ============================================================================
# LOGGING SETUP
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# CACHE INITIALIZATION
# ============================================================================

regime_cache = RegimeCache(ttl_minutes=5)

# ============================================================================
# TOP 100 COIN VALIDATION
# ============================================================================

def load_top_100_coins():
    """Load top 100 CoinGecko coins from JSON"""
    try:
        with open("services/top100_coingecko_ids.json", "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("top100_coingecko_ids.json must be a dict")
            return {symbol.upper(): cg_id for symbol, cg_id in data.items()}
    except Exception as e:
        logger.error(f"Error loading top 100 CoinGecko coins: {e}")
        return {}
        
TOP_100_COINS = load_top_100_coins()
        
def validate_coin_symbol(symbol: str) -> bool:
    """Check if coin is in top 100 CoinGecko list"""
    return symbol.upper() in TOP_100_COINS

# ============================================================================
# MAIN COMMAND HANDLER
# ============================================================================

async def regime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initial /regime command handler"""
    
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    plan = get_user_plan(user_id)
    await update_last_active(user_id, command_name="/regime")
    await handle_streak(update, context)
    
    # Parse and validate symbol
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ <b>Usage:</b> <code>/regime &lt;COIN&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/regime BTC</code>\n"
            "• <code>/regime ETH</code>\n"
            "• <code>/regime SOL</code>\n\n"
            "Only top 100 CoinGecko coins supported.",
            parse_mode=ParseMode.HTML
        )
        return
    
    raw_symbol = context.args[0].upper().strip()
    symbol = raw_symbol.replace("USDT", "").replace("USD", "")[:10]
    
    # Validate coin is in top 100
    if not validate_coin_symbol(symbol):
        await update.message.reply_text(
            f"❌ <b>{symbol} is not in the top 100 coins.</b>\n\n"
            f"Regime analysis only supports top 100 CoinGecko coins.\n\n"
            f"<b>Popular coins:</b>\n"
            f"• BTC, ETH, BNB, SOL, XRP\n"
            f"• ADA, DOGE, MATIC, DOT, AVAX",
            parse_mode=ParseMode.HTML
        )
        return
    
    logger.info(f"Regime analysis request: user={user_id} ({username}), symbol={symbol}, plan={plan}")
    
    # ========================================================================
    # SHOW TIMEFRAME SELECTION UI
    # ========================================================================
    
    keyboard = [
        [InlineKeyboardButton("📊 Swing Trading", callback_data=f"regime_swing_{symbol}")],
        [InlineKeyboardButton("⚡ Day Trading", callback_data=f"regime_day_{symbol}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        f"🔍 <b>Market Regime Analysis: {symbol}</b>\n\n"
        f"Choose your trading style:\n\n"
        f"<b>📊 Swing Trading</b> (4H + Daily)\n"
        f"⏰ Holding: 2-7 days\n"
        f"👤 Best for: Part-time traders with jobs\n"
        f"✅ Checks charts 2-3 times per day\n\n"
        f"<b>⚡ Day Trading</b> (1H + 4H)\n"
        f"⏰ Holding: 30 min - 1 day\n"
        f"👤 Best for: Active traders\n"
        f"✅ Multiple trades, no overnight holds"
    )
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# ============================================================================
# BUTTON CALLBACK HANDLER
# ============================================================================

async def regime_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks for timeframe selection"""
    
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    plan = get_user_plan(user_id)
    
    # Parse callback data
    try:
        parts = query.data.split('_')
        if len(parts) != 3 or parts[0] != "regime":
            raise ValueError("Invalid callback data format")
        
        timeframe_type = parts[1]  # "swing" or "day"
        symbol = parts[2]
        
    except Exception as e:
        logger.error(f"Error parsing callback data: {query.data}, error: {e}")
        await query.edit_message_text(
            "❌ <b>Invalid request</b>\n\nPlease run <code>/regime &lt;COIN&gt;</code> again.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # ========================================================================
    # CHECK USER TIER - BLOCK FREE USERS
    # ========================================================================
    
    if not is_pro_plan(plan):
        timeframe_name = "Swing Trading" if timeframe_type == "swing" else "Day Trading"
        
        upgrade_message = (
            f"🔒 <b>Pro Feature Only</b>\n\n"
            f"Market regime analysis is available for <b>Pro users only</b>.\n\n"
            f"<b>What you get with Pro:</b>\n"
            f"✅ Multi-timeframe regime analysis\n"
            f"✅ Risk level assessment\n"
            f"✅ Detailed trading recommendations\n" 
            f"✅ Volume behavior analysis\n"
            f"✅ Strategy rule checks\n\n"
            f"<b>Your choice:</b> {timeframe_name} for {symbol}\n"
            f"<b>Current plan:</b> Free\n\n"
            f"👉 <code>/upgrade</code> to unlock regime analysis"
        )
        
        await query.edit_message_text(upgrade_message, parse_mode=ParseMode.HTML)
        logger.info(f"Free user blocked: user={user_id}, symbol={symbol}, timeframe={timeframe_type}")
        return
    
    # ========================================================================
    # PRO USER - PROCEED WITH ANALYSIS
    # ========================================================================
    
    if timeframe_type == "swing":
        lower_tf = "4h"
        upper_tf = "1day"
        tf_display = "4H + Daily (Swing Trading)"
    elif timeframe_type == "day":
        lower_tf = "1h"
        upper_tf = "4h"
        tf_display = "1H + 4H (Day Trading)"
    else:
        await query.edit_message_text(
            "❌ <b>Invalid timeframe selection</b>\n\nPlease try again.",
            parse_mode=ParseMode.HTML
        )
        return
    
    logger.info(f"Pro user analysis: user={user_id}, symbol={symbol}, timeframes={lower_tf}+{upper_tf}")
    
    # Show loading message
    loading_msg = await query.edit_message_text(
        f"⏳ <b>Analyzing {symbol}</b>\n"
        f"⏰ Timeframes: {tf_display}\n\n"
        f"<i>Fetching market data...</i>",
        parse_mode=ParseMode.HTML
    )
    
    await asyncio.sleep(0.3)
    
    try:
        # ====================================================================
        # TRY CACHE FIRST (FAST PATH)
        # ====================================================================
        
        cache_key = f"{symbol}_{timeframe_type}"
        cached_result = regime_cache.get(cache_key, plan)
        
        if cached_result:
            logger.info(f"Cache hit: user={user_id}, symbol={symbol}, timeframe={timeframe_type}")
            
            await loading_msg.edit_text(
                f"⏳ <b>Analyzing {symbol}</b>\n"
                f"⏰ Timeframes: {tf_display}\n\n",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.2)
            
            cached_result['timeframe_display'] = tf_display
            response = format_regime_response_detailed(cached_result)
            
            cache_age_mins = regime_cache.get_cache_age_minutes(cache_key, plan)
            if cache_age_mins is not None:
                freshness = "very fresh" if cache_age_mins < 1 else f"{int(cache_age_mins)}m old"
                response += f"\n\n<i>📦 Cached data ({freshness})</i>"
            
            await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
            return
        
        # ====================================================================
        # CACHE MISS - FETCH FRESH DATA (SLOW PATH)
        # ====================================================================
        
        logger.info(f"Cache miss: user={user_id}, symbol={symbol}, timeframe={timeframe_type} - fetching fresh")
        
        await loading_msg.edit_text(
            f"⏳ <b>Analyzing {symbol}</b>\n"
            f"⏰ Timeframes: {tf_display}\n\n"
            f"<i>Fetching live market data...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Run analysis
        engine = RegimeEngine()
        result = await engine.analyze(symbol, plan, lower_tf, upper_tf)
        
        result['timeframe_display'] = tf_display
        
        logger.info(f"Analysis complete: user={user_id}, symbol={symbol}, regime={result.get('regime', 'unknown')}")
        
        # Cache the result
        regime_cache.set(cache_key, plan, result)
        
        await loading_msg.edit_text(
            f"⏳ <b>Analyzing {symbol}</b>\n"
            f"⏰ Timeframes: {tf_display}\n\n"
            f"<i>✓ Analysis complete</i>",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(0.2)
        
        # Format and send
        response = format_regime_response_detailed(result)
        response += "\n\n<i>✨ Fresh analysis</i>"
        
        await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(
            f"Regime analysis error: user={user_id}, symbol={symbol}, timeframe={timeframe_type} "
            f"error={type(e).__name__}: {str(e)}",
            exc_info=True
        )
        
        error_msg = format_error_message(str(e), symbol)
        
        try:
            await loading_msg.edit_text(error_msg, parse_mode=ParseMode.HTML)
        except Exception as edit_error:
            logger.error(f"Failed to edit error message: {edit_error}")
            await update.effective_message.reply_text(error_msg, parse_mode=ParseMode.HTML)


# ============================================================================
# RESPONSE FORMATTING (IMPROVED FOR DETAILED POSTURE)
# ============================================================================

def format_regime_response_detailed(result: dict) -> str:
    """Format regime analysis with detailed actionable guidance"""
    
    # Add fallback warning if used
    warning = ""
    if "warning" in result:
        warning = f"⚠️ <i>{result['warning']}</i>\n\n"
    
    timeframe_info = result.get('timeframe_display', '4H + Daily')
    regime_emoji = get_regime_emoji(result['regime'])
    
    # Build response
    response = (
        f"{warning}"
        f"<b>{result['symbol']} Regime Analysis</b>\n"
        f"⏰ {timeframe_info}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{regime_emoji} <b>{result['regime']}</b>\n"
        f"📊 Risk: {result['risk_level']}\n"
        f"🎯 Confidence: {result['confidence']}%\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📋 Trading Recommendation:</b>\n\n"
        f"{result['posture']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    # Add strategy rules
    rules_summary = format_rules_compact(result['strategy_rules'])
    response += f"<b>Strategy Checklist:</b> {rules_summary}\n"
    response += format_rules_detailed(result['strategy_rules'])
    response += "\n\n"
    
    # Add volume
    response += f"<b>Volume:</b> {result['volume_behavior']}"
    
    return response.strip()

    
def get_regime_emoji(regime: str) -> str:
    """Map regime type to appropriate emoji"""
    if "Volatile" in regime:
        return "🔴"
    elif "Steady Bearish" in regime:
        return "🔻"
    elif "Choppy" in regime:
        return "↔️"
    elif "Strong Bullish" in regime:
        return "🚀"
    elif "Bullish" in regime:
        return "📈"
    elif "Bearish" in regime:
        return "📉"
    else:
        return "📊"


def format_rules_compact(rules: dict) -> str:
    """Format strategy rules as compact summary"""
    met_count = sum(1 for status in rules.values() if status)
    total_count = len(rules)
    
    if met_count == total_count:
        indicator = "✅"
    elif met_count >= total_count * 0.66:
        indicator = "✓"
    elif met_count >= total_count * 0.33:
        indicator = "⚠️"
    else:
        indicator = "❌"
    
    return f"{met_count}/{total_count} {indicator}"


def format_rules_detailed(rules: dict) -> str:
    """Format individual rule statuses"""
    rule_lines = []
    for rule_name, status in rules.items():
        emoji = "✓" if status else "✗"
        rule_lines.append(f"  {emoji} {rule_name}")
    
    return "\n".join(rule_lines)


# ============================================================================
# ERROR HANDLING
# ============================================================================

def format_error_message(error: str, symbol: str) -> str:
    """Format clear, actionable error messages"""
    error_lower = error.lower()
    
    if any(x in error_lower for x in ["network", "timeout", "connection"]):
        return (
            "❌ <b>Connection Issue</b>\n\n"
            "Couldn't reach the market data provider right now.\n\n"
            "<b>What to try:</b>\n"
            "• Wait 30 seconds and try again\n"
            "• Check your internet connection\n"
            "• Try a different symbol: <code>/regime ETH</code>\n\n"
            "<i>If this keeps happening, the data provider may be temporarily down.</i>"
        )
    
    if any(x in error_lower for x in ["rate limit", "429", "quota", "credits"]):
        return (
            "⏱️ <b>Slow Down There!</b>\n\n"
            "We've hit our data request limit temporarily.\n\n"
            "<b>Please wait 2-3 minutes</b> and try again.\n\n"
            "💡 <b>Pro tip:</b> Results are cached for 5 minutes.\n\n"
            "<i>This protects our data costs and keeps the service running smoothly.</i>"
        )
    
    if any(x in error_lower for x in ["invalid symbol", "symbol", "not found", "404"]):
        return (
            f"❌ <b>Symbol Not Found: {symbol}</b>\n\n"
            f"We couldn't find market data for <b>{symbol}</b>.\n\n"
            f"<b>Try these popular coins:</b>\n"
            f"• <code>/regime BTC</code>\n"
            f"• <code>/regime ETH</code>\n"
            f"• <code>/regime SOL</code>\n\n"
            f"<b>Tips:</b>\n"
            f"• Use base symbol only (BTC, not BTCUSDT)\n"
            f"• Only top 100 CoinGecko coins supported\n\n"
            f"<i>See /help for full command list</i>"
        )
    
    # Generic fallback
    return (
        f"❌ <b>Analysis Failed</b>\n\n"
        f"We couldn't complete the analysis for <b>{symbol}</b> right now.\n\n"
        f"<b>Quick fixes to try:</b>\n"
        f"1. Wait a minute and try again\n"
        f"2. Try a different symbol: <code>/regime BTC</code>\n"
        f"3. Check if the symbol is correct\n\n"
        f"<b>Still not working?</b>\n"
        f"Contact support: /support\n\n"
        f"<i>We're here to help!</i>"
    )
