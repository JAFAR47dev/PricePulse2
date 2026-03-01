from telegram import Update
from telegram.ext import ContextTypes
from services.today_data import MarketDataService
from services.sentiment import SentimentService
from services.sector_analysis import SectorAnalysisService
from services.macro_data import MacroDataService
from utils.today_builder import TodayAnalyzer
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
import time
from typing import Dict, Optional
from tasks.handlers import handle_streak
# Initialize services (singleton pattern)
market_service = MarketDataService()
sentiment_service = SentimentService()
sector_service = SectorAnalysisService()
macro_service = MacroDataService()
analyzer = TodayAnalyzer()

# Rate limiting cache (user_id: last_request_time)
_rate_limit_cache: Dict[int, float] = {}
RATE_LIMIT_SECONDS = 15 # 15 seconds between requests

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /today command handler - PRO FEATURE
    Comprehensive market analysis with actionable recommendations
    
    Usage:
    /today          - Full market analysis (default)
    /today btc      - BTC deep dive only
    /today eth      - ETH deep dive only (NEW)
    /today sectors  - Sector breakdown only
    /today risk     - Quick risk assessment
    /today macro    - Macro market view (NEW)
    
    Examples:
    /today
    /today risk
    /today btc
    """
    user_id = update.effective_user.id
    
    try:
        # Update user activity
        await update_last_active(user_id, command_name="/today")
        await handle_streak(update, context)
    
    except Exception as e:
        print(f"Error updating user activity: {e}")
        # Don't block command execution
    
    # === PRO PLAN CHECK ===
    plan = get_user_plan(user_id)
    
    if not is_pro_plan(plan):
        preview_message = (
            "🔒 **Pro Feature: Market Intelligence**\n\n"
            "Get institutional-grade market analysis:\n\n"
            "✅ **Smart Market Verdict** — 100-point scoring system\n"
            "✅ **Technical Analysis** — BTC, ETH with RSI, MA, trend strength\n"
            "✅ **8 Sector Breakdown** — Layer1, DeFi, Meme, AI, Gaming, NFT, Privacy, Infrastructure\n"
            "✅ **Macro Analysis** — Dominance, flows, alt season index\n"
            "✅ **Top 5 Opportunities** — Quality-scored trade setups\n"
            "✅ **Risk Warnings** — Real-time alerts on market extremes\n"
            "✅ **Custom Strategy** — Position sizing, leverage, timeframe\n"
            "✅ **6 View Modes** — Full, BTC, ETH, Sectors, Risk, Macro\n\n"
            "🎯 **Stop guessing. Start trading with data.**\n\n"
            "💎 Upgrade to Pro: /upgrade"
        )
        await update.message.reply_text(preview_message, parse_mode="Markdown")
        return
    
    # === RATE LIMITING (Pro users only) ===
    current_time = time.time()
    last_request = _rate_limit_cache.get(user_id, 0)
    
    if current_time - last_request < RATE_LIMIT_SECONDS:
        remaining = int(RATE_LIMIT_SECONDS - (current_time - last_request))
        await update.message.reply_text(
            f"⏳ Please wait {remaining} seconds before requesting another analysis.\n"
            f"(Data updates every 30 minutes anyway)"
        )
        return
    
    # Update rate limit cache
    _rate_limit_cache[user_id] = current_time
    
    # === PARSE ARGUMENTS ===
    args = context.args
    view_mode = args[0].lower() if args else "full"
    
    # Validate view mode
    valid_modes = ["full", "btc", "eth", "sectors", "risk", "macro"]
    if view_mode not in valid_modes:
        await update.message.reply_text(
            f"❌ Invalid view mode: `{view_mode}`\n\n"
            f"**Valid modes:**\n"
            f"• `/today` or `/today full` - Complete analysis\n"
            f"• `/today btc` - Bitcoin deep dive\n"
            f"• `/today eth` - Ethereum deep dive\n"
            f"• `/today sectors` - Sector performance\n"
            f"• `/today risk` - Quick risk check\n"
            f"• `/today macro` - Macro market view",
            parse_mode="Markdown"
        )
        return
    
    # === LOADING MESSAGE ===
    if view_mode == "risk":
        loading_msg = await update.message.reply_text("⚡ Running quick analysis...")
    elif view_mode in ["btc", "eth"]:
        loading_msg = await update.message.reply_text(f"🔄 Analyzing {view_mode.upper()}...")
    elif view_mode == "macro":
        loading_msg = await update.message.reply_text("🌍 Analyzing macro conditions...")
    elif view_mode == "sectors":
        loading_msg = await update.message.reply_text("🎯 Analyzing 8 sectors...")
    else:
        loading_msg = await update.message.reply_text("🔄 Analyzing market conditions across all metrics...")
    
    try:
        # === FETCH DATA (with individual error handling) ===
        
        # BTC data (critical)
        btc_data = market_service.get_coin_data("BTC")
        if not btc_data:
            await loading_msg.edit_text(
                "❌ Failed to fetch BTC data. This is required for analysis.\n"
                "Please try again in a few moments."
            )
            return
        
        # ETH data (critical)
        eth_data = market_service.get_coin_data("ETH")
        if not eth_data:
            await loading_msg.edit_text(
                "❌ Failed to fetch ETH data. This is required for analysis.\n"
                "Please try again in a few moments."
            )
            return
        
        # Sentiment data (fallback available)
        sentiment_data = sentiment_service.get_fear_greed_index()
        if not sentiment_data:
            print("Warning: Sentiment data unavailable, using fallback")
            sentiment_data = {
                "value": 50,
                "classification": "Neutral",
                "emoji": "🔶",
                "context": "Sentiment data temporarily unavailable"
            }
        
        # Sector data (can continue without)
        sector_data = sector_service.get_sector_analysis()
        if not sector_data:
            print("Warning: Sector data unavailable")
            sector_data = {}
        
        # Macro data (important but can use fallback)
        try:
            # For quick views, skip altcoin season calculation (faster)
            include_alt_season = view_mode not in ["risk", "btc", "eth"]
            macro_data = macro_service.get_macro_indicators(include_alt_season=include_alt_season)
        except Exception as e:
            print(f"Error fetching macro data: {e}")
            macro_data = macro_service._get_fallback_data(include_alt_season=False)
        
        if not macro_data:
            print("Warning: Using fallback macro data")
            macro_data = {
                "btc_dominance": 50.0,
                "eth_dominance": 15.0,
                "total_stablecoin_dominance": 7.0,
                "market_structure": "unknown",
                "exchange_flow": "neutral",
                "exchange_flow_signal": "neutral"
            }
        
        # === RUN ANALYSIS ===
        analysis = analyzer.analyze_market(
            btc_data=btc_data,
            eth_data=eth_data,
            sentiment_data=sentiment_data,
            sector_data=sector_data,
            macro_data=macro_data
        )
        
        # === FORMAT MESSAGE ===
        if view_mode == "btc":
            message = analyzer.format_btc_deep_dive(analysis)
        elif view_mode == "eth":
            message = analyzer.format_eth_deep_dive(analysis)  # You'll need to add this
        elif view_mode == "sectors":
            message = analyzer.format_sectors_only(analysis)
        elif view_mode == "risk":
            message = analyzer.format_risk_only(analysis)
        elif view_mode == "macro":
            message = analyzer.format_macro_only(analysis)
        else:  # full
            message = analyzer.format_full_analysis(analysis)
        
        # === SEND RESULT ===
        try:
            await loading_msg.edit_text(
                message, 
                parse_mode="HTML", 
                disable_web_page_preview=True
            )
        except Exception as e:
            # Handle message too long error
            if "message is too long" in str(e).lower():
                # Split message or send as file
                await loading_msg.edit_text(
                    "📊 Analysis complete! Message too long for Telegram.\n"
                    "Try a specific view:\n"
                    "• `/today risk` - Quick view\n"
                    "• `/today btc` - BTC only\n"
                    "• `/today sectors` - Sectors only",
                    parse_mode="Markdown"
                )
            else:
                raise
        
    except Exception as e:
        print(f"Error in /today command: {e}")
        import traceback
        traceback.print_exc()
        
        # User-friendly error message
        error_msg = (
            "❌ **Analysis Failed**\n\n"
            "Something went wrong while analyzing the market. "
            "This could be due to:\n"
            "• Temporary API issues\n"
            "• Network connectivity\n"
            "• Rate limiting from data providers\n\n"
            "**What to do:**\n"
            "• Wait 30 seconds and try again\n"
            "• Try a simpler view: `/today risk`\n"
            "• Contact support if issue persists\n\n"
            f"Error details: `{str(e)[:100]}`"
        )
        
        try:
            await loading_msg.edit_text(error_msg, parse_mode="Markdown")
        except:
            # If edit fails, send new message
            await update.message.reply_text(error_msg, parse_mode="Markdown")

# === HELPER: Clear rate limit cache periodically ===
def clear_old_rate_limits():
    """Remove rate limit entries older than 5 minutes"""
    current_time = time.time()
    expired_users = [
        user_id for user_id, timestamp in _rate_limit_cache.items()
        if current_time - timestamp > 300  # 5 minutes
    ]
    for user_id in expired_users:
        del _rate_limit_cache[user_id]

# Call this periodically in your bot's main loop or scheduler
# Example: scheduler.add_job(clear_old_rate_limits, 'interval', minutes=10)
