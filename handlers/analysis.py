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
from typing import Optional, Dict, Any
from functools import lru_cache
    
logger = logging.getLogger(__name__)

# Load supported coins (top 200)
COINGECKO_IDS_PATH = os.path.join("services", "top200_coingecko_ids.json")
with open(COINGECKO_IDS_PATH, "r") as f:
    COINGECKO_ID_MAP = json.load(f)

# CoinGecko API Configuration
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"


def safe(value: Any) -> str:
    """Safely format indicator values with improved type handling"""
    if value is None or value == "N/A":
        return "N/A"
    
    try:
        if isinstance(value, (float, int)):
            # Format large numbers with commas
            if abs(value) >= 1000:
                return f"{value:,.2f}"
            return f"{value:.4f}"
        return str(value)
    except (ValueError, TypeError):
        return "N/A"


def format_large_number(value: Any) -> str:
    """Format large numbers (volume, market cap) with K/M/B notation"""
    if value is None or value == "N/A":
        return "N/A"
    
    try:
        num = float(value)
        if num >= 1_000_000_000:
            return f"${num / 1_000_000_000:.2f}B"
        elif num >= 1_000_000:
            return f"${num / 1_000_000:.2f}M"
        elif num >= 1_000:
            return f"${num / 1_000:.2f}K"
        return f"${num:.2f}"
    except (ValueError, TypeError):
        return "N/A"


async def get_coingecko_24h(coin_id: str, vs_currency: str = "usd") -> Optional[Dict[str, Any]]:
    """
    Fetch 24h market stats from CoinGecko using Demo API key
    
    Args:
        coin_id: CoinGecko coin ID (e.g., 'bitcoin')
        vs_currency: Quote currency (default: 'usd')
    
    Returns:
        Dict with market data or None on failure
    """
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    params = {
        "vs_currency": vs_currency,
        "ids": coin_id,
        "order": "market_cap_desc",
        "per_page": 1,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h"
    }
    
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params, headers=headers)
            
            # Check for rate limiting
            if resp.status_code == 429:
                logger.warning(f"CoinGecko rate limit hit for {coin_id}")
                return None
            
            resp.raise_for_status()
            data = resp.json()

        if isinstance(data, list) and len(data) > 0:
            coin = data[0]
            return {
                "current_price": coin.get("current_price"),
                "high_24h": coin.get("high_24h"),
                "low_24h": coin.get("low_24h"),
                "volume_24h": coin.get("total_volume"),
                "market_cap": coin.get("market_cap"),
                "price_change_24h": coin.get("price_change_24h"),
                "price_change_24h_pct": coin.get("price_change_percentage_24h"),
                "circulating_supply": coin.get("circulating_supply"),
                "total_supply": coin.get("total_supply"),
                "ath": coin.get("ath"),
                "ath_change_percentage": coin.get("ath_change_percentage"),
                "atl": coin.get("atl"),
                "atl_change_percentage": coin.get("atl_change_percentage"),
            }
        
        # Handle API errors
        if isinstance(data, dict) and "error" in data:
            logger.warning(f"CoinGecko API error for {coin_id}: {data['error']}")
            return None
        
        # Empty response
        logger.warning(f"No data returned from CoinGecko for {coin_id}")
        return None

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching CoinGecko data for {coin_id}: {e.response.status_code}")
        return None
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching CoinGecko data for {coin_id}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching CoinGecko data for {coin_id}: {e}")
        return None


@lru_cache(maxsize=128)
def get_timeframe_display(tf: str) -> str:
    """Convert timeframe code to display format"""
    display_map = {
        "1m": "1 Minute",
        "5m": "5 Minutes",
        "15m": "15 Minutes",
        "30m": "30 Minutes",
        "1h": "1 Hour",
        "2h": "2 Hours",
        "4h": "4 Hours",
        "8h": "8 Hours",
        "1d": "Daily",
        "1w": "Weekly"
    }
    return display_map.get(tf, tf.upper())


# ============================================================================
# MAIN COMMAND HANDLER
# ============================================================================

async def analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main handler for /analysis command with improved error handling
    """
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
            f"`{symbol}` is not in our supported coin list.\n\n"
            f"**Popular Symbols:**\n"
            f"BTC, ETH, BNB, SOL, XRP, ADA, DOGE, MATIC, DOT, LINK\n\n"
            f"_We support the top 200 CoinGecko coins_",
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
            "**Valid options:**\n"
            "`1m` `5m` `15m` `30m` `1h` `2h` `4h` `8h` `1d` `1w`\n\n"
            "**Example:** `/analysis BTC 4h`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    timeframe = timeframe_map[user_input_tf]
    timeframe_display = get_timeframe_display(user_input_tf)

    # ========================================================================
    # SHOW LOADING STATE
    # ========================================================================
    
    loading_msg = await update.message.reply_text(
        f"🔍 Analyzing **{symbol}** on {timeframe_display}...\n\n"
        f"_Fetching market data and indicators..._",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        # ====================================================================
        # FETCH MARKET DATA (Parallel)
        # ====================================================================
        
        # Run both API calls concurrently
        import asyncio
        indicators_task = get_crypto_indicators(symbol, timeframe)
        coingecko_task = get_coingecko_24h(coin_id)
        
        indicators, stats_24h = await asyncio.gather(
            indicators_task,
            coingecko_task,
            return_exceptions=True
        )
        
        # Handle indicators fetch failure
        if isinstance(indicators, Exception) or indicators is None:
            await loading_msg.edit_text(
                f"⚠️ **Technical Data Unavailable**\n\n"
                f"Could not fetch technical indicators for **{symbol}**.\n\n"
                f"This could be due to:\n"
                f"• Insufficient price history for {timeframe_display}\n"
                f"• Temporary data provider issue\n\n"
                f"**Try:**\n"
                f"• A different timeframe (e.g., `/analysis {symbol} 1h`)\n"
                f"• A different symbol",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Handle CoinGecko failure (use fallback)
        if isinstance(stats_24h, Exception) or stats_24h is None:
            logger.warning(f"CoinGecko API failed for {coin_id}, using fallback data")
            stats_24h = {
                "current_price": indicators.get("price"),
                "high_24h": "N/A",
                "low_24h": "N/A",
                "volume_24h": "N/A",
                "market_cap": "N/A",
                "price_change_24h": "N/A",
                "price_change_24h_pct": "N/A",
            }

        # ====================================================================
        # BUILD AI PROMPT
        # ====================================================================
        
        prompt = build_analysis_prompt(symbol, user_input_tf, timeframe_display, indicators, stats_24h)

        # ====================================================================
        # GET AI ANALYSIS
        # ====================================================================
        
        analysis_text = await get_ai_analysis(prompt)
        
        if analysis_text is None:
            await loading_msg.edit_text(
                "❌ **AI Analysis Failed**\n\n"
                "The AI service is temporarily unavailable.\n\n"
                "Please try again in a few moments.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # ====================================================================
        # FORMAT & SEND RESPONSE
        # ====================================================================
        
        response = format_analysis_response(
            symbol, 
            user_input_tf,
            timeframe_display,
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
        logger.exception(f"Critical analysis error for {symbol}: {e}")
        await loading_msg.edit_text(
            f"❌ **Unexpected Error**\n\n"
            f"An error occurred while analyzing **{symbol}**.\n\n"
            f"Our team has been notified. Please try again later.",
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================================
# AI PROMPT BUILDER
# ============================================================================

def build_analysis_prompt(
    symbol: str, 
    timeframe: str, 
    timeframe_display: str,
    indicators: Dict[str, Any], 
    stats_24h: Dict[str, Any]
) -> str:
    """
    Build comprehensive, honest prompt for AI analysis
    """
    
    # Calculate some derived metrics
    price = stats_24h.get("current_price")
    ema20 = indicators.get("ema20")
    vwap = indicators.get("vwap")
    
    price_vs_ema = "N/A"
    price_vs_vwap = "N/A"
    
    if price and ema20:
        try:
            diff_pct = ((float(price) - float(ema20)) / float(ema20)) * 100
            price_vs_ema = f"{diff_pct:+.2f}%"
        except:
            pass
    
    if price and vwap:
        try:
            diff_pct = ((float(price) - float(vwap)) / float(vwap)) * 100
            price_vs_vwap = f"{diff_pct:+.2f}%"
        except:
            pass
    
    return f"""You are a professional technical analysis assistant interpreting market data for cryptocurrency traders.

