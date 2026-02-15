from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from models.user_activity import update_last_active

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    await update_last_active(user_id, command_name="/menu")
    
    # --- Menu Message ---
    text = (
        "🎯 *Bot Command Menu*\n\n"
        "Select a category below to explore available commands:"
    )

    # --- Inline Buttons (3 per row, logically grouped) ---
    
    keyboard = [
  	  [
  	      InlineKeyboardButton("🔔 Alerts", callback_data="menu_alerts"),
  	      InlineKeyboardButton("📈 Popular Commands", callback_data="menu_popular_commands"),
     	   InlineKeyboardButton("📊 Markets", callback_data="menu_markets")
	    ],
	    [
      	  InlineKeyboardButton("💰 Trade", callback_data="menu_trade"),
      	  InlineKeyboardButton("📁 Portfolio", callback_data="menu_portfolio"),
       	 InlineKeyboardButton("📚 Learn", callback_data="menu_learn")
	    ],
 	   [
      	  InlineKeyboardButton("🚀 Pro Features", callback_data="menu_pro_features"),
     	   InlineKeyboardButton("📲 Upgrade", callback_data="menu_upgrade"),
      	  InlineKeyboardButton("👤 Account", callback_data="menu_account")
    	]
	]

    reply_markup = InlineKeyboardMarkup(keyboard)


    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Handler functions for menu callbacks
