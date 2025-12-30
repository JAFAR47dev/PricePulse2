from models.db import get_connection
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
from config import ADMIN_ID

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    await update_last_active(user_id, command_name="/start")
    username = user.username
    name = user.first_name or "Trader"
    args = context.args

    referred_by = None
    if args:
        try:
            referred_by = int(args[0])
        except ValueError:
            referred_by = None

    conn = get_connection()
    cursor = conn.cursor()

    # Check if this user was already referred before
    cursor.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (user_id,))
    already_referred = cursor.fetchone()

    if referred_by and not already_referred and referred_by != user_id:

        # Insert referral
        cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
        """, (referred_by, user_id))

        # Make sure task_progress rows exist
        init_task_progress(user_id)
        init_task_progress(referred_by)

        # Increase referral count
        cursor.execute("""
            UPDATE task_progress
            SET referral_count = referral_count + 1
            WHERE user_id = ?
        """, (referred_by,))

        conn.commit()

    # Register user if not exists
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, plan)
        VALUES (?, ?, 'free')
    """, (user_id, username))

    if cursor.rowcount > 0:
        print(f"🆕 New user joined: {user_id} (@{username})")

    conn.commit()
    conn.close()

    # 🔔 Notify admin about new user
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "👤 *New User Joined!*\n"
                f"ID: `{user_id}`\n"
                f"Username: @{username or 'N/A'}"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Failed to notify admin: {e}")
        
    # --- Welcome Message ---
    text = (
        f"👋 Welcome *{name}*!\n\n"
        f"📈 _You're now using one of Telegram's most powerful crypto trading assistants._\n\n"
        "💹 Thousands of traders use this bot daily to:\n"
        "• Set price, volume, and portfolio alerts\n"
        "• Track market trends & get AI predictions\n"
        "• Protect portfolios with SL/TP alerts\n"
        "• Monitor risk and volatility\n\n"
        "✨ Join the growing Pro community and level up your trading!"
    )

    # --- Inline Buttons (3 per row, logically grouped) ---
    keyboard = [
        [
            InlineKeyboardButton("🔔 Alerts", callback_data="alerts"),
            InlineKeyboardButton("📊 Markets", callback_data="markets"),
            InlineKeyboardButton("💰 Trade", callback_data="trade")
        ],
        [
            InlineKeyboardButton("📁 Portfolio", callback_data="portfolio"),
            InlineKeyboardButton("🤖 AI", callback_data="ai"),
            InlineKeyboardButton("📚 Learn", callback_data="learn")
        ],
        [
            InlineKeyboardButton("📈 How It Helps", callback_data="how_it_helps"),
            InlineKeyboardButton("🚀 Upgrade", callback_data="upgrade_menu"),
            InlineKeyboardButton("👤 Account", callback_data="account")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    

async def handle_upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
async def handle_how_it_helps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    upgrade_text = (
        "📈 *How This Bot Helps You Trade Smarter:*\n\n"
        "✅ *Never miss market moves* — Alerts for price, % change, volume, SL/TP, and indicators.\n"
        "✅ *Trade with confidence* — AI predictions, backtesting, pattern detection & strategy builder.\n"
        "✅ *Know exactly when to act* — Real-time watchlist alerts and whale wallet tracking.\n"
        "✅ *Master the markets* — Charts, trend analysis, heatmaps, news, forex tools & global data.\n"
        "✅ *Grow your edge* — Screen 200+ coins for setups, compare assets, and optimize your portfolio.\n\n"
        "_Trusted by thousands of crypto traders worldwide._ 🌍"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=alerts_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "• `/global` — Market overview\n"
        "• `/hmap` — Heatmap of top 100 coins\n"
        "• `/fav` — Keep track of your favorite crypto"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=markets_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=trade_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    portfolio_text = (
        "📁 *Portfolio Menu*\n\n"
        "Manage and track your crypto portfolio.\n\n"
        "Available commands:\n"
        "• `/portfolio` — View portfolio\n"
        "• `/add` — Add assets\n"
        "• `/removeasset` — Remove assets\n"
        "• `/pflimit` — Set loss alert\n"
        "• `/pftarget` — Set profit alert"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=portfolio_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ai_text = (
        "🤖 *AI Tools Menu*\n\n"
        "Advanced AI-powered trading features.\n\n"
        "Available commands:\n"
        "• `/prediction` — AI price forecasting\n"
        "• `/aiscan` — Pattern detection\n"
        "• `/bt` — Backtest strategies\n"
        "• `/screen` — Scan 200+ coins"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=ai_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=learn_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    account_text = (
        "👤 *Account Menu*\n\n"
        "Manage your account settings and preferences.\n\n"
        "Available commands:\n"
        "• `/upgrade` — Upgrade to Pro\n"
        "• `/tasks` — Earn FREE Pro\n"
        "• `/referral` — Get referral link\n"
        "• `/notifications` — Toggle notifications\n"
        "• `/myplan` — Check your subscription plan and expiry date\n"
        "• `/feedback` — Share your review"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=account_text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    name = user.first_name or "Trader"

    # --- Inline Buttons (3 per row, logically grouped) ---
    keyboard = [
        [
            InlineKeyboardButton("🔔 Alerts", callback_data="alerts"),
            InlineKeyboardButton("📊 Markets", callback_data="markets"),
            InlineKeyboardButton("💰 Trade", callback_data="trade")
        ],
        [
            InlineKeyboardButton("📁 Portfolio", callback_data="portfolio"),
            InlineKeyboardButton("🤖 AI", callback_data="ai"),
            InlineKeyboardButton("📚 Learn", callback_data="learn")
        ],
        [
            InlineKeyboardButton("📈 How It Helps", callback_data="how_it_helps"),
            InlineKeyboardButton("🚀 Upgrade", callback_data="upgrade_menu"),
            InlineKeyboardButton("👤 Account", callback_data="account")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 Welcome *{name}*!\n\n"
        f"📈 _You're now using one of Telegram's most powerful crypto trading assistants._\n\n"
        "💹 Thousands of traders use this bot daily to:\n"
        "• Set price, volume, and portfolio alerts\n"
        "• Track market trends & get AI predictions\n"
        "• Protect portfolios with SL/TP alerts\n"
        "• Monitor risk and volatility\n\n"
        "✨ Join the growing Pro community and level up your trading!"
    )

    await query.edit_message_text(text=welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
