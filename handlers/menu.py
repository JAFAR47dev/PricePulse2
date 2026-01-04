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
            InlineKeyboardButton("📊 Markets", callback_data="menu_markets"),
            InlineKeyboardButton("💰 Trade", callback_data="menu_trade")
        ],
        [
            InlineKeyboardButton("📁 Portfolio", callback_data="menu_portfolio"),
            InlineKeyboardButton("🤖 AI", callback_data="menu_ai"),
            InlineKeyboardButton("📚 Learn", callback_data="menu_learn")
        ],
        [
            InlineKeyboardButton("📈 How It Helps", callback_data="menu_how_it_helps"),
            InlineKeyboardButton("🚀 Upgrade", callback_data="menu_upgrade"),
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
        "• `/set` — Create price alerts\n"
        "• `/alerts` — View active alerts\n"
        "• `/remove` — Remove specific alerts\n"
        "• `/removeall` — Clear all alerts"
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
        "• `/c BTC` — View charts\n"
        "• `/BTC` — Coin info\n"
        "• `/trend BTC` — View indicators\n"
        "• `/best` / `/worst` — Top movers\n"
        "• `/global` — Market overview"
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
        "• `/calc` — Crypto calculator\n"
        "• `/conv` — Currency conversion\n"
        "• `/comp` — Compare coins\n"
        "• `/markets` — Exchange prices\n"
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
        "• `/addasset` — Add assets\n"
        "• `/removeasset` — Remove assets\n"
        "• `/portfoliolimit` — Set loss alert\n"
        "• `/portfoliotarget` — Set profit alert"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=portfolio_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ai_text = (
        "🤖 *AI Tools Menu*\n\n"
        "Advanced AI-powered trading features.\n\n"
        "Available commands:\n"
        "• `/prediction` — AI price forecasting\n"
        "• `/aiscan` — Pattern detection\n"
        "• `/bt` — Backtest strategies\n"
        "• `/screen` — Scan 200+ coins\n"
        "• `/signals` — Get trading signals\n"
        "• `/regime` — Market regime overview\n"
        "• `/today` — Today's market summary"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=ai_text, parse_mode="Markdown", reply_markup=reply_markup)

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
        "• `/links` — Official coin links"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=learn_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_menu_how_it_helps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    how_it_helps_text = (
        "📈 *How This Bot Helps You Trade Smarter:*\n\n"
        "✅ *Never miss market moves* — Alerts for price, % change, volume, SL/TP, and indicators.\n"
        "✅ *Trade with confidence* — AI predictions, backtesting, pattern detection & strategy builder.\n"
        "✅ *Know exactly when to act* — Real-time watchlist alerts and whale wallet tracking.\n"
        "✅ *Master the markets* — Charts, trend analysis, heatmaps, news, forex tools & global data.\n"
        "✅ *Grow your edge* — Screen 200+ coins for setups, compare assets, and optimize your portfolio.\n\n"
        "_Trusted by thousands of crypto traders worldwide._ 🌍"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=how_it_helps_text, parse_mode="Markdown", reply_markup=reply_markup)

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
        "• Whale wallet tracking + real-time watchlist alerts\n\n"
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
            InlineKeyboardButton("📊 Markets", callback_data="menu_markets"),
            InlineKeyboardButton("💰 Trade", callback_data="menu_trade")
        ],
        [
            InlineKeyboardButton("📁 Portfolio", callback_data="menu_portfolio"),
            InlineKeyboardButton("🤖 AI", callback_data="menu_ai"),
            InlineKeyboardButton("📚 Learn", callback_data="menu_learn")
        ],
        [
            InlineKeyboardButton("📈 How It Helps", callback_data="menu_how_it_helps"),
            InlineKeyboardButton("🚀 Upgrade", callback_data="menu_upgrade"),
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