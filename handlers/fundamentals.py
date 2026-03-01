from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from services.fundamentals_service import FundamentalsService
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak
    
fundamentals_service = FundamentalsService()

# Page definitions
PAGES = {
    "overview": "📊 Overview",
    "tokenomics": "💰 Tokenomics",
    "valuation": "📈 Valuation",
    "unlocks": "🔓 Unlocks"
}

async def fundamentals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/fundamentals")  # Fixed: was "/aiscan"
    await handle_streak(update, context)
    
    
    # Check for coin argument
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/fundamentals [coin]`\n\n"
            "**Examples:**\n"
            "`/fundamentals BTC`\n"
            "`/fundamentals ethereum`\n"
            "`/fundamentals SOL`\n\n"
            "💡 Supports top 100 CoinGecko coins",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    coin_input = context.args[0].upper().strip()
    
    # Show loading message
    loading_msg = await update.message.reply_text(
        f"🔄 Fetching fundamental data for {coin_input}..."
    )
    
    try:
        # Fetch basic data (always free)
        coin_data = await fundamentals_service.get_coin_overview(coin_input)
        
        if not coin_data:
            await loading_msg.edit_text(
                f"❌ Could not find coin: `{coin_input}`\n\n"
                "Make sure the coin is in the top 100 on CoinGecko.\n"
                "Try using the full name or official symbol.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Store coin data in context for button navigation
        context.user_data['fundamentals_coin'] = coin_data['id']
        context.user_data['fundamentals_symbol'] = coin_data['symbol'].upper()
        
        # Show overview page (page 1)
        message, keyboard = await build_overview_page(coin_data, user_id)
        
        await loading_msg.edit_text(
            message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Error in /fundamentals: {e}")
        import traceback
        traceback.print_exc()
        
        await loading_msg.edit_text(
            "❌ **Failed to fetch fundamental data**\n\n"
            "This could be due to:\n"
            "• Temporary API issues\n"
            "• Coin not in top 100\n"
            "• Network connectivity\n\n"
            "Please try again in a moment.",
            parse_mode=ParseMode.MARKDOWN
        )


async def build_overview_page(coin_data: dict, user_id: int) -> tuple:
    """Build the Overview page (Page 1)"""
    
    symbol = coin_data['symbol'].upper()
    name = coin_data['name']
    
    # Format market data
    market_cap = coin_data.get('market_cap', 0)
    market_cap_rank = coin_data.get('market_cap_rank', 'N/A')
    volume_24h = coin_data.get('total_volume', 0)
    
    # Format supply data
    circulating = coin_data.get('circulating_supply', 0)
    total = coin_data.get('total_supply', 0)
    max_supply = coin_data.get('max_supply', 0)
    
    supply_pct = (circulating / total * 100) if total > 0 else 0
    
    # Format price data
    current_price = coin_data.get('current_price', 0)
    ath = coin_data.get('ath', 0)
    ath_date = coin_data.get('ath_date', 'N/A')
    atl = coin_data.get('atl', 0)
    ath_change_pct = coin_data.get('ath_change_percentage', 0)
    
    # Categories
    categories = coin_data.get('categories', [])
    categories_str = ", ".join(categories[:3]) if categories else "N/A"
    
    # Fix: Handle max_supply formatting properly
    max_supply_str = f"{max_supply:,.0f}" if max_supply and max_supply > 0 else "∞"
    
    # Fix: Handle division by zero for Vol/MCap
    vol_mcap_ratio = (volume_24h/market_cap*100) if market_cap > 0 else 0
    
    message = (
        f"📊 **{name} ({symbol}) Fundamentals**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"**💰 Market Overview**\n"
        f"• Price: `${current_price:,.2f}`\n"
        f"• Market Cap: `${market_cap:,.0f}` (#{market_cap_rank})\n"
        f"• 24h Volume: `${volume_24h:,.0f}`\n"
        f"• Vol/MCap: `{vol_mcap_ratio:.2f}%`\n\n"
        
        f"**📦 Supply Metrics**\n"
        f"• Circulating: `{circulating:,.0f}` {symbol}\n"
        f"• Total Supply: `{total:,.0f}` {symbol}\n"
        f"• Max Supply: `{max_supply_str}` {symbol}\n"
        f"• In Circulation: `{supply_pct:.1f}%`\n\n"
        
        f"**📈 Historical**\n"
        f"• ATH: `${ath:,.2f}` ({ath_date[:10] if len(ath_date) >= 10 else ath_date})\n"
        f"• ATL: `${atl:,.8f}`\n"
        f"• From ATH: `{ath_change_pct:+.1f}%`\n\n"
        
        f"**🏷️ Categories**\n"
        f"{categories_str}\n\n"
        
    )
    
    # Build keyboard
    keyboard = [
        [
            InlineKeyboardButton("💰 Tokenomics", callback_data="fund_tokenomics"),
            InlineKeyboardButton("📈 Valuation", callback_data="fund_valuation"),
        ],
        [
            InlineKeyboardButton("🔓 Unlocks", callback_data="fund_unlocks"),
            InlineKeyboardButton("🔄 Refresh", callback_data="fund_overview"),
        ]
    ]
    
    return message, InlineKeyboardMarkup(keyboard)


async def build_tokenomics_page(coin_data: dict, user_id: int) -> tuple:
    """Build the Tokenomics page (Page 2) - PRO ONLY"""
    
    plan = get_user_plan(user_id)
    
    if not is_pro_plan(plan):
        # Free user sees preview + paywall
        message = (
            f"🔒 **Tokenomics Analysis**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"**💎 Pro Feature Preview:**\n\n"
            
            f"✅ **Supply Distribution**\n"
            f"   • Team & advisor allocation\n"
            f"   • Investor holdings breakdown\n"
            f"   • Community distribution\n"
            f"   • Treasury reserves\n\n"
            
            f"✅ **Inflation Mechanics**\n"
            f"   • Current inflation rate\n"
            f"   • Emission schedule\n"
            f"   • Burn mechanisms\n"
            f"   • Net inflation trend\n\n"
            
            f"✅ **Staking Economics**\n"
            f"   • Total staked amount\n"
            f"   • Staking APR/APY\n"
            f"   • Validator count\n"
            f"   • Lock-up periods\n\n"
            
            f"✅ **Utility Analysis**\n"
            f"   • Token use cases\n"
            f"   • Fee structure\n"
            f"   • Governance rights\n\n"
            
            f"💡 **Why tokenomics matter:**\n"
            f"Understanding supply dynamics helps predict price pressure "
            f"from unlocks, inflation, and staking behavior.\n\n"
            
            f"🚀 Upgrade to Pro: /upgrade"
        )
    else:
        # PRO user sees full data
        symbol = coin_data['symbol'].upper()
        name = coin_data['name']
        
        # Fetch tokenomics data
        tokenomics = await fundamentals_service.get_tokenomics(coin_data['id'])
        
        staking_info = tokenomics.get('staking', {})
        inflation_rate = tokenomics.get('inflation_rate', 0)
        
        # Fix: Handle division by zero
        total_supply = coin_data.get('total_supply', 1)
        if total_supply == 0:
            total_supply = 1  # Prevent division by zero
        
        circulating_supply = coin_data.get('circulating_supply', 0)
        circ_pct = (circulating_supply / total_supply * 100) if total_supply > 0 else 0
        
        message = (
            f"💰 **{name} ({symbol}) Tokenomics**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"**📊 Supply Breakdown**\n"
            f"• Total Supply: `{total_supply:,.0f}` {symbol}\n"
            f"• Circulating: `{circulating_supply:,.0f}` ({circ_pct:.1f}%)\n"
            f"• Locked: `{tokenomics.get('locked_supply', 0):,.0f}` {symbol}\n"
            f"• Reserved: `{tokenomics.get('reserved_supply', 0):,.0f}` {symbol}\n\n"
            
            f"**🔥 Inflation & Burns**\n"
            f"• Inflation Rate: `{inflation_rate:+.2f}%` yearly\n"
            f"• Emission: `{tokenomics.get('emission_rate', 0):,.0f}` {symbol}/day\n"
            f"• Burn Rate: `{tokenomics.get('burn_rate', 0):,.0f}` {symbol}/day\n"
            f"• Net Change: `{tokenomics.get('net_inflation', 0):+.2f}%`\n\n"
            
            f"**🔒 Staking Metrics**\n"
            f"• Total Staked: `{staking_info.get('total_staked', 0):,.0f}` {symbol}\n"
            f"• Staked %: `{staking_info.get('staked_percentage', 0):.1f}%`\n"
            f"• Staking APR: `{staking_info.get('apr', 0):.2f}%`\n"
            f"• Validators: `{staking_info.get('validator_count', 0):,}`\n\n"
            
            f"**💡 Distribution**\n"
            f"• Team/Advisors: `{tokenomics.get('team_allocation', 0):.1f}%`\n"
            f"• Investors: `{tokenomics.get('investor_allocation', 0):.1f}%`\n"
            f"• Community: `{tokenomics.get('community_allocation', 0):.1f}%`\n"
            f"• Treasury: `{tokenomics.get('treasury_allocation', 0):.1f}%`\n\n"
            
        )
    
    # Build keyboard
    keyboard = [
        [
            InlineKeyboardButton("📊 Overview", callback_data="fund_overview"),
            InlineKeyboardButton("📈 Valuation", callback_data="fund_valuation"),
        ],
        [
            InlineKeyboardButton("🔓 Unlocks", callback_data="fund_unlocks"),
            InlineKeyboardButton("🔄 Refresh", callback_data="fund_tokenomics"),
        ]
    ]
    
    return message, InlineKeyboardMarkup(keyboard)


async def build_valuation_page(coin_data: dict, user_id: int) -> tuple:
    """Build the Valuation page (Page 3) - PRO ONLY"""
    
    plan = get_user_plan(user_id)
    
    if not is_pro_plan(plan):
        # Free user paywall
        message = (
            f"🔒 **Valuation Analysis**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"**💎 Pro Feature Preview:**\n\n"
            
            f"✅ **Network Valuation**\n"
            f"   • NVT Ratio (Network Value to Transactions)\n"
            f"   • Price/TVL for DeFi protocols\n"
            f"   • Market Cap/Realized Cap\n"
            f"   • Active users valuation\n\n"
            
            f"✅ **Relative Valuation**\n"
            f"   • vs Bitcoin ratio\n"
            f"   • vs Ethereum ratio\n"
            f"   • Historical averages\n"
            f"   • Sector comparison\n\n"
            
            f"✅ **Revenue Metrics** (where applicable)\n"
            f"   • Protocol revenue\n"
            f"   • Fee generation\n"
            f"   • P/S ratio\n"
            f"   • Revenue per token\n\n"
            
            f"✅ **Fair Value Estimate**\n"
            f"   • Multiple valuation models\n"
            f"   • Over/undervalued %\n"
            f"   • Price targets\n\n"
            
            f"💡 **Why valuation matters:**\n"
            f"Identify overvalued hype vs undervalued gems using "
            f"fundamental metrics, not just price action.\n\n"
            
            f"🚀 Upgrade to Pro: /upgrade"
        )
    else:
        # PRO user sees full data
        symbol = coin_data['symbol'].upper()
        name = coin_data['name']
        
        # Fetch valuation data
        valuation = await fundamentals_service.get_valuation_metrics(coin_data['id'])
        
        message = (
            f"📈 **{name} ({symbol}) Valuation**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"**💰 Network Metrics**\n"
            f"• NVT Ratio: `{valuation.get('nvt_ratio', 0):.1f}`\n"
            f"• Price/TVL: `{valuation.get('price_to_tvl', 0):.2f}`\n"
            f"• MCap/Realized: `{valuation.get('mvrv_ratio', 0):.2f}`\n"
            f"• Value/User: `${valuation.get('value_per_user', 0):,.0f}`\n\n"
            
            f"**📊 Relative Valuation**\n"
            f"• vs BTC: `{valuation.get('btc_ratio', 0):.6f}`\n"
            f"• Historical Avg: `{valuation.get('btc_ratio_avg', 0):.6f}`\n"
            f"• vs ETH: `{valuation.get('eth_ratio', 0):.4f}`\n"
            f"• Sector Rank: `#{valuation.get('sector_rank', 0)}`\n\n"
            
            f"**💵 Revenue (if applicable)**\n"
            f"• Daily Fees: `${valuation.get('daily_fees', 0):,.0f}`\n"
            f"• Protocol Revenue: `${valuation.get('protocol_revenue', 0):,.0f}`\n"
            f"• P/S Ratio: `{valuation.get('ps_ratio', 0):.1f}`\n"
            f"• Annualized: `${valuation.get('annualized_revenue', 0):,.0f}`\n\n"
            
            f"**🎯 Fair Value Assessment**\n"
            f"• Model Price: `${valuation.get('fair_value', 0):,.2f}`\n"
            f"• Current: `${coin_data.get('current_price', 0):,.2f}`\n"
            f"• Deviation: `{valuation.get('valuation_deviation', 0):+.1f}%`\n"
            f"• Signal: {valuation.get('signal', 'Neutral')}\n\n"
            
        )
    
    # Build keyboard
    keyboard = [
        [
            InlineKeyboardButton("📊 Overview", callback_data="fund_overview"),
            InlineKeyboardButton("💰 Tokenomics", callback_data="fund_tokenomics"),
        ],
        [
            InlineKeyboardButton("🔓 Unlocks", callback_data="fund_unlocks"),
            InlineKeyboardButton("🔄 Refresh", callback_data="fund_valuation"),
        ]
    ]
    
    return message, InlineKeyboardMarkup(keyboard)


