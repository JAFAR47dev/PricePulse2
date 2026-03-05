from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional, Dict, List
from models.user_activity import update_last_active
from services.signal_data import fetch_top_100_indicator_data
from services.pre_score_engine import rank_top_setups
from services.ai_postprocess import post_process_and_rank
from tasks.handlers import handle_streak
# Signal display configuration
SIGNAL_EMOJI = {
    "BUY": "🟢",
    "SELL": "🔴",
    "HOLD": "🟡"
}

# User tier configuration
TIER_CONFIG = {
    "free": {
        "max_signals": 3,
        "show_exact_confidence": False,
        "tier_name": "Free"
    },
    "pro": {
        "max_signals": 10,
        "show_exact_confidence": True,
        "tier_name": "Pro"
    }
}

# Valid timeframes
VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}


def get_user_tier(user_id: int) -> str:
    """
    Determine user's subscription tier.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Tier name ("free" or "pro")
    """
    from models.user import get_user_plan
    from utils.auth import is_pro_plan
    
    try:
        plan = get_user_plan(user_id)
        
        if is_pro_plan(plan):
            return "pro"
        else:
            return "free"
            
    except Exception:
        # Default to free on any error
        return "free"

def format_confidence(confidence: int, show_exact: bool) -> str:
    """
    Format confidence value based on user tier.
    
    Args:
        confidence: Confidence value (0-100)
        show_exact: Whether to show exact percentage
        
    Returns:
        Formatted confidence string
    """
    if show_exact:
        return f"{confidence}%"
    
    # Convert to Low/Med/High for free users
    if confidence >= 70:
        return "High"
    elif confidence >= 50:
        return "Med"
    else:
        return "Low"


def format_trend(strength: float) -> str:
    """
    Format trend strength into readable text.
    
    Args:
        strength: Trend strength value (0.0-1.0)
        
    Returns:
        Formatted trend string
    """
    if not isinstance(strength, (int, float)):
        return "Unknown"
    
    if strength >= 0.7:
        return "Strong"
    elif strength >= 0.4:
        return "Moderate"
    else:
        return "Weak"


def validate_timeframe(timeframe: str) -> Optional[str]:
    """
    Validate and normalize timeframe input.
    
    Args:
        timeframe: User-provided timeframe string
        
    Returns:
        Normalized timeframe or None if invalid
    """
    if not isinstance(timeframe, str):
        return None
    
    normalized = timeframe.lower().strip()
    
    if normalized in VALID_TIMEFRAMES:
        return normalized
    
    return None


def build_upgrade_message() -> str:
    """
    Build upgrade prompt for free users.
    
    Returns:
        Formatted upgrade message
    """
    return (
        "\n\n🌟 *Upgrade to Pro for:*\n"
        "  • 10 signals instead of 3\n"
        "  • Exact confidence percentages\n"
        "\n"
        "Type /upgrade to learn more!"
    )


