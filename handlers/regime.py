from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from services.regime_engine import RegimeEngine
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from utils.regime_cache import RegimeCache
import asyncio
import logging

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
# MAIN COMMAND HANDLER
# ============================================================================

async def regime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    plan = get_user_plan(user_id)
    await update_last_active(user_id, command_name="/regime")
    
    # Parse and validate symbol
    symbol = "BTC"
    if context.args and len(context.args) > 0:
        raw_symbol = context.args[0].upper().strip()
        # Clean symbol (remove common suffixes)
        symbol = raw_symbol.replace("USDT", "").replace("USD", "")[:10]  # Limit length
    
    # Log request to terminal only
    logger.info(f"Regime analysis request: user={user_id} ({username}), symbol={symbol}, plan={plan}")
    
    # ========================================================================
    # GRACEFUL LOADING MESSAGE
    # ========================================================================
    
    loading_msg = await update.message.reply_text(
        f"🔍 **Analyzing {symbol}**\n\n"
        f"_Checking market regime & sentiment..._",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Natural delay for better UX (makes it feel more thoughtful)
    await asyncio.sleep(0.3)
    
    try:
        # ====================================================================
        # TRY CACHE FIRST (FAST PATH)
        # ====================================================================
        
        cached_result = regime_cache.get(symbol, plan)
        
        if cached_result:
            # ================================================================
            # CACHE HIT - INSTANT RESPONSE
            # ================================================================
            
            logger.info(f"Cache hit: user={user_id}, symbol={symbol}, plan={plan}")
            
            # Show progress animation
            await loading_msg.edit_text(
                f"🔍 **Analyzing {symbol}**\n\n"
                f"_✓ Data retrieved from cache_",
                parse_mode=ParseMode.MARKDOWN
            )
            await asyncio.sleep(0.2)
            
            # Format cached result
            response = format_regime_response_compact(cached_result, plan)
            
            # Add cache indicator with freshness info
            cache_age_mins = regime_cache.get_cache_age_minutes(symbol, plan)
            if cache_age_mins is not None:
                freshness = "very fresh" if cache_age_mins < 1 else f"{int(cache_age_mins)}m old"
                response += f"\n\n_📦 Cached data ({freshness}) • Updates every 5min_"
            else:
                response += "\n\n_📦 Cached data • Updates every 5min_"
            
            # Send final response
            await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
            return
        
        # ====================================================================
        # CACHE MISS - FETCH FRESH DATA (SLOW PATH)
        # ====================================================================
        
        logger.info(f"Cache miss: user={user_id}, symbol={symbol}, plan={plan} - fetching fresh data")
        
        # Update loading message to show we're fetching
        await loading_msg.edit_text(
            f"🔍 **Analyzing {symbol}**\n\n"
            f"_Fetching live market data..._",
            parse_mode=ParseMode.MARKDOWN
        )
        
        engine = RegimeEngine()
        result = await engine.analyze(symbol, plan)
        
        logger.info(f"Analysis complete: user={user_id}, symbol={symbol}, regime={result.get('regime', 'unknown')}")
        
        # Cache the fresh result for future requests
        regime_cache.set(symbol, plan, result)
        
        # Show completion
        await loading_msg.edit_text(
            f"🔍 **Analyzing {symbol}**\n\n"
            f"_✓ Analysis complete_",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(0.2)
        
        # Format response with upsell if free user
        response = format_regime_response_compact(result, plan)
        
        # Add fresh data indicator
        response += "\n\n_✨ Fresh analysis • Updated every 5min_"
        
        # Edit loading message with final result
        await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        # ====================================================================
        # ERROR HANDLING
        # ====================================================================
        
        # Log full error details to terminal only
        logger.error(
            f"Regime analysis error: user={user_id} ({username}), symbol={symbol}, plan={plan}, "
            f"error_type={type(e).__name__}, error_msg={str(e)}",
            exc_info=True  # This logs full stack trace
        )
        
        # Show user-friendly error (no technical details or stack traces)
        error_msg = format_error_message(str(e), symbol)
        
        try:
            await loading_msg.edit_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as edit_error:
            # If we can't edit the message, send a new one
            logger.error(f"Failed to edit error message: {edit_error}")
            await update.message.reply_text(error_msg, parse_mode=ParseMode.MARKDOWN)


# ============================================================================
# RESPONSE FORMATTING
# ============================================================================

def format_regime_response_compact(result: dict, plan: str) -> str:
    """
    Format regime analysis in mobile-optimized compact format
    
    FREE: 7 lines + Pro upsell
    PRO: 12 lines with full details
    
    Args:
        result: Regime analysis result from RegimeEngine
        plan: User plan tier
    
    Returns:
        Formatted Telegram message with markdown
    """
    
    # Add fallback warning if used (more informative)
    warning = ""
    if "warning" in result:
        # Make warning more prominent
        warning = f"⚠️ _{result['warning']}_\n\n"
    
    # Get regime emoji
    regime_emoji = get_regime_emoji(result['regime'])
    
    # ========================================================================
    # FREE TIER OUTPUT (7 lines + upsell)
    # ========================================================================
    
    if not is_pro_plan(plan):
        response = f"""{warning}**{result['symbol']} Market Analysis**

{regime_emoji} **{result['regime']}**
📊 {result['risk_level']} Risk Level
🎯 {result['confidence']}% Confidence

**Recommended Posture:**
_{result['posture']}_"""
        
        # Add Pro upsell (context-aware based on confidence)
        upsell = get_pro_upsell(result['confidence'], result['risk_level'])
        response += f"\n\n{upsell}"
        
        return response.strip()
    
    # ========================================================================
    # PRO TIER OUTPUT (12 lines with full details)
    # ========================================================================
    
    rules_summary = format_rules_compact(result['strategy_rules'])
    rules_details = format_rules_detailed(result['strategy_rules'])
    
    response = f"""{warning}**{result['symbol']} Market Analysis**

{regime_emoji} **{result['regime']}**
📊 {result['risk_level']} Risk
 • 🎯 {result['confidence']}% Confidence

**Recommended Posture:**
_{result['posture']}_

**Strategy Rules:** {rules_summary}
{rules_details}

**Volume Trend:** {result['volume_behavior']}

**Key Levels:**
• Support: ${result['key_levels']['support']:,.2f}
• Resistance: ${result['key_levels']['resistance']:,.2f}"""
    
    return response.strip()


def get_pro_upsell(confidence: int, risk_level: str) -> str:
    """
    Generate context-aware Pro upsell message
    Tailored to confidence score and risk level for better conversion
    
    Args:
        confidence: Confidence score (0-100)
        risk_level: Risk level string (e.g., "High", "Moderate", "Low")
    
    Returns:
        Upsell message with call-to-action
    """
    
    # High risk situations - emphasize risk management tools
    if "High" in risk_level:
        return (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 **High Risk Detected - Pro Helps:**\n"
            "• See exactly which rules are failing\n"
            "• Volume divergence warnings\n"
            "• Critical support/resistance zones\n"
            "• Better risk management tools\n\n"
            "👉 /upgrade for full protection"
        )
    
    # High confidence (75%+) - emphasize missing details
    if confidence >= 75:
        return (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 **Strong Signal - See Full Details:**\n"
            "• 6 strategy rules breakdown\n"
            "• Volume confirmation analysis\n"
            "• Precise entry/exit levels\n"
            "• Maximize this opportunity\n\n"
            "👉 /upgrade to unlock"
        )
    
    # Medium confidence (50-74%) - emphasize decision support
    elif confidence >= 50:
        return (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 **Get More Clarity:**\n"
            "• Which rules are passing/failing\n"
            "• Volume behavior insights\n"
            "• Support & resistance zones\n"
            "• Make better decisions\n\n"
            "👉 /upgrade for pro insights"
        )
    
    # Low confidence (<50%) - emphasize risk avoidance
    else:
        return (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 **Low Confidence? Pro Shows Why:**\n"
            "• See failing rule indicators\n"
            "• Volume confirmation status\n"
            "• Where to wait for entries\n"
            "• Avoid bad trades\n\n"
            "👉 /upgrade to stay safe"
        )


def get_regime_emoji(regime: str) -> str:
    """
    Map regime type to appropriate emoji
    
    Args:
        regime: Regime string from RegimeEngine
    
    Returns:
        Single emoji character
    """
    
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
    """
    Format strategy rules as compact summary
    
    Args:
        rules: Dictionary of rule name -> bool status
    
    Returns:
        Compact string like "5/6 met ✓" or "3/6 met ⚠️"
    """
    
    met_count = sum(1 for status in rules.values() if status)
    total_count = len(rules)
    
    # Add visual indicator
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
    """
    Format individual rule statuses for Pro users
    
    Args:
        rules: Dictionary of rule name -> bool status
    
    Returns:
        Formatted string with individual rule statuses
    """
    
    rule_lines = []
    for rule_name, status in rules.items():
        # Shorten rule names for readability
        short_name = rule_name.replace("_", " ").title()
        emoji = "✓" if status else "✗"
        rule_lines.append(f"  {emoji} {short_name}")
    
    return "\n".join(rule_lines)


# ============================================================================
# ERROR HANDLING
# ============================================================================

def format_error_message(error: str, symbol: str) -> str:
    """
    Format clear, actionable error messages
    User-friendly only - no technical details or stack traces
    
    Args:
        error: Error message string
        symbol: Trading symbol that failed
    
    Returns:
        User-friendly error message with troubleshooting steps
    """
    
    error_lower = error.lower()
    
    # ========================================================================
    # NETWORK / CONNECTION ERRORS
    # ========================================================================
    
    if any(x in error_lower for x in ["network", "timeout", "connection"]):
        return """❌ **Connection Issue**

Couldn't reach the market data provider right now.

**What to try:**
• Wait 30 seconds and try again
• Check your internet connection
• Try a different symbol: `/regime ETH`

_If this keeps happening, the data provider may be temporarily down._"""
    
    # ========================================================================
    # API KEY / AUTHENTICATION ERRORS
    # ========================================================================
    
    if any(x in error_lower for x in ["api key", "401", "unauthorized", "forbidden"]):
        return """❌ **Service Configuration Error**

There's an issue with our market data connection.

**This is on our end** - please contact support:
👉 /support

_We'll get this fixed quickly!_"""
    
    # ========================================================================
    # RATE LIMIT ERRORS (with caching hint)
    # ========================================================================
    
    if any(x in error_lower for x in ["rate limit", "429", "quota", "credits"]):
        return """⏱️ **Slow Down There!**

We've hit our data request limit temporarily.

**Please wait 2-3 minutes** and try again.

💡 **Pro tip:** Results are cached for 5 minutes, so checking the same symbol multiple times won't help - the cached version will show automatically once available.

_This protects our data costs and keeps the service running smoothly._"""
    
    # ========================================================================
    # INVALID SYMBOL ERRORS
    # ========================================================================
    
    if any(x in error_lower for x in ["invalid symbol", "symbol", "not found", "404"]):
        return f"""❌ **Symbol Not Found: {symbol}**

We couldn't find market data for **{symbol}**.

**Try these popular coins:**
• `/regime` (defaults to BTC)
• `/regime ETH`
• `/regime SOL`
• `/regime BNB`

**Tips:**
• Use base symbol only (BTC, not BTCUSDT)
• Check spelling
• Stick to top 100 coins for best results

_See /help for full command list_"""
    
    # ========================================================================
    # INSUFFICIENT DATA ERRORS
    # ========================================================================
    
    if any(x in error_lower for x in ["insufficient", "not enough", "minimum", "no data"]):
        return f"""📊 **Not Enough Data: {symbol}**

**{symbol}** doesn't have enough price history for accurate analysis.

**Try these established coins instead:**
• `/regime BTC` - Bitcoin
• `/regime ETH` - Ethereum
• `/regime SOL` - Solana
• `/regime BNB` - Binance Coin

_Newer/smaller coins may not have the required historical data._"""
    
    # ========================================================================
    # DATA VALIDATION ERRORS
    # ========================================================================
    
    if any(x in error_lower for x in ["data error", "validation", "invalid", "malformed", "missing"]):
        return f"""⚠️ **Data Quality Issue: {symbol}**

The market data for **{symbol}** failed our quality checks.

**What to do:**
1. Try a different symbol: `/regime BTC`
2. Wait 5-10 minutes and retry {symbol}
3. If it keeps failing, use /support

_This usually means the data feed is temporarily unstable._"""
    
    # ========================================================================
    # SERVER ERRORS
    # ========================================================================
    
    if any(x in error_lower for x in ["500", "503", "server error", "unavailable", "service"]):
        return """🔧 **Data Provider Issues**

The market data service is having temporary problems.

**Please try again in 2-5 minutes.**

This happens occasionally and usually resolves quickly.

_This isn't your fault - the external service is having issues!_

Need help? → /support"""
    
    # ========================================================================
    # GENERIC ERROR (FALLBACK - NO TECHNICAL DETAILS)
    # ========================================================================
    
    return f"""❌ **Analysis Failed**

We couldn't complete the analysis for **{symbol}** right now.

**Quick fixes to try:**
1. Wait a minute and try again
2. Try a different symbol: `/regime BTC`
3. Check if the symbol is correct

**Still not working?**
Contact support: /support

_We're here to help!_"""
