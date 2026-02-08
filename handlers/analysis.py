# ============================================================================
# /ANALYSIS - AI TECHNICAL ANALYSIS ASSISTANT (PRO ONLY)
# ============================================================================

# ----------------------------------------------------------------------------
# handlers/analysis.py
# ----------------------------------------------------------------------------
"""
AI Technical Analysis Assistant - Pro Feature

What it does:
- Interprets complex technical indicators in plain English
- Identifies current market conditions and momentum
- Explains what indicators suggest (not predicts)
- Provides actionable insights for different timeframes

What it DOESN'T do:
- Predict future prices
- Guarantee outcomes
- Replace your own analysis
- Constitute financial advice
"""

import requests
import os
from utils.indicators import get_crypto_indicators
from models.user import get_user_plan
from utils.auth import is_pro_plan
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from models.user_activity import update_last_active
import json
import httpx
import logging
from datetime import datetime
from tasks.handlers import handle_streak
    
logger = logging.getLogger(__name__)

# Load supported coins (top 200)
COINGECKO_IDS_PATH = os.path.join("services", "top200_coingecko_ids.json")
with open(COINGECKO_IDS_PATH, "r") as f:
    COINGECKO_ID_MAP = json.load(f)


def safe(value):
    """Safely format indicator values"""
    try:
        if value is None:
            return "N/A"
        return round(float(value), 4) if isinstance(value, (float, int)) else str(value)
    except:
        return "N/A"


async def get_coingecko_24h(coin_id: str, vs_currency="usd"):
    """Fetch 24h market stats from CoinGecko"""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": vs_currency,
        "ids": coin_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        if isinstance(data, list) and len(data) > 0:
            coin = data[0]
            return {
                "high_24h": coin.get("high_24h", "N/A"),
                "low_24h": coin.get("low_24h", "N/A"),
                "volume_24h": coin.get("total_volume", "N/A"),
                "current_price": coin.get("current_price", "N/A"),
                "price_change_24h_pct": coin.get("price_change_percentage_24h", "N/A"),
            }
        elif isinstance(data, dict) and "error" in data:
            logger.warning(f"CoinGecko API error for {coin_id}: {data['error']}")
            return None
        else:
            logger.warning(f"Unexpected CoinGecko response for {coin_id}")
            return None

    except Exception as e:
        logger.exception(f"Failed to fetch CoinGecko data for {coin_id}: {e}")
        return None


# ============================================================================
# MAIN COMMAND HANDLER
# ============================================================================

