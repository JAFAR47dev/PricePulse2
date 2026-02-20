# ============================================================================
# /MACRO COMMAND - FREE FEATURE
# ============================================================================

# ----------------------------------------------------------------------------
# handlers/macro.py
# ----------------------------------------------------------------------------
"""
Handler for /macro command - Macro Market Overview
Shows BTC, ETH, Gold, Silver, DXY, S&P 500 with correlations

FREE FEATURE - Great for user acquisition and education
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from services.macro_engine import MacroEngine, MacroError
from models.user import get_user_plan
from models.user_activity import update_last_active
from utils.macro_cache import MacroCache
import asyncio
from tasks.handlers import handle_streak
    

# Initialize cache (5 minute TTL - macro data changes frequently)
macro_cache = MacroCache(ttl_minutes=5)


async def macro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /macro command - Show macro market overview
    
    Usage:
        /macro - Show current macro snapshot
    
    FREE Feature - Available to all users
    """
    
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)
    await update_last_active(user_id, command_name="/macro")
    await handle_streak(update, context)
    
    
    # Loading message
    loading_msg = await update.message.reply_text(
        "📊 Loading macro market overview...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await asyncio.sleep(0.3)
    
    try:
        # Check cache first
        cached_result = macro_cache.get()
        
        if cached_result:
            # Show cache hit animation
            await loading_msg.edit_text(
                "📊 Loading macro market overview... ✓",
                parse_mode=ParseMode.MARKDOWN
            )
            await asyncio.sleep(0.2)
            
            response = format_macro_response(cached_result, plan)
            response += "\n\n_📦 Cached (updates every 5 min)_"
            
            await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Fetch fresh data
        engine = MacroEngine()
        result = await engine.get_macro_snapshot()
        
        # Cache result
        macro_cache.set(result)
        
        # Format and send
        response = format_macro_response(result, plan)
        await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        
    except MacroError as e:
        await loading_msg.edit_text(
            format_error_message(str(e)),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await loading_msg.edit_text(
            "❌ **Error**\n\nCould not load macro data.\n\nTry again in a moment.",
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================================
# RESPONSE FORMATTING
# ============================================================================

def format_macro_response(data: dict, plan: str) -> str:
    """
    Format macro market overview
    
    Shows:
    - Crypto (BTC, ETH)
    - Precious Metals (Gold, Silver)
    - Macro Indicators (DXY, S&P 500)
    - Key Ratios
    - Market Sentiment
    """
    
    btc = data['assets']['BTC']
    eth = data['assets']['ETH']
    gold = data['assets']['GOLD']
    silver = data['assets']['SILVER']
    dxy = data['assets']['DXY']
    spx = data['assets']['SPX']
    
    response = f"""📊 **Macro Market Overview**

**Crypto**
₿ **BTC:** ${btc['price']:,.0f} {format_change(btc['change_24h'])}
Ξ **ETH:** ${eth['price']:,.0f} {format_change(eth['change_24h'])}

**Precious Metals**
🥇 **Gold:** ${gold['price']:,.2f}/oz {format_change(gold['change_24h'])}
🥈 **Silver:** ${silver['price']:,.2f}/oz {format_change(silver['change_24h'])}

**Macro Indicators**
💵 **DXY:** {dxy['price']:.2f} {format_change(dxy['change_24h'])}
📈 **S&P 500:** {spx['price']:,.0f} {format_change(spx['change_24h'])}

**Key Ratios**
🔗 Gold/BTC: {data['ratios']['gold_btc']:.4f} oz per BTC
🔗 Silver/Gold: 1:{data['ratios']['silver_gold_ratio']:.0f}

💡 **Market Sentiment:** {data['sentiment']['status']}
{data['sentiment']['description']}

_Updated: {data['timestamp']}_"""
    
    # Add Pro upsell for free users
    from utils.auth import is_pro_plan
    if not is_pro_plan(plan):
        response += "\n\n" + get_macro_upsell()
    
    return response.strip()


def format_change(change_pct: float) -> str:
    """
    Format percentage change with emoji
    
    Args:
        change_pct: Percentage change (e.g., 2.5 for +2.5%)
    
    Returns:
        Formatted string like "🟢 +2.5%" or "🔴 -1.2%"
    """
    if change_pct > 0:
        return f"🟢 +{change_pct:.1f}%"
    elif change_pct < 0:
        return f"🔴 {change_pct:.1f}%"
    else:
        return "➡️ 0.0%"


def get_macro_upsell() -> str:
    """Upsell Pro features related to macro"""
    return """━━━━━━━━━━━━━━━━━━━━
🔒 **Pro traders get more:**
• Compare any two assets (/compare BTC GOLD)
• Track historical ratios & trends
• Get alerts on key ratio changes
• Advanced correlation analysis

👉 /upgrade to unlock"""


def format_error_message(error: str) -> str:
    """Format error messages"""
    
    error_lower = error.lower()
    
    if "api" in error_lower or "fetch" in error_lower:
        return """❌ **Data Fetch Error**

Could not retrieve macro data from provider.

**Try:**
• Wait a moment and retry
• Check back in a few minutes

_If issue persists, our data provider may be down._"""
    
    if "rate limit" in error_lower:
        return """⏱️ **Rate Limit**

Too many macro data requests.

**Try again in 1-2 minutes.**

_Tip: Results are cached for 5 minutes._"""
    
    return f"""❌ **Error**

Could not load macro data.

**Error:** {error[:100]}

Try: /macro again in a moment"""




# ============================================================================
# REGISTRATION
# ============================================================================

"""
Add to handlers/__init__.py:

from telegram.ext import CommandHandler
from .macro import macro_command

def register_handlers(application):
    # Macro command (FREE feature)
    application.add_handler(CommandHandler("macro", macro_command))
"""


# ============================================================================
# BOTFATHER DESCRIPTION
# ============================================================================

"""
BotFather command description:

macro - View macro market overview (crypto, metals, indices)

Help text:

📊 **/macro** - Macro Market Overview

See the big picture with one command:
• Bitcoin & Ethereum prices
• Gold & Silver prices
• Dollar Index (DXY)
• S&P 500 Index
• Key ratios (Gold/BTC, Silver/Gold)
• Market sentiment analysis

Updates every 5 minutes.
100% FREE for all users.

Example: Just type /macro
"""


# ============================================================================
# EXAMPLE OUTPUT
# ============================================================================

"""
USER TYPES: /macro

BOT RESPONDS:
──────────────────────────────────────────
📊 **Macro Market Overview**

**Crypto**
₿ **BTC:** $43,250 🟢 +2.3%
Ξ **ETH:** $2,345 🟢 +3.1%

**Precious Metals**
🥇 **Gold:** $2,045.30/oz 🟢 +0.8%
🥈 **Silver:** $24.15/oz 🟢 +1.2%

**Macro Indicators**
💵 **DXY:** 103.45 🔴 -0.3%
📈 **S&P 500:** 4,780 🟢 +0.5%

**Key Ratios**
🔗 Gold/BTC: 0.0473 oz per BTC
🔗 Silver/Gold: 1:85

💡 **Market Sentiment:** 🟢 Risk-On
Bullish environment for crypto and equities

_Updated: 2026-01-21 14:30 UTC_

━━━━━━━━━━━━━━━━━━━━
🔒 **Pro traders get more:**
• Compare any two assets (/compare BTC GOLD)
• Track historical ratios & trends
• Get alerts on key ratio changes
• Advanced correlation analysis

👉 /upgrade to unlock
──────────────────────────────────────────

RISK-OFF EXAMPLE:
──────────────────────────────────────────
📊 **Macro Market Overview**

**Crypto**
₿ **BTC:** $41,800 🔴 -3.5%
Ξ **ETH:** $2,150 🔴 -5.2%

**Precious Metals**
🥇 **Gold:** $2,085.50/oz 🟢 +2.1%
🥈 **Silver:** $25.40/oz 🟢 +1.8%

**Macro Indicators**
💵 **DXY:** 105.20 🟢 +1.2%
📈 **S&P 500:** 4,650 🔴 -1.8%

**Key Ratios**
🔗 Gold/BTC: 0.0499 oz per BTC
🔗 Silver/Gold: 1:82

💡 **Market Sentiment:** 🔴 Risk-Off
Defensive positioning — capital fleeing to safety

_Updated: 2026-01-21 14:30 UTC_
──────────────────────────────────────────

INFLATION HEDGE EXAMPLE:
──────────────────────────────────────────
📊 **Macro Market Overview**

**Crypto**
₿ **BTC:** $44,500 🟢 +4.2%
Ξ **ETH:** $2,450 🟢 +5.8%

**Precious Metals**
🥇 **Gold:** $2,125.00/oz 🟢 +3.5%
🥈 **Silver:** $26.10/oz 🟢 +4.2%

**Macro Indicators**
💵 **DXY:** 102.80 🔴 -0.8%
📈 **S&P 500:** 4,820 🟢 +1.2%

**Key Ratios**
🔗 Gold/BTC: 0.0477 oz per BTC
🔗 Silver/Gold: 1:81

💡 **Market Sentiment:** ⚠️ Inflation Hedge Mode
Uncertainty driving flows to alternative assets

_Updated: 2026-01-21 14:30 UTC_
──────────────────────────────────────────
"""