from telegram import Update
from telegram.ext import ContextTypes
from services.today_data import MarketDataService
from services.sentiment import SentimentService
from utils.today_builder import TodayAnalyzer

# Initialize services
market_service = MarketDataService()
sentiment_service = SentimentService()
analyzer = TodayAnalyzer()

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /today command handler
    Shows current market snapshot with actionable recommendation
    """
    user_id = update.effective_user.id
    
    
    # Send "loading" message
    loading_msg = await update.message.reply_text("🔄 Analyzing market conditions...")
    
    try:
        # Fetch data
        market_data = market_service.get_btc_data()
        sentiment_data = sentiment_service.get_fear_greed_index()
        
        if not market_data:
            await loading_msg.edit_text("❌ Failed to fetch market data. Try again later.")
            return
        
        # Analyze
        analysis = analyzer.analyze(market_data, sentiment_data)
        
        # Format message
        message = analyzer.format_message(analysis)
        
        # Send final message
        await loading_msg.edit_text(message, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error in /today command: {e}")
        await loading_msg.edit_text("❌ Something went wrong. Please try again.")