async def analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    AI Technical Analysis Assistant
    
    Usage:
        /analysis BTC          → BTC analysis on 1h (default)
        /analysis ETH 1h       → ETH analysis on 1 hour
        /analysis SOL 1d       → SOL analysis on daily
    
    Pro Only Feature
    """
    
    # ========================================================================
    # USER VALIDATION
    # ========================================================================
    
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/analysis")
    await handle_streak(update, context)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            format_pro_upsell(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ========================================================================
    # PARSE ARGUMENTS
    # ========================================================================
    
    args = context.args
    if not args:
        await update.message.reply_text(
            format_usage_help(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    symbol = args[0].upper()
    coin_id = COINGECKO_ID_MAP.get(symbol)
    
    if not coin_id:
        await update.message.reply_text(
            f"❌ **Symbol Not Supported**\n\n"
            f"{symbol} is not in our supported coin list.\n\n"
            f"Try: BTC, ETH, BNB, SOL, XRP, ADA, DOGE, MATIC\n\n"
            f"_Supported: Top 200 CoinGecko coins_",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Map timeframe
    timeframe_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "8h": "8h",
        "1d": "1day",
        "1w": "1week"
    }

    user_input_tf = args[1].lower() if len(args) > 1 else "1h"
    
    if user_input_tf not in timeframe_map:
        await update.message.reply_text(
            "❌ **Invalid Timeframe**\n\n"
            "Valid options: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d, 1w\n\n"
            "Example: `/analysis BTC 4h`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    timeframe = timeframe_map[user_input_tf]

    # ========================================================================
    # SHOW LOADING STATE
    # ========================================================================
    
    loading_msg = await update.message.reply_text(
        f"🤖 Analyzing {symbol} market conditions on {user_input_tf}...",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        # ====================================================================
        # FETCH MARKET DATA
        # ====================================================================
        
        # Get technical indicators
        indicators = await get_crypto_indicators(symbol, timeframe)
        if indicators is None:
            await loading_msg.edit_text(
                "⚠️ **Data Unavailable**\n\n"
                f"Could not fetch technical indicators for {symbol}.\n\n"
                "Try a different symbol or timeframe.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Get 24h market stats
        stats_24h = await get_coingecko_24h(coin_id)
        if stats_24h is None:
            stats_24h = {
                "high_24h": "N/A",
                "low_24h": "N/A",
                "volume_24h": "N/A",
                "current_price": indicators.get("price", "N/A"),
                "price_change_24h_pct": "N/A"
            }

        # ====================================================================
        # BUILD AI PROMPT (HONEST & SPECIFIC)
        # ====================================================================
        
        prompt = build_analysis_prompt(symbol, user_input_tf, indicators, stats_24h)

        # ====================================================================
        # GET AI ANALYSIS
        # ====================================================================
        
        analysis_text = await get_ai_analysis(prompt)
        
        if analysis_text is None:
            await loading_msg.edit_text(
                "❌ **Analysis Failed**\n\n"
                "AI service is temporarily unavailable.\n\n"
                "Please try again in a moment.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # ====================================================================
        # FORMAT & SEND RESPONSE
        # ====================================================================
        
        response = format_analysis_response(
            symbol, 
            user_input_tf, 
            indicators, 
            stats_24h, 
            analysis_text
        )
        
        await loading_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        
        # ====================================================================
        # SAVE TO HISTORY (for future accuracy tracking)
        # ====================================================================
        
        try:
            await save_analysis_result(
                user_id=user_id,
                symbol=symbol,
                timeframe=user_input_tf,
                price_at_analysis=stats_24h.get("current_price", 0),
                analysis_text=analysis_text,
                indicators=indicators
            )
        except Exception as e:
            logger.error(f"Failed to save analysis history: {e}")
        
    except Exception as e:
        logger.exception(f"Analysis error for {symbol}: {e}")
        await loading_msg.edit_text(
            "❌ **Error**\n\n"
            f"An unexpected error occurred while analyzing {symbol}.\n\n"
            "Please try again later.",
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================================
# AI PROMPT BUILDER
# ============================================================================

def build_analysis_prompt(symbol: str, timeframe: str, indicators: dict, stats_24h: dict) -> str:
    """
    Build honest, specific prompt for AI analysis
    Focus on interpretation, not prediction
    """
    
    return f"""You are a professional technical analysis assistant helping traders interpret market conditions.

=== TASK ===
Analyze the current technical setup for {symbol} on the {timeframe} timeframe.
Provide a clear, honest interpretation of what the indicators suggest.

=== IMPORTANT RULES ===
1. You are INTERPRETING current conditions, NOT predicting future prices
2. Use language like "suggests", "indicates", "could" - AVOID "will", "definitely", "guaranteed"
3. Acknowledge uncertainty and multiple scenarios
4. Be concise and actionable (max 250 words)
5. No hype or exaggeration - professional tone only

=== MARKET DATA ===

Current Price: ${safe(stats_24h.get('current_price'))}
24h Change: {safe(stats_24h.get('price_change_24h_pct'))}%
24h High/Low: ${safe(stats_24h.get('high_24h'))} / ${safe(stats_24h.get('low_24h'))}
24h Volume: ${safe(stats_24h.get('volume_24h'))}

Technical Indicators:
• RSI(14): {safe(indicators.get('rsi'))}
• EMA(20): ${safe(indicators.get('ema20'))}
• VWAP: ${safe(indicators.get('vwap'))}

MACD:
• MACD Line: {safe(indicators.get('macd'))}
• Signal Line: {safe(indicators.get('macdSignal'))}
• Histogram: {safe(indicators.get('macdHist'))}

Momentum:
• Stochastic K/D: {safe(indicators.get('stochK'))} / {safe(indicators.get('stochD'))}
• CCI: {safe(indicators.get('cci'))}
• ADX: {safe(indicators.get('adx'))}
• MFI: {safe(indicators.get('mfi'))}

