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

# Initialize services
market_service = MarketDataService()
sentiment_service = SentimentService()
sector_service = SectorAnalysisService()
macro_service = MacroDataService()
analyzer = TodayAnalyzer()

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /today command handler - PRO FEATURE
    Shows comprehensive market analysis with actionable recommendation
    
    Usage:
    /today          - Full market analysis
    /today btc      - BTC deep dive only
    /today sectors  - Sector breakdown only
    /today risk     - Quick risk assessment
    """
    user_id = update.effective_user.id
    
    # Update user activity
    await update_last_active(user_id, command_name="/today")
    
    # Check if user has Pro plan
    plan = get_user_plan(user_id)
    
    if not is_pro_plan(plan):
        # Show free users what they're missing with a compelling preview
        preview_message = (
            "🔒 **Pro Feature: Market Intelligence**\n\n"
            "The `/today` command gives you:\n\n"
            "✅ **Real-time market verdict** — Should you trade today?\n"
            "✅ **BTC + ETH technical analysis** — RSI, MA, trend strength\n"
            "✅ **Sector performance breakdown** — Layer 1s, DeFi, Memes, AI\n"
            "✅ **Top 3 opportunities** — What to trade right now\n"
            "✅ **Risk assessment** — Position sizing & strategy\n"
            "✅ **4 view modes** — Full, BTC-only, Sectors, Quick risk\n\n"
            "📊 **Example verdict:**\n"
            "`🟢 FAVORABLE CONDITIONS`\n"
            "`✅ TRADE TODAY — BTC showing bullish strength`\n"
            "`• BTC: $43,500 (+2.3%) — Bullish 💪`\n"
            "`• Top pick: Layer 1s (+3.2% avg)`\n"
            "`• Strategy: Normal sizing OK`\n\n"
            "🎯 **Never guess again** — Let the data decide.\n\n"
            "💎 Upgrade to Pro: /upgrade"
        )
        await update.message.reply_text(preview_message, parse_mode="Markdown")
        return
    
    # Parse command arguments
    args = context.args
    view_mode = args[0].lower() if args else "full"
    
    # Send "loading" message
    loading_msg = await update.message.reply_text("🔄 Analyzing market conditions...")
    
    try:
        # Fetch all data sources
        btc_data = market_service.get_coin_data("BTC")
        eth_data = market_service.get_coin_data("ETH")
        sentiment_data = sentiment_service.get_fear_greed_index()
        sector_data = sector_service.get_sector_analysis()
        macro_data = macro_service.get_macro_indicators()
        
        # Check critical data
        if not btc_data or not eth_data:
            await loading_msg.edit_text("❌ Failed to fetch market data. Try again later.")
            return
        
        # Comprehensive analysis
        analysis = analyzer.analyze_market(
            btc_data=btc_data,
            eth_data=eth_data,
            sentiment_data=sentiment_data,
            sector_data=sector_data,
            macro_data=macro_data
        )
        
        # Format message based on view mode
        if view_mode == "btc":
            message = analyzer.format_btc_deep_dive(analysis)
        elif view_mode == "sectors":
            message = analyzer.format_sectors_only(analysis)
        elif view_mode == "risk":
            message = analyzer.format_risk_only(analysis)
        else:  # full
            message = analyzer.format_full_analysis(analysis)
        
        # Send final message
        await loading_msg.edit_text(message, parse_mode="Markdown", disable_web_page_preview=True)
        
    except Exception as e:
        print(f"Error in /today command: {e}")
        import traceback
        traceback.print_exc()
        await loading_msg.edit_text("❌ Something went wrong. Please try again.")