async def build_unlocks_page(coin_data: dict, user_id: int) -> tuple:
    """Build the Unlocks page (Page 4) - PRO ONLY"""
    
    plan = get_user_plan(user_id)
    
    if not is_pro_plan(plan):
        # Free user paywall
        message = (
            f"🔒 **Token Unlock Schedule**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"**💎 Pro Feature Preview:**\n\n"
            
            f"✅ **Upcoming Unlocks**\n"
            f"   • Next 90 days calendar\n"
            f"   • Token amounts & USD value\n"
            f"   • Vesting categories (team, investors, etc.)\n"
            f"   • % of circulating supply impact\n\n"
            
            f"✅ **Vesting Schedule**\n"
            f"   • Full unlock timeline\n"
            f"   • Cliff dates\n"
            f"   • Linear vs stepped unlocks\n"
            f"   • Remaining locked tokens\n\n"
            
            f"✅ **Historical Impact**\n"
            f"   • Past unlock dates\n"
            f"   • Price action around unlocks\n"
            f"   • Selling pressure analysis\n\n"
            
            f"✅ **Risk Assessment**\n"
            f"   • High-risk unlock alerts\n"
            f"   • Large unlock warnings\n"
            f"   • Recommended actions\n\n"
            
            f"💡 **Why unlocks matter:**\n"
            f"Large token unlocks often create selling pressure. "
            f"Knowing unlock dates helps you avoid getting dumped on.\n\n"
            
            f"🚀 Upgrade to Pro: /upgrade"
        )
    else:
        # PRO user sees full data
        symbol = coin_data['symbol'].upper()
        name = coin_data['name']
        
        # Fetch unlock data
        unlocks = await fundamentals_service.get_unlock_schedule(coin_data['id'])
        
        upcoming = unlocks.get('upcoming', [])
        
        # Build upcoming unlocks list
        unlock_list = ""
        for unlock in upcoming[:5]:  # Show next 5
            date = unlock.get('date', 'TBD')
            amount = unlock.get('amount', 0)
            value_usd = unlock.get('value_usd', 0)
            category = unlock.get('category', 'Unknown')
            pct_supply = unlock.get('pct_of_supply', 0)
            
            emoji = "⚠️" if pct_supply > 5 else "⏰"
            
            unlock_list += (
                f"{emoji} **{date}**\n"
                f"   `{amount:,.0f}` {symbol} (${value_usd:,.0f})\n"
                f"   {category} • {pct_supply:.1f}% of supply\n\n"
            )
        
        if not unlock_list:
            unlock_list = "No major unlocks in next 90 days ✅\n\n"
        
        message = (
            f"🔓 **{name} ({symbol}) Unlocks**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"**📅 Upcoming Unlocks**\n"
            f"{unlock_list}"
            
            f"**📊 Vesting Summary**\n"
            f"• Total Locked: `{unlocks.get('total_locked', 0):,.0f}` {symbol}\n"
            f"• % of Total: `{unlocks.get('locked_percentage', 0):.1f}%`\n"
            f"• Next Big Unlock: `{unlocks.get('next_major_date', 'N/A')}`\n"
            f"• Avg Monthly: `{unlocks.get('avg_monthly_unlock', 0):,.0f}` {symbol}\n\n"
            
            f"**⚠️ Risk Level**\n"
            f"{unlocks.get('risk_assessment', 'Calculating...')}\n\n"
            
            f"💡 Set alerts: `/alert {symbol} unlock`\n\n"
            
        )
    
    # Build keyboard
    keyboard = [
        [
            InlineKeyboardButton("📊 Overview", callback_data="fund_overview"),
            InlineKeyboardButton("💰 Tokenomics", callback_data="fund_tokenomics"),
        ],
        [
            InlineKeyboardButton("📈 Valuation", callback_data="fund_valuation"),
            InlineKeyboardButton("🔄 Refresh", callback_data="fund_unlocks"),
        ]
    ]
    
    return message, InlineKeyboardMarkup(keyboard)