def format_signal_output(
    signals: List[Dict],
    timeframe: str,
    user_tier: str
) -> str:
    """
    Format signals for display based on user tier.
    
    Args:
        signals: List of signal dictionaries
        timeframe: Trading timeframe
        user_tier: User's tier ("free" or "pro")
        
    Returns:
        Formatted message string
    """
    if not signals:
        return "⚠️ No high-confidence signals detected."
    
    config = TIER_CONFIG.get(user_tier, TIER_CONFIG["free"])
    show_exact = config["show_exact_confidence"]
    
    # Build header
    lines = [
        f"📊 *AI Trading Signals*  ({timeframe.upper()})",
        f"👤 Tier: {config['tier_name']}",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]
    
    # Add signals
    for i, s in enumerate(signals, 1):
        try:
            # Safe field extraction
            symbol = s.get("symbol", "UNKNOWN")
            signal = s.get("signal", "HOLD")
            confidence = s.get("confidence", 0)
            risk = s.get("risk", "medium")
            trend_strength = s.get("trend_strength", 0)
            
            # Validate signal type
            emoji = SIGNAL_EMOJI.get(signal, "⚪")
            
            # Format confidence based on tier
            confidence_str = format_confidence(confidence, show_exact)
            
            # Format trend
            trend = format_trend(trend_strength)
            
            # Build signal line
            lines.extend([
                f"{emoji} *{symbol}*  —  *{signal}*  |  *{confidence_str}*",
                f"Trend: {trend}  |  Risk: {risk.capitalize()}",
                ""
            ])
            
        except Exception:
            # Skip malformed signals
            continue
    
    # Add footer
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Educational purposes only. Not financial advice._"
    ])
    
    # Add upgrade prompt for free users
    if user_tier == "free":
        lines.append(build_upgrade_message())
    
    return "\n".join(lines)


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /signals command with tier-based restrictions.
    
    Args:
        update: Telegram update object
        context: Telegram context object
    """
    # Validate update and message
    if not update or not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    user_id = user.id
    await update_last_active(user_id, command_name="/signals")
    await handle_streak(update, context)
   
    # Get user tier
    user_tier = get_user_tier(user_id)
    tier_config = TIER_CONFIG.get(user_tier, TIER_CONFIG["free"])
    
    # Parse and validate timeframe
    timeframe = None
    if context.args and len(context.args) > 0:
        timeframe = validate_timeframe(context.args[0])
    
    if not timeframe:
        timeframe = "1h"  # Default timeframe
    
    # Send loading message
    try:
        loading = await update.message.reply_text(
            "📡 Scanning AI market signals...",
            parse_mode="Markdown"
        )
    except Exception:
        return  # Failed to send message
    
    try:
        # ────────────────────────────
        # PHASE 1 — FETCH DATA
        # ────────────────────────────
        raw_data = await fetch_top_200_indicator_data(timeframe=timeframe)
        
        if not raw_data or not isinstance(raw_data, list):
            await loading.edit_text(
                "⚠️ Market data unavailable. Try again later.",
                parse_mode="Markdown"
            )
            return
        
        # ─────────────────────────────
        # PHASE 2 — PRE-SCORE
        # ─────────────────────────────
        top_candidates = rank_top_setups(raw_data, top_n=30)
        
        if not top_candidates or not isinstance(top_candidates, list):
            await loading.edit_text(
                "⚠️ No viable setups found.",
                parse_mode="Markdown"
            )
            return
        
        # ─────────────────────────────────────
        # PHASE 3 + 4 — AI + POST-PROCESS
        # ─────────────────────────────────────
        # Request more signals than needed, then trim by tier
        max_signals = tier_config["max_signals"]
        
        final_signals = post_process_and_rank(
            pre_scored_coins=top_candidates,
            timeframe=timeframe,
            top_n=max_signals,  # Request only what user can see
            min_confidence=30,
            use_fallback=True
        )
        
        if not final_signals or not isinstance(final_signals, list):
            await loading.edit_text(
                "⚠️ No high-confidence signals detected.",
                parse_mode="Markdown"
            )
            return
        
        # ─────────────────────────────
        # PHASE 5 — TIER-BASED OUTPUT
        # ─────────────────────────────
        # Trim to tier limit (defensive, already limited in post_process)
        final_signals = final_signals[:max_signals]
        
        # Format output based on tier
        output = format_signal_output(
            signals=final_signals,
            timeframe=timeframe,
            user_tier=user_tier
        )
        
        # Send formatted message
        await loading.edit_text(
            output,
            parse_mode="Markdown"
        )
        
    except ValueError as e:
        # Handle validation errors
        await loading.edit_text(
            f"⚠️ Invalid input: {str(e)}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        # Handle unexpected errors
        error_msg = (
            "⚠️ An error occurred while processing signals.\n"
            "Please try again later."
        )
        
        try:
            await loading.edit_text(error_msg, parse_mode="Markdown")
        except Exception:
            pass  # Failed to send error message


async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /upgrade command to show Pro tier benefits.
    
    Args:
        update: Telegram update object
        context: Telegram context object
    """
    if not update or not update.message:
        return
    
    upgrade_text = (
        "🌟 *Upgrade to Pro*\n\n"
        "*Benefits:*\n"
        "  • 10 signals (vs 3 free)\n"
        "  • Exact confidence percentages\n"
        
    )
    
    try:
        await update.message.reply_text(
            upgrade_text,
            parse_mode="Markdown"
        )
    except Exception:
        pass


# Helper function for testing user tier updates
def set_user_tier(user_id: int, tier: str) -> bool:
    """
    Set user tier (for admin/testing purposes).
    
    Args:
        user_id: Telegram user ID
        tier: Tier to set ("free" or "pro")
        
    Returns:
        True if successful, False otherwise
        
    Note:
        Implement actual database update logic here
    """
    if tier not in TIER_CONFIG:
        return False
    
    # TODO: Implement database update
    # Example:
    # db.update_user_tier(user_id, tier)
    
    return True