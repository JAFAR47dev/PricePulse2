# ----------------------------------------------------------------------------
# handlers/levels.py
# ----------------------------------------------------------------------------
"""
Handler for /levels command - Professional Support & Resistance Analysis
- Multi-timeframe support (1m, 5m, 15m, 1h, 4h, 1d, 1w)
- Single key level + range display
- No caching (always fresh data)
- Pro-only feature
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from services.levels_engine import LevelsEngine, LevelsError, TIMEFRAME_CONFIG
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
import asyncio
from tasks.handlers import handle_streak
    
async def levels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /levels command - Pro only, always fresh calculations"""
    
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)
    await update_last_active(user_id, command_name="/levels")
    await handle_streak(update, context)
    
    
    # Pro-only check
    if not is_pro_plan(plan):
        await update.message.reply_text(
            format_upgrade_prompt(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Parse arguments
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            format_usage_help(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    symbol = context.args[0].upper().strip()
    timeframe = context.args[1].lower().strip() if len(context.args) >= 2 else "1h"
    timeframe_aliases = {
    "1day": "1d",
    "1week": "1w",
    "daily": "1d",
    "weekly": "1w",
    "1min": "1m",
    "5min": "5m",
    "15min": "15m",
    "hour": "1h",
    "4hour": "4h",
}
    timeframe = timeframe_aliases.get(timeframe, timeframe)

	# Validate timeframe
    valid_timeframes = list(TIMEFRAME_CONFIG.keys())
    if timeframe not in valid_timeframes:
        await update.message.reply_text(
            f"❌ Invalid timeframe: `{timeframe}`\n\n"
      	  f"**Valid options:**\n"
      	  f"• Scalping: `1m`, `5m`, `15m`\n"
      	  f"• Intraday: `1h`, `4h`\n"
        	f"• Swing/Position: `1d`, `1w`\n\n"
       	 f"Example: `/levels btc 4h`",
            parse_mode=ParseMode.MARKDOWN
  	  )
        return
    
    # Loading message
    loading_msg = await update.message.reply_text(
        f"📊 Analyzing {symbol} on {timeframe.upper()} timeframe...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await asyncio.sleep(0.3)
    
    try:
        # Always calculate fresh (no cache)
        engine = LevelsEngine()
        result = await engine.calculate_levels(symbol, timeframe)
        
        # Format and send response
        response = format_levels_response(result, symbol, timeframe)
        await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        
    except LevelsError as e:
        error_msg = format_error_message(str(e), symbol, timeframe)
        await loading_msg.edit_text(error_msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ **Error**\n\n"
            f"Could not calculate levels for {symbol} on {timeframe}.\n\n"
            f"Try a different symbol or timeframe.",
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================================
# RESPONSE FORMATTING (KEY LEVEL + RANGE)
# ============================================================================

def format_levels_response(result: dict, symbol: str, timeframe: str) -> str:
    """
    Format levels analysis with key level + range display
    
    Format: $45,000 ($44,800 - $45,200)
    Shows single key level with range in parentheses
    """
    
    current_price = result['current_price']
    support_levels = result['support_levels']
    resistance_levels = result['resistance_levels']
    
    # Build response header
    response = f"**📊 {symbol} Key Levels ({timeframe.upper()})**\n\n"
    response += f"💰 **Current:** ${format_price(current_price)}\n\n"
    
    # ========================================================================
    # RESISTANCE LEVELS (above current price)
    # ========================================================================
    
    if resistance_levels:
        response += "🔴 **Resistance:**\n"
        for level in resistance_levels[:3]:
            distance_pct = ((level['price'] - current_price) / current_price) * 100
            strength_emoji = get_strength_emoji(level['strength'])
            
            # Format: $45,000 ($44,800 - $45,200)
            level_display = format_key_level_with_range(
                level['price'],
                level['price_lower'],
                level['price_upper']
            )
            
            response += (
                f"{strength_emoji} **{level_display}** "
                f"_(+{distance_pct:.1f}%)_\n"
                f"   {level['touches']} touches · {level['strength']}\n"
            )
        response += "\n"
    else:
        response += "🔴 **Resistance:** _No nearby levels_\n\n"
    
    # ========================================================================
    # SUPPORT LEVELS (below current price)
    # ========================================================================
    
    if support_levels:
        response += "🟢 **Support:**\n"
        for level in support_levels[:3]:
            distance_pct = ((current_price - level['price']) / current_price) * 100
            strength_emoji = get_strength_emoji(level['strength'])
            
            # Format: $42,000 ($41,800 - $42,200)
            level_display = format_key_level_with_range(
                level['price'],
                level['price_lower'],
                level['price_upper']
            )
            
            response += (
                f"{strength_emoji} **{level_display}** "
                f"_(-{distance_pct:.1f}%)_\n"
                f"   {level['touches']} touches · {level['strength']}\n"
            )
        response += "\n"
    else:
        response += "🟢 **Support:** _No nearby levels_\n\n"
    
    # ========================================================================
    # TRADING INSIGHT
    # ========================================================================
    
    insight = generate_trading_insight(result)
    response += f"💡 **Insight:** {insight}\n\n"
    
    # Add timeframe indicator
    response += f"_⏱ {get_timeframe_description(timeframe)} · Fresh data_"
    
    return response.strip()


def format_key_level_with_range(
    key_level: float,
    range_lower: float,
    range_upper: float
) -> str:
    """
    Format level as: $45,000 ($44,800 - $45,200)
    
    Args:
        key_level: Main price level
        range_lower: Lower bound of range
        range_upper: Upper bound of range
    
    Returns:
        Formatted string
    """
    key_str = format_price(key_level)
    lower_str = format_price(range_lower)
    upper_str = format_price(range_upper)
    
    return f"${key_str} (${lower_str} - ${upper_str})"


def format_price(price: float) -> str:
    """
    Smart price formatting based on magnitude
    
    Examples:
        43250.5 → 43,250
        1234.567 → 1,234.57
        12.345 → 12.35
        0.12345 → 0.1235
        0.00012345 → 0.0001235
    """
    if price >= 1000:
        return f"{price:,.0f}"
    elif price >= 100:
        return f"{price:,.0f}"
    elif price >= 1:
        return f"{price:,.2f}"
    elif price >= 0.01:
        return f"{price:.4f}"
    else:
        return f"{price:.7f}"


def get_strength_emoji(strength: str) -> str:
    """Map strength level to emoji"""
    emoji_map = {
        "Strong": "🔥",
        "Medium": "⚡",
        "Weak": "💫"
    }
    return emoji_map.get(strength, "•")


def get_timeframe_description(timeframe: str) -> str:
    """Get human-readable timeframe description"""
    descriptions = {
        "1m": "1 Minute",
        "5m": "5 Minutes",
        "15m": "15 Minutes",
        "1h": "1 Hour",
        "4h": "4 Hours",
        "1d": "Daily",
        "1w": "Weekly",
    }
    return descriptions.get(timeframe, timeframe.upper())


def generate_trading_insight(result: dict) -> str:
    """
    Generate actionable trading insight based on price position
    
    Args:
        result: Levels calculation result
    
    Returns:
        Trading insight string
    """
    
    support = result['support_levels']
    resistance = result['resistance_levels']
    current = result['current_price']
    
    # No levels detected
    if not support and not resistance:
        return "Price in open territory — watch for volatility"
    
    # Check proximity to resistance
    if resistance:
        nearest_res = resistance[0]
        res_lower = nearest_res['price_lower']
        res_upper = nearest_res['price_upper']
        
        # Inside resistance zone
        if res_lower <= current <= res_upper:
            if nearest_res['strength'] == "Strong":
                return "🔴 Testing strong resistance zone — watch for rejection or breakout"
            else:
                return "🔴 Inside resistance zone — monitor for direction"
        
        # Very close to resistance (within 1.5%)
        distance_pct = ((res_lower - current) / current) * 100
        if 0 < distance_pct < 1.5:
            if nearest_res['strength'] == "Strong":
                return "🔴 Approaching strong resistance — prepare for reaction"
            else:
                return "🔴 Nearing resistance — watch for price action"
    
    # Check proximity to support
    if support:
        nearest_sup = support[0]
        sup_lower = nearest_sup['price_lower']
        sup_upper = nearest_sup['price_upper']
        
        # Inside support zone
        if sup_lower <= current <= sup_upper:
            if nearest_sup['strength'] == "Strong":
                return "🟢 Testing strong support zone — watch for bounce or breakdown"
            else:
                return "🟢 Inside support zone — monitor for direction"
        
        # Very close to support (within 1.5%)
        distance_pct = ((current - sup_upper) / current) * 100
        if 0 < distance_pct < 1.5:
            if nearest_sup['strength'] == "Strong":
                return "🟢 Approaching strong support — prepare for reaction"
            else:
                return "🟢 Nearing support — watch for price action"
    
    # Between levels
    if support and resistance:
        return "Price between key levels — range-bound conditions"
    
    # Default
    return "Monitor nearest level for price reaction"


# ============================================================================
# HELPER TEXT FORMATTERS
# ============================================================================

def format_upgrade_prompt() -> str:
    """Upgrade prompt for free users"""
    return """🔒 **Pro Feature: Support & Resistance Analysis**

Professional key level detection is exclusively for Pro traders.

**Why this matters:**
• Identify high-probability reversal zones
• See exact price ranges (not just single levels)
• Understand level strength based on testing history
• Make informed entry and exit decisions
• Avoid getting trapped at major levels

**What you get:**
✓ Key levels with price ranges on 7 timeframes
✓ Strength scoring (Strong/Medium/Weak)
✓ Touch count and volume analysis
✓ Distance from current price
✓ Actionable trading insights

**Example output:**
```
🔴 Resistance:
🔥 $45,000 ($44,800 - $45,200) (+4.2%)
   4 touches · Strong

🟢 Support:
🔥 $42,000 ($41,800 - $42,200) (-3.1%)
   5 touches · Strong
```

**Supported timeframes:**
• Scalping: 1m, 5m, 15m
• Swing: 1h, 4h
• Position: 1d, 1w

👉 /upgrade to unlock professional level analysis"""


def format_usage_help() -> str:
    """Usage help message"""
    return """📊 **Professional S/R Level Analysis**

**Usage:**
`/levels <symbol> [timeframe]`

**Examples:**
• `/levels BTC` — BTC on 1h (default)
• `/levels ETH 4h` — ETH on 4 hour
• `/levels SOL 1d` — SOL on daily
• `/levels MATIC 15m` — MATIC on 15 minutes

**Available Timeframes:**

_Scalping & Day Trading:_
• `1m` — 1 minute
• `5m` — 5 minutes
• `15m` — 15 minutes

_Swing Trading:_
• `1h` — 1 hour
• `4h` — 4 hours (default)

_Position Trading:_
• `1d` — Daily
• `1w` — Weekly

**Features:**
✓ Key level + price range format
✓ Strength scoring per level
✓ Touch count and volume data
✓ Distance from current price
✓ Real-time trading insights

**Supported Assets:**
Top 100 CoinGecko coins only
"""


def format_error_message(error: str, symbol: str, timeframe: str) -> str:
    """Format error messages with helpful suggestions"""
    
    error_lower = error.lower()
    
    # Symbol not supported
    if "not in top 100" in error_lower or "not supported" in error_lower:
        return f"""❌ **Symbol Not Supported**

{symbol} is not in the top 100 CoinGecko coins.

**Try major assets:**
• Layer 1: BTC, ETH, BNB, SOL, ADA
• DeFi: UNI, AAVE, LINK, SUSHI
• Layer 2: MATIC, ARB, OP
• Memes: DOGE, SHIB, PEPE

_Only top 100 coins supported for accurate analysis._"""
    
    # Insufficient data
    if "insufficient" in error_lower or "not enough" in error_lower:
        return f"""📊 **Insufficient Data**

Not enough historical data for {symbol} on {timeframe}.

**Solutions:**
• Try longer timeframe: `/levels {symbol} 4h`
• Try daily chart: `/levels {symbol} 1d`
• Use more established coin
• Check back later

_Newer coins may lack data on shorter timeframes._"""
    
    # Invalid timeframe
    if "invalid timeframe" in error_lower:
        return f"""⏱ **Invalid Timeframe**

`{timeframe}` is not a valid timeframe.

**Valid options:**
• Scalping: `1m`, `5m`, `15m`
• Swing: `1h`, `4h`
• Position: `1d`, `1w`

**Try:**
`/levels {symbol} 4h`"""
    
    # Generic error
    return f"""❌ **Calculation Error**

Could not analyze {symbol} on {timeframe}.

**Troubleshooting:**
• Try different timeframe: `/levels {symbol} 4h`
• Try different symbol: `/levels BTC {timeframe}`
• Check symbol spelling
• Ensure symbol is top 100 coin

_If issue persists, the asset may have data quality issues._"""