async def fundamentals_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses for page navigation"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data.replace("fund_", "")
    
    # Get stored coin data
    coin_id = context.user_data.get('fundamentals_coin')
    
    if not coin_id:
        await query.edit_message_text(
            "❌ Session expired. Please run `/fundamentals [coin]` again.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        # Fetch fresh coin data
        coin_data = await fundamentals_service.get_coin_data_by_id(coin_id)
        
        if not coin_data:
            await query.edit_message_text("❌ Failed to fetch data. Please try again.")
            return
        
        # Build appropriate page
        if action == "overview":
            message, keyboard = await build_overview_page(coin_data, user_id)
        elif action == "tokenomics":
            message, keyboard = await build_tokenomics_page(coin_data, user_id)
        elif action == "valuation":
            message, keyboard = await build_valuation_page(coin_data, user_id)
        elif action == "unlocks":
            message, keyboard = await build_unlocks_page(coin_data, user_id)
        else:
            await query.edit_message_text("❌ Unknown action")
            return
        
        # Update message
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Error in callback: {e}")
        import traceback
        traceback.print_exc()
        await query.edit_message_text(
            "❌ Something went wrong. Please try `/fundamentals [coin]` again.",
            parse_mode=ParseMode.MARKDOWN
        )


# Register handlers in main bot file
def register_fundamentals_handlers(app):
    """Register all fundamentals handlers"""
    from telegram.ext import CommandHandler, CallbackQueryHandler
    
    app.add_handler(CommandHandler("fundamentals", fundamentals_command))
    app.add_handler(CallbackQueryHandler(fundamentals_callback, pattern="^fund_"))
