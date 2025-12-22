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

    # --- Inline Buttons ---
    keyboard = [
        [
            InlineKeyboardButton("🚀 Upgrade", callback_data="upgrade_menu"),
            InlineKeyboardButton("📈 How It Helps", callback_data="how_it_helps")
        ],
        [
            InlineKeyboardButton("📚 View Commands", callback_data="view_commands"),
            InlineKeyboardButton("👥 Join Community", callback_data="join_community")
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
    
    
async def handle_view_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    upgrade_text = (
    "📘 *Available Bot Commands*\n\n"

    "━━━━━━━━━━━━━━━━━━━\n"
    "⚙️ *Free Plan Commands*\n"
    "━━━━━━━━━━━━━━━━━━━\n"
    "🛎️ *Basic Alerts:*\n"
    "• `/set (price)` — Set price-based alerts \n"
    "• `/alerts` — View your active alerts\n"
    "• `/remove ` — Remove a specific alert type\n"
    "• `/removeall` — Delete all alerts\n\n"

    "📊 *Charts & Data:*\n"
    "• `/c BTC` — View 1h TradingView chart\n"
    "• `/BTC` — Coin info: price, % change, volume, ATH, etc.\n"
    "• `/trend BTC` — View indicators (1h only)\n"
    "• `/best` / `/worst` — Top 3 gainers/losers (24h)\n"
    "• `/news` — Get latest 5 crypto headlines\n\n"
    "• `/cod` — Coin of the day\n"
    "• `/global` — Crypto market overview\n"
    "• `/gas` — ETH gas fees\n"
    "• `/markets btc` — Prices on major exchanges\n"
    "• `/links btc` — Official links for any coin\n\n"
    
    "📚 *Education & Fun:*\n"
    "• `/learn` — Crypto terms explained\n"
    "• `/funfact` — Random crypto fact\n\n"
    
    "📐 *Utilities:*\n"
    "• `/calc 100 btc` — Crypto/fiat calculator\n"
    "• `/conv 2 eth to usd` — Crypto conversion\n"
    "• `/hmap` — Heatmap of top 50 coins\n"
    "• `/comp btc eth` – Compare 2–3 coins\n\n"


     "*🌍 Forex Tools & Community*\n\n"
       "• `/fx eurusd` – Live forex rates\n"
       "• `/fxchart` – Forex Charts\n"
       "• `/fxconv 100 gbp to usd` – Fiat conversions\n"
       "• `/fxsessions` – Open forex markets\n\n"

    "🎁 *Growth & Referral:*\n"
    "• `/tasks` — Complete tasks to earn FREE Pro\n"
    "• `/referral` — Get your referral link\n\n"

    "🧭 *Navigation & Info:*\n"
    "• `/start` — Launch welcome menu\n"
    "• `/help` — View detailed guide\n"
    "• `/upgrade` — See Pro benefits & upgrade steps\n"
    "• `/feedback` — Share your review\n"
    "• `/notifications` — Enable/disable bot notifications\n"
    "• `/addtogroup` — Add bot to your Telegram group\n\n"
    
    "━━━━━━━━━━━━━━━━━━━\n"
    "💎 *Pro Plan Features*\n"
    "━━━━━━━━━━━━━━━━━━━\n"
    "📈 *Advanced Alerts:*\n"
    "• `/set (percent) ` — Alert on % price changes\n"
    "• `/set (volume)` — Volume spike alert\n"
    "• `/set (risk) ` — Stop-loss / Take-profit alerts\n"
    "• `/set (custom) ` — Price + indicator alerts\n"

    "🧾 *Portfolio Management:*\n"
    "• `/portfolio` — View total value of assets\n"
    "• `/addasset BTC 1.2` — Add coins to portfolio\n"
    "• `/removeasset BTC` — Remove a coin\n"
    "• `/clearportfolio` — Clear all assets\n"
    "• `/portfoliolimit 15000` — Set a loss alert\n"
    "• `/portfoliotarget 25000` — Set a profit alert\n\n"

    "🔔 *Watchlist Tools:*\n"
    "• `/watch BTC 5 1h` — Alert for ±% moves\n"
    "• `/watchlist` — View all watch alerts\n"
    "• `/removewatch BTC` — Remove coin from watchlist\n\n"

    "🤖 *Smart Tools:*\n"
    "• `/c BTC 4h` — Unlock full chart timeframes\n"
    "• `/trend ETH 1d` — Advanced trend analysis\n"
    "• `/prediction BTC 1h` — AI-based price forecasting\n"
    "• `/aistrat` – Natural language alert builder\n"
    "• `/aiscan` – Detect patterns: divergence, crosses, etc.\n"
    "• `/bt BTC 1h` – Backtest strategies with AI summary\n"
    "• `/screen` – Scan top 200+ coins for setups\n"
    
    
    "🐋 *On-Chain Tools:*\n"
    "• `/track` – Track whale wallets\n"
    "• `/untrack` – Stop tracking\n"
    "• `/mywhales` – View whale alerts\n\n"
    
    "━━━━━━━━━━━━━━━━━━━\n"
    "💬 *Feature Request?*\n"
    "Got an idea or need a custom feature?\n"
    "👉 [Join our community](https://t.me/+tSWwj5w7S8hkZmM0) and share your thoughts!"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
    
    
async def handle_join_community(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    community_link = "https://t.me/+tSWwj5w7S8hkZmM0"  # Private invite link

    upgrade_text = (
        "🤝 *Join Our Trading Community!*\n\n"
        "Connect with hundreds of traders, share signals, ask questions, and learn from others using this bot.\n\n"
        f"🔗 Join here: {community_link}"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
async def handle_back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    name = user.first_name or "Trader"

    keyboard = [
        [
            InlineKeyboardButton("🚀 Upgrade", callback_data="upgrade_menu"),
            InlineKeyboardButton("📈 How It Helps", callback_data="how_it_helps")
        ],
        [
            InlineKeyboardButton("📚 View Commands", callback_data="view_commands"),
            InlineKeyboardButton("👥 Join Community", callback_data="join_community")
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