async def handle_menu_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    alerts_text = (
    "🔔 *Alerts Menu*\n\n"
    "Set up custom alerts to never miss important market moves.\n\n"
    "Available commands:\n"
    "• `/set` — Create alerts\n"
    "• `/alerts` — View active alerts\n"
    "• `/remove` — Remove specific alerts\n"
    "• `/removeall` — Clear all alerts\n"
    "• `/watch [coin] [threshold] [time period]` — Watch a coin for % moves\n"
    "• `/watchlist` — View your watchlist\n"
    "• `/removewatch [coin]` — Remove a coin from watchlist"
)

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=alerts_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    markets_text = (
        "📊 *Markets Menu*\n\n"
        "Track market data, charts, and trends.\n\n"
        "Available commands:\n"
        "• `/c [coin] [timeframe]` — View charts\n"
        "• `/[coin]` — Coin info\n"
        "• `/trend [coin] [timeframe]` — View indicators\n"
        "• `/best` / `/worst` — Top movers\n"
        "• `/global` — Market overview\n"
        "• `/fav` — Keep track of your favorite crypto"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=markets_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    trade_text = (
        "💰 *Trade Menu*\n\n"
        "Trading tools and utilities.\n\n"
        "Available commands:\n"
        "• `/calc [coin] [amount]` — Crypto calculator\n"
        "• `/risk [account] [risk_%] [entry] [stop_loss]` — Position sizing & risk calculator\n"
        "• `/conv [amount] [coin/fiat] to [coin/fiat]` — Currency conversion\n"
        "• `/comp [coin] [coin]` — Compare 2 - 3 coins\n"
        "• `/markets [coin]` — Exchange prices\n"
        "• `/gas` — ETH gas fees"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=trade_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    portfolio_text = (
        "📁 *Portfolio Menu*\n\n"
        "Manage and track your crypto portfolio.\n\n"
        "Available commands:\n"
        "• `/portfolio` — View portfolio\n"
        "• `/add [coin] [amount]` — Add assets\n"
        "• `/removeasset` — Remove assets\n"
        "• `/pflimit [limit] [repeat(optional)]` — Set loss alert\n"
        "• `/pftarget [target] [repeat(optional)]` — Set profit alert"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=portfolio_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_pro_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pro_text = (
        "🚀 *Pro Trading Tools*\n\n"
        "Advanced features designed for active and professional traders.\n\n"

        "*Alerts & Risk*\n"
        "• Advanced alerts — percent, volume, risk, indicators\n"
        "• Watch alerts — track coin moves over time (`/watch`)\n"
        "• `/levels [coin] [timeframe]` — Key support & resistance zones\n\n"

        "*AI & Market Intelligence*\n"
        "• `/setup [coin] [timeframe]` - Professional Setup Analyzer\n"
        "• `/analysis [coin] [timeframe]` — AI-powered technical analysis\n"
        "• `/aiscan [coin] [timeframe]` — Detect patterns: divergence, crosses, etc.\n"
        "• `/regime [coin]` — Market regime & risk assessment\n"
        "• `/hold [coin] [period]` — Capital preservation analysis (hold vs exit)\n"
        "• `/today` — Today's market summary\n\n"

        "*Research & Strategy*\n"
        "• `/bt [coin] [period]` — Strategy backtesting\n"
        "• `/screen` — Scan top coins for setups\n\n"

        "*Portfolio & Smart Risk*\n"
        "• Portfolio SL / TP automation\n"
        "• Advanced portfolio risk controls\n\n"

        #"*On-chain Intelligence*\n"
#        "• `/track [coin] [no. of whales]` — Whale wallet tracking\n"
#        "• `/mywhales` — Whale activity alerts"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to menu", callback_data="back_to_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=pro_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
      
async def handle_menu_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    learn_text = (
        "📚 *Learn Menu*\n\n"
        "Educational resources and crypto information.\n\n"
        "Available commands:\n"
        "• `/learn` — Crypto terms explained\n"
        "• `/funfact` — Random crypto facts\n"
        "• `/news` — Latest crypto news\n"
        "• `/cod` — Coin of the day\n"
        "• `/links [coin]` — Official coin links"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=learn_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_popular_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    popular_text = (
        "⭐ *Popular Commands*\n\n"
        "The most-used tools traders rely on daily:\n\n"

        "🚨 *Alerts & Monitoring*\n"
        "• `/set` — Create smart price alerts\n"
        "• `/watch` — Monitor coin moves over time\n"
        "• `/alerts` — View active alerts\n\n"

        "📊 *Market Analysis*\n"
        "• `/setup` - Professional Setup Analyzer\n"
        "• `/today` — Should you trade today?\n"
        "• `/analysis` — AI technical analysis\n"
        "• `/trend` — Indicators & momentum\n"
        "• `/levels` — Key support & resistance\n\n"

        "📈 *Charts & Insights*\n"
        "• `/c` — TradingView charts\n"
        "• `/regime` — Market risk & phase\n"
        "• `/global` — Market overview\n\n"
        
        "🧮 *Trading Utilities*\n"
   	 "• `/calc` — Crypto calculator\n"
    	"• `/conv` — Currency conversion\n"
    	"• `/comp` — Compare coins\n"

       # "🐳 *Smart Money*\n"
#        "• `/track` — Track whale wallets\n"
#        "• `/mywhales` — Whale activity alerts\n"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to menu", callback_data="back_to_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=popular_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
async def handle_menu_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    upgrade_text = (
        "💎 *Upgrade to Pro & Unlock Your Full Trading Power*\n\n"
        "🚀 *Why Go Pro?*\n"
        "• Unlimited alerts — never miss a move\n"
        "• % change, volume, risk & custom alert types\n"
        "• Full chart timeframes & advanced trend analysis\n"
        "• AI predictions, backtests, scanners & pattern detection\n"
        "• Portfolio tracking with SL/TP automation\n"
        "• Real-time watchlist alerts\n\n"
        "✨ Want FREE Pro ? Just type /tasks\n"
        "💼 Ready to upgrade anytime? Use /upgrade"
    )
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    account_text = (
        "👤 *Account Menu*\n\n"
        "Manage your account settings and preferences.\n\n"
        "Available commands:\n"
        "• `/upgrade` — Upgrade to Pro\n"
        "• `/tasks` — Earn FREE Pro\n"
        "• `/referral` — Get referral link\n"
        "• `/myplan` — Check your subscription plan and expiry date\n"
        "• `/notifications` — Toggle notifications\n"
        "• `/feedback` — Share your review\n"
        "• `/privacy` - View our privacy policy and terms\n"
        "• `/support` — Contact support"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=account_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = (
        "🎯 *Bot Command Menu*\n\n"
        "Select a category below to explore available commands:"
    )

    keyboard = [
  	  [
  	      InlineKeyboardButton("🔔 Alerts", callback_data="menu_alerts"),
  	      InlineKeyboardButton("📈 Popular Commands", callback_data="menu_popular_commands"),
     	   InlineKeyboardButton("📊 Markets", callback_data="menu_markets")
	    ],
	    [
      	  InlineKeyboardButton("💰 Trade", callback_data="menu_trade"),
      	  InlineKeyboardButton("📁 Portfolio", callback_data="menu_portfolio"),
       	 InlineKeyboardButton("📚 Learn", callback_data="menu_learn")
	    ],
 	   [
      	  InlineKeyboardButton("🚀 Pro Features", callback_data="menu_pro_features"),
     	   InlineKeyboardButton("📲 Upgrade", callback_data="menu_upgrade"),
      	  InlineKeyboardButton("👤 Account", callback_data="menu_account")
    	]
	]

    reply_markup = InlineKeyboardMarkup(keyboard)


    await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=reply_markup)


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    await update_last_active(user_id, command_name="/support")
    
    community_link = "https://t.me/+tSWwj5w7S8hkZmM0"
    
    support_text = (
        "💬 *Need Help or Support?*\n\n"
        "Join our active Telegram community where you can:\n\n"
        "✅ Get help from experienced traders\n"
        "✅ Share trading strategies and signals\n"
        "✅ Request new features\n"
        "✅ Report bugs or issues\n"
        "✅ Connect with other bot users\n"
        "✅ Get updates on new features\n\n"
        f"🔗 [Join Community]({community_link})\n\n"
        "💡 _You can also use /feedback to send us direct feedback!_"
    )
    
    keyboard = [
        [InlineKeyboardButton("👥 Join Community", url=community_link)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        support_text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )