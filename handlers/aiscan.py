import os
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.ohlcv import fetch_candles
from utils.patterns import (
    detect_divergences,
    detect_engulfing_patterns,
    detect_trendline_breaks,
    detect_golden_death_crosses,
    detect_double_top_bottom
)
import datetime
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak
    
VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]

# ============================================================================
# DYNAMIC PATTERN COUNT BASED ON TIMEFRAME
# ============================================================================

def get_pattern_limits(timeframe: str) -> dict:
    """
    Determine how many patterns to analyze based on timeframe.
    
    Logic:
    - Shorter timeframes = fewer patterns (noise filter)
    - Longer timeframes = more patterns (broader context)
    
    Returns:
        dict with 'recent_patterns' and 'lookback_candles'
    """
    limits = {
        # Ultra-short timeframes (scalping) - focus on immediate action
        "1m": {
            "recent_patterns": 3,      # Only last 3 patterns (5-15 min window)
            "lookback_candles": 50,    # ~50 minutes of data
            "ai_focus": "immediate momentum and micro-structure"
        },
        
        # Short timeframes (day trading) - recent context matters most
        "5m": {
            "recent_patterns": 5,      # Last 5 patterns (~25-50 min)
            "lookback_candles": 100,   # ~8 hours of data
            "ai_focus": "short-term momentum and key support/resistance"
        },
        
        "15m": {
            "recent_patterns": 7,      # Last 7 patterns (~1.5-3 hours)
            "lookback_candles": 100,   # ~24 hours of data
            "ai_focus": "intraday trend and breakout potential"
        },
        
        "30m": {
            "recent_patterns": 8,      # Last 8 patterns (~4-6 hours)
            "lookback_candles": 150,   # ~3 days of data
            "ai_focus": "swing setup quality and trend strength"
        },
        
        # Medium timeframes (swing trading) - balanced view
        "1h": {
            "recent_patterns": 10,     # Last 10 patterns (~10-20 hours)
            "lookback_candles": 200,   # ~8 days of data
            "ai_focus": "swing trade setups and major pattern confluence"
        },
        
        "2h": {
            "recent_patterns": 12,     # Last 12 patterns (~1-2 days)
            "lookback_candles": 200,   # ~16 days of data
            "ai_focus": "multi-day trend and key reversal signals"
        },
        
        "4h": {
            "recent_patterns": 15,     # Last 15 patterns (~2-4 days)
            "lookback_candles": 250,   # ~1 month of data
            "ai_focus": "weekly trend direction and major pattern clusters"
        },
        
        # Long timeframes (position trading) - comprehensive analysis
        "8h": {
            "recent_patterns": 18,     # Last 18 patterns (~6-10 days)
            "lookback_candles": 250,   # ~2 months of data
            "ai_focus": "monthly trend and significant reversals"
        },
        
        "1d": {
            "recent_patterns": 20,     # Last 20 patterns (~3-4 weeks)
            "lookback_candles": 300,   # ~10 months of data
            "ai_focus": "long-term trend structure and macro patterns"
        }
    }
    
    return limits.get(timeframe, limits["1h"])  # Default to 1h if unknown


async def aiscan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)
    await update_last_active(user_id, command_name="/aiscan")
    await handle_streak(update, context)
    
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This is a *Pro-only* feature.\nUpgrade to unlock AI Pattern Scanner.\n\n👉 /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    args = context.args
    if len(args) < 1:
        return await update.message.reply_text(
            "❌ Usage: /aiscan BTC [timeframe]\nExample: /aiscan ETH 1h"
        )

    symbol = args[0].upper()
    tf = args[1] if len(args) > 1 else "1h"

    if tf not in VALID_TIMEFRAMES:
        return await update.message.reply_text(
            "❌ Invalid timeframe. Choose from: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d"
        )

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # ═══════════════════════════════════════════════════════════════════════
    # GET DYNAMIC LIMITS FOR THIS TIMEFRAME
    # ═══════════════════════════════════════════════════════════════════════
    limits = get_pattern_limits(tf)
    pattern_limit = limits["recent_patterns"]
    lookback_candles = limits["lookback_candles"]
    ai_focus = limits["ai_focus"]
    
    # Fetch candles with dynamic lookback
    candles = await fetch_candles(symbol, tf, limit=lookback_candles)
    if not candles:
        return await update.message.reply_text("⚠️ Failed to fetch chart data.")

    # Validate candle data quality
    min_candles = max(50, lookback_candles // 2)  # At least 50 or half of requested
    if len(candles) < min_candles:
        return await update.message.reply_text(
            f"⚠️ Insufficient data for {tf} analysis. Try a different timeframe."
        )

    # ═══════════════════════════════════════════════════════════════════════
    # DETECT ALL PATTERNS (FULL DATASET)
    # ═══════════════════════════════════════════════════════════════════════
    all_patterns = (
        detect_divergences(candles)
        + detect_engulfing_patterns(candles)
        + detect_trendline_breaks(candles)
        + detect_golden_death_crosses(candles)
        + detect_double_top_bottom(candles)
    )

    # ═══════════════════════════════════════════════════════════════════════
    # FILTER TO MOST RECENT PATTERNS (DYNAMIC BASED ON TIMEFRAME)
    # ═══════════════════════════════════════════════════════════════════════
    recent_patterns = all_patterns[-pattern_limit:] if all_patterns else []

    # Log patterns with timeframe context
    if recent_patterns:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("\n🧠 [AI Pattern Spotter Log]")
        print(f"Time: {timestamp}")
        print(f"Symbol: {symbol} | Timeframe: {tf}")
        print(f"Pattern Limit: {pattern_limit} (optimized for {tf})")
        print(f"Detected {len(all_patterns)} total patterns (analyzing most recent {len(recent_patterns)}):")

        for i, p in enumerate(recent_patterns, 1):
            print(f"  {i}. {p}")

        print("-" * 50)

        # Show user the patterns
        formatted_patterns = "\n".join([f"• {p}" for p in recent_patterns])
        
        timeframe_context = ""
        if tf in ["1m", "5m"]:
            timeframe_context = "\n\n⚡ *Scalping timeframe* - Focus on immediate 3-5 patterns only"
        elif tf in ["15m", "30m", "1h"]:
            timeframe_context = "\n\n📊 *Swing timeframe* - Recent patterns show emerging setup"
        elif tf in ["4h", "8h", "1d"]:
            timeframe_context = "\n\n📈 *Position timeframe* - Broader pattern context analyzed"
        
        await update.message.reply_text(
            f"📊 *Top {len(recent_patterns)} Patterns for {symbol} ({tf})*{timeframe_context}\n\n{formatted_patterns}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        print(f"🧠 [{symbol} {tf}] No major patterns detected in {lookback_candles} candles.")
        await update.message.reply_text(
            f"✅ No major chart patterns detected on {tf} timeframe.\n\n"
            f"💡 Try a different timeframe or check back later."
        )
        return
        
    # ═══════════════════════════════════════════════════════════════════════
    # AI ANALYSIS - ONLY ON RECENT PATTERNS
    # ═══════════════════════════════════════════════════════════════════════
    summary = await get_ai_pattern_summary(
        symbol, 
        tf, 
        recent_patterns,  # Only analyze recent patterns
        candles,
        ai_focus  # Pass timeframe-specific focus
    )

    if summary:
        await update.message.reply_text(
            f"🤖 *AI Analysis ({tf} timeframe):*\n\n{summary}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "⚠️ AI summary unavailable. Pattern list shown above."
        )
    

# ============================================================================
# AI SUMMARY WITH TIMEFRAME-AWARE ANALYSIS
# ============================================================================

async def get_ai_pattern_summary(symbol, timeframe, patterns, candles, ai_focus):
    """
    Generate AI summary with timeframe-specific context
    
    Args:
        symbol: Trading pair
        timeframe: Chart timeframe
        patterns: List of detected patterns (already filtered to recent)
        candles: OHLCV data
        ai_focus: What the AI should focus on for this timeframe
    """
    if not patterns:
        return None
    
    # Get actual market data for grounding
    latest_close = candles[-1]['close']
    
    # Calculate price change over relevant period
    # Use different lookback periods based on timeframe
    lookback_map = {
        "1m": 20,   # 20 minutes
        "5m": 20,   # 100 minutes (~1.5 hours)
        "15m": 20,  # 5 hours
        "30m": 20,  # 10 hours
        "1h": 24,   # 1 day
        "2h": 24,   # 2 days
        "4h": 30,   # 5 days
        "8h": 30,   # 10 days
        "1d": 30    # 1 month
    }
    
    lookback = lookback_map.get(timeframe, 20)
    price_change_pct = ((candles[-1]['close'] - candles[-lookback]['close']) / candles[-lookback]['close']) * 100
    
    pattern_text = "\n".join(f"- {p}" for p in patterns)
    
    # ═══════════════════════════════════════════════════════════════════════
    # TIMEFRAME-SPECIFIC PROMPT
    # ═══════════════════════════════════════════════════════════════════════
    
    # Adjust analysis depth based on timeframe
    if timeframe in ["1m", "5m"]:
        analysis_depth = "immediate"
        word_limit = 200
        instructions = (
            "This is a SCALPING timeframe. Focus on:\n"
            "- Immediate momentum (next 15-60 minutes)\n"
            "- Quick entry/exit signals\n"
            "- Avoid long-term projections\n"
            "- Emphasize risk of rapid reversals"
        )
    elif timeframe in ["15m", "30m", "1h"]:
        analysis_depth = "short-term"
        word_limit = 250
        instructions = (
            "This is a DAY/SWING timeframe. Focus on:\n"
            "- Intraday trend direction\n"
            "- Key support/resistance for today/this week\n"
            "- Setup quality for swing entries\n"
            "- Mention if waiting for confirmation is wise"
        )
    else:  # 2h, 4h, 8h, 1d
        analysis_depth = "long-term"
        word_limit = 300
        instructions = (
            "This is a POSITION timeframe. Focus on:\n"
            "- Multi-day to weekly trend structure\n"
            "- Major reversal vs continuation patterns\n"
            "- Strategic positioning advice\n"
            "- Broader market context"
        )

    prompt = f"""You are a crypto technical analyst. Analyze ONLY the patterns provided below for {timeframe} timeframe.

Market: {symbol}
Timeframe: {timeframe} ({analysis_depth} analysis)
Current Price: ${latest_close:.2f}
Recent Price Change: {price_change_pct:+.2f}% (last {lookback} periods)

Detected Patterns (most recent {len(patterns)}):
{pattern_text}

ANALYSIS FOCUS FOR {timeframe.upper()}:
{instructions}

AI Focus Area: {ai_focus}

STRICT RULES:
1. Base analysis ONLY on patterns listed above
2. Do NOT mention patterns not in the list
3. Do NOT make specific price targets
4. Do NOT guarantee outcomes
5. Adjust timeframe expectations correctly:
   - 1m/5m: Talk about minutes/hours
   - 15m/1h: Talk about hours/days
   - 4h/1d: Talk about days/weeks

Provide an adequate but concise word summary covering:
- What these patterns indicate for {timeframe} traders
- Which side (bulls/bears) has technical advantage
- The most significant pattern from the list
- Actionable guidance for {analysis_depth} timeframe

End with: "This is pattern analysis for {timeframe} timeframe, not financial advice."
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
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,  # Lower temperature = less creative/hallucinatory
                "max_tokens": word_limit + 50,  # Dynamic based on timeframe
                "top_p": 0.9
            },
            timeout=20
        )

        if response.status_code == 200:
            ai_response = response.json()["choices"][0]["message"]["content"].strip()
            
            # Validation: Check if AI stayed on topic
            forbidden_phrases = [
                "will reach",
                "target price",
                "guaranteed",
                "definitely will",
                "100% certain",
                "investment advice"
            ]
            
            ai_lower = ai_response.lower()
            for phrase in forbidden_phrases:
                if phrase in ai_lower:
                    print(f"⚠️ AI response contained forbidden phrase: {phrase}")
                    return None
            
            return ai_response
        else:
            print("AI response error:", response.status_code, response.text)
            return None

    except requests.Timeout:
        print("AI summary timeout")
        return None
    except Exception as e:
        print("AI summary exception:", e)
        return None
