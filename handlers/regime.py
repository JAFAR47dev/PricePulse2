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

# ============================================================================
# LOGGING SETUP
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# CACHE INITIALIZATION
# ============================================================================

# Initialize cache with 5-minute TTL (configurable)
regime_cache = RegimeCache(ttl_minutes=5)

# ============================================================================
# TOP 100 COIN VALIDATION
# ============================================================================

import json
import logging

logger = logging.getLogger(__name__)

def load_top_100_coins():
    """
    Load top 100 CoinGecko coins from JSON.
    Returns:
        dict: {SYMBOL: coingecko_id}
    """
    try:
        with open("services/top100_coingecko_ids.json", "r") as f:
            data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("top100_coingecko_ids.json must be a dict")

            # Normalize symbols to uppercase
            coins = {symbol.upper(): cg_id for symbol, cg_id in data.items()}

            return coins

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
    """
    Initial /regime command handler
    Shows timeframe selection UI with educational content
    """
    
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    plan = get_user_plan(user_id)
    await update_last_active(user_id, command_name="/regime")
    
    # Parse and validate symbol
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ **Usage:** `/regime <COIN>`\n\n"
            "**Examples:**\n"
            "• `/regime BTC`\n"
            "• `/regime ETH`\n"
            "• `/regime SOL`\n\n"
            "Only top 100 CoinGecko coins supported.\n"
            "Use `/coins` to see the full list.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    raw_symbol = context.args[0].upper().strip()
    # Clean symbol (remove common suffixes)
    symbol = raw_symbol.replace("USDT", "").replace("USD", "")[:10]
    
    # Validate coin is in top 100
    if not validate_coin_symbol(symbol):
        await update.message.reply_text(
            f"❌ **{symbol} is not in the top 100 coins.**\n\n"
            f"Regime analysis only supports top 100 CoinGecko coins.\n\n"
            f"**Popular coins:**\n"
            f"• BTC, ETH, BNB, SOL, XRP\n"
            f"• ADA, DOGE, MATIC, DOT, AVAX\n\n"
            f"Use `/coins` to see the full list.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Log request
    logger.info(f"Regime analysis request: user={user_id} ({username}), symbol={symbol}, plan={plan}")
    
    # ========================================================================
    # SHOW TIMEFRAME SELECTION UI
    # ========================================================================
    
    # Create inline keyboard buttons
    keyboard = [
        [InlineKeyboardButton("📊 Swing Trading", callback_data=f"regime_swing_{symbol}")],
        [InlineKeyboardButton("⚡ Day Trading", callback_data=f"regime_day_{symbol}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send selection message with educational content
    message = (
        f"🔍 **Market Regime Analysis: {symbol}**\n\n"
        f"Choose your trading style:\n\n"
        f"**📊 Swing Trading** (4H + Daily)\n"
        f"⏰ Holding: 2-7 days\n"
        f"👤 Best for: Part-time traders with jobs\n"
        f"✅ Checks charts 2-3 times per day\n\n"
        f"**⚡ Day Trading** (1H + 4H)\n"
        f"⏰ Holding: 30 min - 1 day\n"
        f"👤 Best for: Active traders\n"
        f"✅ Multiple trades, no overnight holds"
    )
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ============================================================================
# BUTTON CALLBACK HANDLER
# ============================================================================

async def regime_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle button clicks for timeframe selection
    Checks user tier and triggers analysis for Pro users
    """
    
    query = update.callback_query
    await query.answer()  # Acknowledge button click
    
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    plan = get_user_plan(user_id)
    
    # Parse callback data: "regime_swing_BTC" or "regime_day_ETH"
    try:
        parts = query.data.split('_')
        if len(parts) != 3 or parts[0] != "regime":
            raise ValueError("Invalid callback data format")
        
        action = parts[0]
        timeframe_type = parts[1]  # "swing" or "day"
        symbol = parts[2]
        
    except Exception as e:
        logger.error(f"Error parsing callback data: {query.data}, error: {e}")
        await query.edit_message_text(
            "❌ **Invalid request**\n\nPlease run `/regime <COIN>` again.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # ========================================================================
    # CHECK USER TIER - BLOCK FREE USERS
    # ========================================================================
    
    if not is_pro_plan(plan):
        # Show upgrade message for free users
        timeframe_name = "Swing Trading" if timeframe_type == "swing" else "Day Trading"
        
        upgrade_message = (
            f"🔒 **Pro Feature Only**\n\n"
            f"Market regime analysis is available for **Pro users only**.\n\n"
            f"**What you get with Pro:**\n"
            f"✅ Multi-timeframe regime analysis\n"
            f"✅ Risk level assessment\n"
            f"✅ Trading posture recommendations\n"
            f"✅ Support/Resistance levels\n"
            f"✅ Volume behavior analysis\n"
            f"✅ Strategy rule checks\n\n"
            f"**Your choice:** {timeframe_name} for {symbol}\n"
            f"**Current plan:** Free\n\n"
            f"👉 `/upgrade` to unlock regime analysis"
        )
        
        await query.edit_message_text(
            upgrade_message,
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"Free user blocked: user={user_id}, symbol={symbol}, timeframe={timeframe_type}")
        return
    
    # ========================================================================
    # PRO USER - PROCEED WITH ANALYSIS
    # ========================================================================
    
    # Map timeframe type to actual timeframes
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
            "❌ **Invalid timeframe selection**\n\nPlease try again.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    logger.info(f"Pro user analysis: user={user_id}, symbol={symbol}, timeframes={lower_tf}+{upper_tf}")
    
    # Show loading message
    loading_msg = await query.edit_message_text(
        f"⏳ **Analyzing {symbol}**\n"
        f"⏰ Timeframes: {tf_display}\n\n"
        f"_Fetching market data..._",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await asyncio.sleep(0.3)
    
    try:
        # ====================================================================
        # TRY CACHE FIRST (FAST PATH)
        # ====================================================================
        
        # Create cache key that includes timeframe
        cache_key = f"{symbol}_{timeframe_type}"
        cached_result = regime_cache.get(cache_key, plan)
        
        if cached_result:
            logger.info(f"Cache hit: user={user_id}, symbol={symbol}, timeframe={timeframe_type}")
            
            await loading_msg.edit_text(
                f"⏳ **Analyzing {symbol}**\n"
                f"⏰ Timeframes: {tf_display}\n\n"
                f"_✓ Data retrieved from cache_",
                parse_mode=ParseMode.MARKDOWN
            )
            await asyncio.sleep(0.2)
            
            # Add timeframe info to result
            cached_result['timeframe_display'] = tf_display
            
            # Format and send
            response = format_regime_response_compact(cached_result, plan)
            
            cache_age_mins = regime_cache.get_cache_age_minutes(cache_key, plan)
            if cache_age_mins is not None:
                freshness = "very fresh" if cache_age_mins < 1 else f"{int(cache_age_mins)}m old"
                response += f"\n\n_📦 Cached data ({freshness}) • Updates every 5min_"
            
            await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
            return
        
        # ====================================================================
        # CACHE MISS - FETCH FRESH DATA (SLOW PATH)
        # ====================================================================
        
        logger.info(f"Cache miss: user={user_id}, symbol={symbol}, timeframe={timeframe_type} - fetching fresh")
        
        await loading_msg.edit_text(
            f"⏳ **Analyzing {symbol}**\n"
            f"⏰ Timeframes: {tf_display}\n\n"
            f"_Fetching live market data..._",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Run analysis with specified timeframes
        engine = RegimeEngine()
        result = await engine.analyze(symbol, plan, lower_tf, upper_tf)
        
        # Add timeframe info to result
        result['timeframe_display'] = tf_display
        
        logger.info(f"Analysis complete: user={user_id}, symbol={symbol}, regime={result.get('regime', 'unknown')}")
        
        # Cache the result
        regime_cache.set(cache_key, plan, result)
        
        await loading_msg.edit_text(
            f"⏳ **Analyzing {symbol}**\n"
            f"⏰ Timeframes: {tf_display}\n\n"
            f"_✓ Analysis complete_",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(0.2)
        
        # Format and send
        response = format_regime_response_compact(result, plan)
        response += "\n\n_✨ Fresh analysis • Updated every 5min_"
        
        await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(
            f"Regime analysis error: user={user_id}, symbol={symbol}, timeframe={timeframe_type}, "
            f"error={type(e).__name__}: {str(e)}",
            exc_info=True
        )
        
        error_msg = format_error_message(str(e), symbol)
        
        try:
            await loading_msg.edit_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as edit_error:
            logger.error(f"Failed to edit error message: {edit_error}")
            await update.effective_message.reply_text(error_msg, parse_mode=ParseMode.MARKDOWN)


# ============================================================================
# RESPONSE FORMATTING
# ============================================================================

def format_regime_response_compact(result: dict, plan: str) -> str:
    """
    Format regime analysis in mobile-optimized compact format
    Now includes timeframe information
    """
    
    # Add fallback warning if used
    warning = ""
    if "warning" in result:
        warning = f"⚠️ _{result['warning']}_\n\n"
    
    # Get timeframe display
    timeframe_info = result.get('timeframe_display', '4H + Daily')
    
    # Get regime emoji
    regime_emoji = get_regime_emoji(result['regime'])
    
    # ========================================================================
    # PRO TIER OUTPUT (they're the only ones who can access this now)
    # ========================================================================
    
    rules_summary = format_rules_compact(result['strategy_rules'])
    rules_details = format_rules_detailed(result['strategy_rules'])
    
    response = f"""{warning}**{result['symbol']} Market Analysis**
⏰ {timeframe_info}

{regime_emoji} **{result['regime']}**
📊 {result['risk_level']} Risk
 • 🎯 {result['confidence']}% Confidence

**Recommended Posture:**
_{result['posture']}_

**Strategy Rules:** {rules_summary}
{rules_details}

**Volume Trend:** {result['volume_behavior']}

**Key Levels:**
• 🟢 Support: ${result['key_levels']['support']:,.2f} ({result['key_levels']['support_strength']})
• 🔴 Resistance: ${result['key_levels']['resistance']:,.2f} ({result['key_levels']['resistance_strength']})
• 📍 Current: ${result['key_levels']['current_price']:,.2f}"""

    return response.strip()


def get_regime_emoji(regime: str) -> str:
    """Map regime type to appropriate emoji"""
    if "High-Risk Bearish" in regime:
        return "🔴"
    elif "Controlled Bearish" in regime or "Bearish" in regime:
        return "🔻"
    elif "Ranging" in regime:
        return "↔️"
    elif "Strong Bullish" in regime:
        return "🚀"
    elif "Bullish" in regime:
        return "📈"
    else:
        return "📊"


def format_rules_compact(rules: dict) -> str:
    """Format strategy rules as compact summary"""
    met_count = sum(1 for status in rules.values() if status)
    total_count = len(rules)
    
    if met_count == total_count:
        indicator = "✓"
    elif met_count >= total_count * 0.66:
        indicator = "✓"
    elif met_count >= total_count * 0.33:
        indicator = "⚠️"
    else:
        indicator = "❌"
    
    return f"{met_count}/{total_count} met {indicator}"


def format_rules_detailed(rules: dict) -> str:
    """Format individual rule statuses for Pro users"""
    rule_lines = []
    for rule_name, status in rules.items():
        short_name = rule_name.replace("_", " ").title()
        emoji = "✓" if status else "✗"
        rule_lines.append(f"  {emoji} {short_name}")
    
    return "\n".join(rule_lines)


# ============================================================================
# ERROR HANDLING
# ============================================================================

def format_error_message(error: str, symbol: str) -> str:
    """Format clear, actionable error messages"""
    error_lower = error.lower()
    
    if any(x in error_lower for x in ["network", "timeout", "connection"]):
        return """❌ **Connection Issue**

Couldn't reach the market data provider right now.

**What to try:**
• Wait 30 seconds and try again
• Check your internet connection
• Try a different symbol: `/regime ETH`

_If this keeps happening, the data provider may be temporarily down._"""
    
    if any(x in error_lower for x in ["rate limit", "429", "quota", "credits"]):
        return """⏱️ **Slow Down There!**

We've hit our data request limit temporarily.

**Please wait 2-3 minutes** and try again.

💡 **Pro tip:** Results are cached for 5 minutes.

_This protects our data costs and keeps the service running smoothly._"""
    
    if any(x in error_lower for x in ["invalid symbol", "symbol", "not found", "404"]):
        return f"""❌ **Symbol Not Found: {symbol}**

We couldn't find market data for **{symbol}**.

**Try these popular coins:**
• `/regime BTC`
• `/regime ETH`
• `/regime SOL`

**Tips:**
• Use base symbol only (BTC, not BTCUSDT)
• Only top 100 CoinGecko coins supported
• Use `/coins` to see the full list

_See /help for full command list_"""
    
    # Generic fallback
    return f"""❌ **Analysis Failed**

We couldn't complete the analysis for **{symbol}** right now.

**Quick fixes to try:**
1. Wait a minute and try again
2. Try a different symbol: `/regime BTC`
3. Check if the symbol is correct

**Still not working?**
Contact support: /support

_We're here to help!_"""