=== TASK ===
Analyze the current technical setup for {symbol} on the {timeframe_display} timeframe.
Provide clear, actionable interpretation of what the indicators collectively suggest.

=== CRITICAL RULES ===
1. INTERPRET current conditions - do NOT predict prices
2. Use measured language: "suggests", "indicates", "could" - NEVER "will", "guaranteed"
3. Acknowledge uncertainty and present multiple scenarios
4. Be concise (200-250 words max) and actionable
5. Professional tone - no hype, no sensationalism
6. Focus on CONFLUENCE of indicators, not individual readings

=== MARKET SNAPSHOT ===

**Price Action:**
Current: ${safe(stats_24h.get('current_price'))}
24h Change: {safe(stats_24h.get('price_change_24h_pct'))}% (${safe(stats_24h.get('price_change_24h'))})
24h Range: ${safe(stats_24h.get('low_24h'))} - ${safe(stats_24h.get('high_24h'))}
24h Volume: {format_large_number(stats_24h.get('volume_24h'))}
Market Cap: {format_large_number(stats_24h.get('market_cap'))}

**Technical Indicators ({timeframe_display}):**

Trend & Moving Averages:
• Price vs EMA(20): {price_vs_ema}
• Price vs VWAP: {price_vs_vwap}
• EMA(20): ${safe(ema20)}
• VWAP: ${safe(vwap)}

Momentum:
• RSI(14): {safe(indicators.get('rsi'))} [<30=Oversold, >70=Overbought]
• Stochastic K/D: {safe(indicators.get('stochK'))} / {safe(indicators.get('stochD'))}
• CCI: {safe(indicators.get('cci'))} [>100=Overbought, <-100=Oversold]
• MFI: {safe(indicators.get('mfi'))} [Money Flow Index]

MACD:
• MACD Line: {safe(indicators.get('macd'))}
• Signal Line: {safe(indicators.get('macdSignal'))}
• Histogram: {safe(indicators.get('macdHist'))} [Positive=Bullish, Negative=Bearish]

Trend Strength:
• ADX: {safe(indicators.get('adx'))} [<20=Weak, 20-40=Strong, >40=Very Strong]

Volatility:
• ATR: {safe(indicators.get('atr'))}
• Bollinger Bands:
  - Upper: ${safe(indicators.get('bbUpper'))}
  - Middle: ${safe(indicators.get('bbMiddle'))}
  - Lower: ${safe(indicators.get('bbLower'))}

=== REQUIRED OUTPUT FORMAT ===

**Momentum:** [Bullish/Bearish/Neutral/Mixed] + 1-sentence rationale

**Key Technical Signals:**
• [Most important confluence of 2-3 indicators]
• [What they collectively suggest about direction/strength]

**Market Context:**
[Brief interpretation: is price trending/ranging? Strong/weak momentum? Any divergences?]

**{timeframe_display} Trading Implications:**
[What this setup means for traders on this timeframe - scalp/swing/position context]

**Risk Considerations:**
[Key levels or conditions that could invalidate this setup]