Volatility:
• ATR: {safe(indicators.get('atr'))}
• Bollinger Bands: ${safe(indicators.get('bbUpper'))} / ${safe(indicators.get('bbMiddle'))} / ${safe(indicators.get('bbLower'))}

=== REQUIRED OUTPUT FORMAT ===

**Current Momentum:** [Bullish/Bearish/Neutral] + brief why

**Key Observations:**
• [2-3 most important indicator signals]

**What This Suggests:**
[Interpretation of likely scenarios - be balanced, mention risks]

**Timeframe Context:**
[What this {timeframe} setup means for traders - scalp/swing/position]

**Risk Factors:**
[What could invalidate this setup or create unexpected moves]

Remember: You're helping traders understand the current setup, not telling them what WILL happen."""

    return prompt


# ============================================================================
# AI ANALYSIS (with fallback)
# ============================================================================

async def get_ai_analysis(prompt: str) -> str:
    """
    Get AI analysis from OpenRouter (Mixtral)
    Returns analysis text or None on failure
    """
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a professional technical analysis assistant. You interpret market data honestly and never make price predictions. You acknowledge uncertainty and provide balanced analysis."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,  # Balanced creativity
                "max_tokens": 500    # Limit length
            },
            timeout=20
        )

        if response.status_code == 200:
            analysis = response.json()["choices"][0]["message"]["content"].strip()
            return analysis
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.exception(f"AI analysis request failed: {e}")
        return None


# ============================================================================
# RESPONSE FORMATTING
# ============================================================================

def format_analysis_response(
    symbol: str, 
    timeframe: str, 
    indicators: dict, 
    stats_24h: dict, 
    analysis_text: str
) -> str:
    """
    Format the complete analysis response
    Shows key data + AI interpretation + honest disclaimer
    """
    
    current_price = stats_24h.get("current_price", "N/A")
    price_change = stats_24h.get("price_change_24h_pct", "N/A")
    
    # Format price change with emoji
    if price_change != "N/A":
        change_float = float(price_change)
        if change_float > 0:
            change_str = f"+{price_change}% 📈"
        elif change_float < 0:
            change_str = f"{price_change}% 📉"
        else:
            change_str = f"{price_change}% ➡️"
    else:
        change_str = "N/A"
    
    response = f"""**🤖 AI Technical Analysis**

**{symbol}** · {timeframe.upper()} · ${current_price}
24h: {change_str}

━━━━━━━━━━━━━━━━━━━━

{analysis_text}

━━━━━━━━━━━━━━━━━━━━

**📊 Key Indicators**
RSI: {safe(indicators.get('rsi'))} | MACD: {safe(indicators.get('macdHist'))}
Stoch: {safe(indicators.get('stochK'))} | EMA: {safe(indicators.get('ema20'))}

━━━━━━━━━━━━━━━━━━━━

⚠️ **Important Disclaimer**: AI-assisted analysis only — NOT financial advice or a trading signal; use your own judgment."""
    return response


# ============================================================================
# HELPER MESSAGES
# ============================================================================

def format_pro_upsell() -> str:
    """Format Pro upgrade message"""
    return """🔒 **Pro Feature: AI Technical Analysis**

Get AI-powered interpretation of complex market conditions.

**What you get:**
✓ Professional technical analysis in plain English
✓ Multi-indicator interpretation (RSI, MACD, Stoch, etc.)
✓ Momentum and trend assessment
✓ Scenario analysis and risk factors
✓ Timeframe-specific insights
✓ Support for top 200 coins

**What it's NOT:**
✗ Not a price prediction service
✗ Not a guaranteed trading signal
✗ Not a replacement for your analysis

**Honest AI analysis for informed decisions.**

👉 /upgrade to unlock"""


def format_usage_help() -> str:
    """Format usage instructions"""
    return """**🤖 AI Technical Analysis**

Get professional interpretation of market conditions.

**Usage:**
`/analysis <symbol> [timeframe]`

**Examples:**
• `/analysis BTC` — BTC on 1h (default)
• `/analysis ETH 1h` — ETH on 1 hour
• `/analysis SOL 1d` — SOL on daily

**Timeframes:**
1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d, 1w

**Supported Coins:**
Top 200 CoinGecko (BTC, ETH, BNB, SOL, XRP, ADA, etc.)

**Note:** This is technical analysis interpretation, not price prediction."""
