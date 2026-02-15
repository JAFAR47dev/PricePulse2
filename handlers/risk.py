from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak


async def risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /risk command - Position sizing and risk management calculator
    
    Free users: Basic calculation
    Pro users: Advanced calculations with multiple scenarios
    
    Usage:
        /risk [account_size] [risk_%] [entry_price] [stop_loss]
    
    Examples:
        /risk 10000 2 - Basic: account and risk %
        /risk 10000 2 50000 48000 - Full: with entry and stop loss
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/risk")
    await handle_streak(update, context)
    
    plan = get_user_plan(user_id)
    is_pro = is_pro_plan(plan)
    
    # Parse arguments
    args = context.args
    
    if not args:
        await update.message.reply_text(
            format_usage_guide(is_pro),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Validate arguments
    try:
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Missing required parameters\n\n"
                "**Usage:** `/risk [account_size] [risk_%]`\n"
                "**Example:** `/risk 10000 2`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        account_size = float(args[0])
        risk_percent = float(args[1])
        
        # Optional parameters for pro/advanced calculation
        entry_price = float(args[2]) if len(args) >= 3 else None
        stop_loss = float(args[3]) if len(args) >= 4 else None
        
        # Validation
        if account_size <= 0:
            await update.message.reply_text("❌ Account size must be positive")
            return
        
        if risk_percent <= 0 or risk_percent > 100:
            await update.message.reply_text("❌ Risk % must be between 0 and 100")
            return
        
        if entry_price is not None and entry_price <= 0:
            await update.message.reply_text("❌ Entry price must be positive")
            return
        
        if stop_loss is not None and stop_loss <= 0:
            await update.message.reply_text("❌ Stop loss must be positive")
            return
        
        # Calculate risk
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        if entry_price and stop_loss:
            # Full calculation with position sizing
            result = calculate_full_risk(
                account_size, 
                risk_percent, 
                entry_price, 
                stop_loss,
                is_pro
            )
        else:
            # Basic calculation
            result = calculate_basic_risk(
                account_size, 
                risk_percent,
                is_pro
            )
        
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid input. Please use numbers only.\n\n"
            "**Example:** `/risk 10000 2`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Risk calculator error: {e}")
        await update.message.reply_text(
            "❌ Error calculating risk. Please try again.",
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================================
# CALCULATION FUNCTIONS
# ============================================================================

def calculate_basic_risk(account_size: float, risk_percent: float, is_pro: bool) -> str:
    """
    Basic risk calculation (FREE)
    Shows how much $ to risk per trade
    """
    risk_amount = account_size * (risk_percent / 100)
    
    msg = "💰 **Risk Calculator**\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Account info
    msg += f"📊 **Account Size:** `${format_number(account_size)}`\n"
    msg += f"⚠️ **Risk per Trade:** `{risk_percent}%`\n\n"
    
    # Risk amount
    msg += f"💵 **Amount to Risk:** `${format_number(risk_amount)}`\n\n"
    
    # Risk management rules
    msg += "📋 **Risk Management Rules:**\n"
    msg += f"• Never risk more than `{risk_percent}%` per trade\n"
    msg += f"• Maximum loss: `${format_number(risk_amount)}`\n"
    msg += f"• Position size depends on stop loss distance\n\n"
    
    # Multiple risk scenarios (FREE users get 3 common levels)
    msg += "📊 **Common Risk Levels:**\n\n"
    
    scenarios = [
        (1, "Conservative"),
        (2, "Moderate"),
        (3, "Aggressive")
    ]
    
    for risk_pct, label in scenarios:
        risk_amt = account_size * (risk_pct / 100)
        msg += f"**{label} ({risk_pct}%)**\n"
        msg += f"• Risk: `${format_number(risk_amt)}`\n"
        msg += f"• Max loss per trade\n\n"
    
    # Upgrade prompt for pro users
    if not is_pro:
        msg += "━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🔓 **Pro Features:**\n"
        msg += "• Exact position sizing calculator\n"
        msg += "• Multiple stop loss scenarios\n"
        msg += "• Risk-reward ratio analysis\n"
        msg += "• Portfolio allocation strategy\n"
        msg += "• Save risk profiles\n\n"
        msg += "👉 /upgrade to unlock advanced tools"
    else:
        msg += "━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "_💡 Add entry and stop loss for position sizing_\n"
        msg += "_Example: `/risk 10000 2 50000 48000`_"
    
    return msg


def calculate_full_risk(
    account_size: float, 
    risk_percent: float, 
    entry_price: float, 
    stop_loss: float,
    is_pro: bool
) -> str:
    """
    Full risk calculation with position sizing
    
    Free: Basic position size
    Pro: Multiple scenarios + R:R analysis
    """
    risk_amount = account_size * (risk_percent / 100)
    
    # Determine trade direction
    is_long = entry_price > stop_loss
    
    # Calculate stop loss distance
    if is_long:
        stop_distance = entry_price - stop_loss
        stop_distance_pct = (stop_distance / entry_price) * 100
    else:
        stop_distance = stop_loss - entry_price
        stop_distance_pct = (stop_distance / entry_price) * 100
    
    # Position size calculation
    position_size = risk_amount / stop_distance
    position_value = position_size * entry_price
    
    msg = "💰 **Position Size Calculator**\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Account & Risk
    msg += "📊 **Account & Risk:**\n"
    msg += f"• Account Size: `${format_number(account_size)}`\n"
    msg += f"• Risk per Trade: `{risk_percent}%` (`${format_number(risk_amount)}`)\n\n"
    
    # Trade Setup
    direction = "🟢 LONG" if is_long else "🔴 SHORT"
    msg += f"📈 **Trade Setup:** {direction}\n"
    msg += f"• Entry Price: `${format_number(entry_price)}`\n"
    msg += f"• Stop Loss: `${format_number(stop_loss)}`\n"
    msg += f"• Distance: `${format_number(stop_distance)}` (`{stop_distance_pct:.2f}%`)\n\n"
    
    # Position Size (FREE)
    msg += "🎯 **Recommended Position:**\n"
    msg += f"• **Position Size:** `{format_number(position_size)}` units\n"
    msg += f"• **Position Value:** `${format_number(position_value)}`\n"
    msg += f"• **Leverage:** `{calculate_leverage(account_size, position_value)}x`\n\n"
    
    # Risk-Reward Scenarios (FREE: 1 scenario, PRO: 3 scenarios)
    if is_pro:
        msg += "📊 **Risk-Reward Scenarios:**\n\n"
        
        rr_ratios = [1, 2, 3]
        for rr in rr_ratios:
            if is_long:
                target_price = entry_price + (stop_distance * rr)
            else:
                target_price = entry_price - (stop_distance * rr)
            
            potential_profit = risk_amount * rr
            
            msg += f"**{rr}:1 R:R**\n"
            msg += f"• Target: `${format_number(target_price)}`\n"
            msg += f"• Profit: `${format_number(potential_profit)}` (`{potential_profit/account_size*100:.2f}%`)\n\n"
    else:
        # Free users get 1:2 R:R only
        if is_long:
            target_price = entry_price + (stop_distance * 2)
        else:
            target_price = entry_price - (stop_distance * 2)
        
        potential_profit = risk_amount * 2
        
        msg += "🎯 **2:1 Risk-Reward Target:**\n"
        msg += f"• Target Price: `${format_number(target_price)}`\n"
        msg += f"• Potential Profit: `${format_number(potential_profit)}`\n"
        msg += f"• ROI: `{potential_profit/account_size*100:.2f}%`\n\n"
    
    # Risk Summary
    msg += "⚠️ **Risk Summary:**\n"
    msg += f"• Max Loss: `${format_number(risk_amount)}` ({risk_percent}%)\n"
    msg += f"• Portfolio Exposure: `{position_value/account_size*100:.1f}%`\n"
    
    if position_value > account_size * 2:
        msg += f"• ⚠️ High leverage - Trade carefully!\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    # Upgrade prompt for free users
    if not is_pro:
        msg += "🔓 **Pro Features:**\n"
        msg += "• Multiple R:R scenarios (1:1, 2:1, 3:1, 5:1)\n"
        msg += "• Portfolio allocation across trades\n"
        msg += "• Risk of ruin calculator\n"
        msg += "• Custom R:R ratios\n"
        msg += "• Save position sizing templates\n\n"
        msg += "👉 /upgrade for advanced risk tools"
    else:
        msg += "_💡 Adjust stop loss for optimal position size_"
    
    return msg


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_number(num: float) -> str:
    """Format numbers with appropriate precision and commas"""
    if num >= 1000:
        return f"{num:,.0f}"
    elif num >= 100:
        return f"{num:,.2f}"
    elif num >= 1:
        return f"{num:.2f}"
    else:
        return f"{num:.4f}"


def calculate_leverage(account_size: float, position_value: float) -> str:
    """Calculate effective leverage"""
    leverage = position_value / account_size
    if leverage >= 1:
        return f"{leverage:.1f}"
    else:
        return "< 1"


def format_usage_guide(is_pro: bool) -> str:
    """Format usage guide based on user plan"""
    msg = "💰 **Risk Calculator - Usage Guide**\n\n"
    
    msg += "**Basic Usage (FREE):**\n"
    msg += "`/risk [account_size] [risk_%]`\n\n"
    
    msg += "**Examples:**\n"
    msg += "• `/risk 10000 2` - Risk 2% of $10,000\n"
    msg += "• `/risk 5000 1.5` - Risk 1.5% of $5,000\n"
    msg += "• `/risk 50000 3` - Risk 3% of $50,000\n\n"
    
    msg += "**Advanced Usage:**\n"
    msg += "`/risk [account] [risk_%] [entry] [stop_loss]`\n\n"
    
    msg += "**Position Sizing Examples:**\n"
    msg += "• `/risk 10000 2 50000 48000` - Long BTC\n"
    msg += "• `/risk 5000 1 3500 3600` - Short ETH\n\n"
    
    msg += "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    msg += "**What You Get:**\n\n"
    
    msg += "**Free Plan:**\n"
    msg += "✅ Risk amount calculator\n"
    msg += "✅ Basic position sizing\n"
    msg += "✅ 2:1 risk-reward target\n"
    msg += "✅ Common risk scenarios (1%, 2%, 3%)\n"
    msg += "✅ Leverage calculation\n\n"
    
    if not is_pro:
        msg += "**Pro Plan:**\n"
        msg += "🔓 Multiple R:R scenarios (1:1 to 5:1)\n"
        msg += "🔓 Portfolio allocation strategy\n"
        msg += "🔓 Risk of ruin calculator\n"
        msg += "🔓 Custom risk profiles\n"
        msg += "🔓 Position templates\n"
        msg += "🔓 Win rate analysis\n\n"
        msg += "👉 /upgrade to unlock advanced risk tools"
    
    return msg