Remember: Interpret what IS, not what WILL BE. Help traders understand the current setup."""

    return prompt


# ============================================================================
# AI ANALYSIS
# ============================================================================

async def get_ai_analysis(prompt: str) -> Optional[str]:
    """
    Get AI analysis from OpenRouter with improved error handling
    """
    api_key = os.getenv('OPENROUTER_API_KEY')
    
    if not api_key:
        logger.error("OPENROUTER_API_KEY not configured")
        return None
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("APP_URL", "https://your-bot.com"),
                "X-Title": "Crypto Analysis Bot"
            },
            json={
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a professional cryptocurrency technical analyst. "
                            "You interpret market data objectively and never make price predictions. "
                            "You acknowledge uncertainty and provide balanced, multi-scenario analysis. "
                            "Your goal is to help traders understand current market conditions, not to guess future prices."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.6,  # Slightly lower for more consistent analysis
                "max_tokens": 600,
                "top_p": 0.9
            },
            timeout=25
        )

        if response.status_code == 200:
            data = response.json()
            analysis = data["choices"][0]["message"]["content"].strip()
            
            # Basic validation
            if len(analysis) < 50:
                logger.warning("AI returned suspiciously short analysis")
                return None
                
            return analysis
            
        elif response.status_code == 429:
            logger.error("OpenRouter rate limit exceeded")
            return None
        elif response.status_code == 401:
            logger.error("OpenRouter API key invalid")
            return None
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            return None

    except requests.Timeout:
        logger.error("OpenRouter request timeout")
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
    timeframe_display: str,
    indicators: Dict[str, Any], 
    stats_24h: Dict[str, Any], 
    analysis_text: str
) -> str:
    """
    Format comprehensive analysis response with better layout
    """
    
    current_price = stats_24h.get("current_price", "N/A")
    price_change = stats_24h.get("price_change_24h_pct", "N/A")
    
    # Format price change with emoji
    change_str = "N/A"
    if price_change != "N/A":
        try:
            change_float = float(price_change)
            if change_float > 0:
                change_str = f"+{price_change:.2f}% 📈"
            elif change_float < 0:
                change_str = f"{price_change:.2f}% 📉"
            else:
                change_str = f"{price_change:.2f}% ➡️"
        except:
            pass
    
    # Format volume
    volume_str = format_large_number(stats_24h.get("volume_24h"))
    
    response = f"""**🤖 AI Technical Analysis**

**{symbol}** · {timeframe_display}
💰 ${safe(current_price)} · 24h: {change_str}
📊 Volume: {volume_str}

━━━━━━━━━━━━━━━━━━━━

{analysis_text}

━━━━━━━━━━━━━━━━━━━━

**📈 Quick Indicators**
RSI: `{safe(indicators.get('rsi'))}` | MACD Hist: `{safe(indicators.get('macdHist'))}`
Stoch: `{safe(indicators.get('stochK'))}` | ADX: `{safe(indicators.get('adx'))}`

━━━━━━━━━━━━━━━━━━━━

⚠️ **Disclaimer:** AI interpretation of technical data — NOT financial advice. Markets are unpredictable; always do your own research."""
    
    return response


# ============================================================================
# HELPER MESSAGES
# ============================================================================

def format_pro_upsell() -> str:
    """Enhanced Pro upgrade message"""
    return """🔒 **Pro Feature: AI Technical Analysis**

Get professional AI-powered interpretation of complex market conditions.

**What You Get:**
✅ Multi-indicator confluence analysis
✅ Momentum & trend strength assessment
✅ Context-aware scenario analysis
✅ Risk factor identification
✅ Timeframe-specific trading insights
✅ Support for top 200 cryptocurrencies

**What It's NOT:**
❌ Price predictions or guarantees
❌ Trading signals you should blindly follow
❌ A replacement for your own research

**Honest, professional analysis to support YOUR decisions.**

👉 Use `/upgrade` to unlock Pro features"""


def format_usage_help() -> str:
    """Enhanced usage instructions"""
    return """**🤖 AI Technical Analysis**

Get professional AI interpretation of technical indicators.

**Usage:**
`/analysis <SYMBOL> [timeframe]`

**Examples:**
• `/analysis BTC` → Bitcoin (1h default)
• `/analysis ETH 4h` → Ethereum (4 hour)
• `/analysis SOL 1d` → Solana (daily)

**Supported Timeframes:**
`1m` `5m` `15m` `30m` `1h` `2h` `4h` `8h` `1d` `1w`

**Supported Coins:**
Top 200 by market cap (BTC, ETH, BNB, SOL, XRP, ADA, DOT, MATIC, LINK, UNI, AVAX, etc.)

**Note:** This provides technical interpretation, NOT price predictions.

📊 **Pro Tip:** Combine multiple timeframes for better context!"""

