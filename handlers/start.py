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
import sqlite3
import time

def get_connection_with_retry(max_retries=3):
    """Get database connection with retry logic"""
    for attempt in range(max_retries):
        try:
            conn = get_connection()
            conn.execute("PRAGMA busy_timeout = 30000")
            return conn
        except sqlite3.OperationalError:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
    return get_connection()

def init_task_progress_with_conn(user_id: int, conn):
    """
    Initialize task progress for a new user using an existing connection.
    Creates a row with default values if it doesn't exist.
    
    Args:
        user_id: The user's Telegram ID
        conn: Existing database connection to use (prevents nested connections)
    """
    cursor = conn.cursor()

    try:
        # ✅ Get all existing columns dynamically
        cursor.execute("PRAGMA table_info(task_progress)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # ✅ Build dynamic INSERT with only existing columns
        column_defaults = {
            'user_id': user_id,
            'daily_streak': 0,
            'last_active_date': None,
            'streak_reward_claimed': 0,
            'pro_expiry_date': None,
            'referral_count': 0,
            'claimed_referral_rewards': '[]',
            'referral_rewards_claimed': '',
            'social_tg': 0,
            'social_tw': 0,
            'social_story': 0
        }
        
        # ✅ Only use columns that actually exist in the table
        insert_columns = [col for col in column_defaults.keys() if col in columns]
        insert_values = [column_defaults[col] for col in insert_columns]
        
        # ✅ Build the SQL dynamically
        columns_str = ', '.join(insert_columns)
        placeholders = ', '.join(['?' for _ in insert_columns])
        
        cursor.execute(f"""
            INSERT OR IGNORE INTO task_progress ({columns_str})
            VALUES ({placeholders})
        """, insert_values)

        print(f"✅ Task progress initialized for user {user_id}")
    except Exception as e:
        print(f"❌ Error initializing task progress for user {user_id}: {e}")
        raise  # Re-raise so caller can handle

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

    conn = get_connection_with_retry()
    cursor = conn.cursor()

    try:
        # Check if this user was already referred before
        cursor.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (user_id,))
        already_referred = cursor.fetchone()

        if referred_by and not already_referred and referred_by != user_id:
            # Insert referral
            cursor.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            """, (referred_by, user_id))

            # Make sure task_progress rows exist - USING SAME CONNECTION
            init_task_progress_with_conn(user_id, conn)
            init_task_progress_with_conn(referred_by, conn)

            # Increase referral count
            cursor.execute("""
                UPDATE task_progress
                SET referral_count = referral_count + 1
                WHERE user_id = ?
            """, (referred_by,))

        # Register user if not exists
        cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, username, plan)
            VALUES (?, ?, 'free')
        """, (user_id, username))

        if cursor.rowcount > 0:
            print(f"🆕 New user joined: {user_id} (@{username})")

        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Database error in start_command: {e}")
        # Still allow the bot to respond even if DB fails
        
    finally:
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
        
    text = (
    f"👋 Welcome, {name}.\n\n"
    f"Most traders lose money trading the right setup at the wrong time.\n\n"
    f"This bot helps you find the good trades and avoid the bad ones.\n\n"
    f"It reads market structure, momentum, and risk — then gives you:\n\n"
    f"• Clear bias: bullish, bearish, or stay out\n"
    f"• Key levels where price is likely to react\n"
    f"• Risk assessment so you know when NOT to trade\n\n"
    f"No hype. No signal spam.\n"
    f"Just honest market context so you can trade with an edge.\n\n"
    f"*Start here (takes 20 seconds):*\n\n"
    f"`/set` — Alerts for key price zones\n\n"   
    f"Then explore:\n\n"
    f"`/btc` — Live BTC analysis with levels\n"
    f"`/today` — Should you trade today?\n"
    f"`/fav` — Track your favorite coins\n\n"
    f"This isn't financial advice. It's a tool to trade smarter, not harder."
)

    # --- Inline Buttons (3 per row, logically grouped) ---
    keyboard = [
  	  [
  	      InlineKeyboardButton("🔔 Alerts", callback_data="alerts"),
  	      InlineKeyboardButton("📈 Popular Commands", callback_data="popular_commands"),
     	   InlineKeyboardButton("📊 Markets", callback_data="markets")
	    ],
	    [
      	  InlineKeyboardButton("💰 Trade", callback_data="trade"),
      	  InlineKeyboardButton("📁 Portfolio", callback_data="portfolio"),
       	 InlineKeyboardButton("📚 Learn", callback_data="learn")
	    ],
 	   [
      	  InlineKeyboardButton("🚀 Pro Features", callback_data="pro_features"),
     	   InlineKeyboardButton("📲 Upgrade", callback_data="upgrade_menu"),
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
    "💎 *Unlock Pro — Trade With Clarity, Not Guesswork*\n\n"
    "🚀 *What You Get With Pro:*\n"
    "• 🔔 Unlimited smart alerts across all strategies\n"
    "• 📊 Advanced alert types: % move, volume, risk & indicators\n"
    "• 📈 Full multi-timeframe charts + deep trend analysis\n"
    "• 🤖 AI-powered analysis, backtests, scanners & pattern detection\n"
    "• 💼 Portfolio tracking with automated SL / TP protection\n"
    "• Intelligent watchlist alerts\n\n"
    "🧠 *Built for traders who want signal, not noise.*\n\n"
    "✨ *Get Pro FREE* — complete tasks with `/tasks`\n"
    "💎 *Upgrade instantly* — use `/upgrade` anytime"
)

    
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
async def handle_popular_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "• `/hold` — Capital preservation analysis (hold vs exit)\n"
        "• `/analysis` — AI technical analysis\n"
        "• `/trend` — Indicators & momentum\n\n"

        "📈 *Charts & Insights*\n"
        "• `/c` — TradingView charts\n"
        "• `/regime` — Market risk & phase\n"
        "• `/global` — Market overview\n\n"

        "🧮 *Trading Utilities*\n"
   	 "• `/calc` — Crypto calculator\n"
    	"• `/conv` — Currency conversion\n"
    	"• `/comp` — Compare coins\n"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=popular_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
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
        "• `/removeall` — Clear all alerts\n"
        "• `/watch` — Watch a coin for % moves\n"
  	  "• `/watchlist` — View your watchlist\n"
  	  "• `/removewatch` — Remove a coin from watchlist"
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
        "• `/movers` — See what's pumping/dumping\n"
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
        "• `/risk` — Position sizing & risk calculator\n"
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

async def handle_pro_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pro_text = (
        "🚀 *Pro Trading Tools*\n\n"
        "Advanced features designed for active and professional traders.\n\n"

        "*Alerts & Risk*\n"
        "• Advanced alerts — percent, volume, risk, indicators\n"
        "• Watch alerts — track coin moves over time (`/watch`)\n"
        "• `/levels` — Key support & resistance zones\n\n"

        "*AI & Market Intelligence*\n"
        "• `/setup` - Professional Setup Analyzer\n"
        "• `/analysis` — AI-powered technical analysis\n"
        "• `/aiscan` — Detect patterns: divergence, crosses, etc.\n"
        "• `/regime` — Market regime & risk assessment\n"
        "• `/hold` — Capital preservation analysis (hold vs exit)\n"
        "• `/today` — Today's market summary\n\n"

        "*Research & Strategy*\n"
        "• `/bt` — Strategy backtesting\n"
        "• `/screen` — Scan top coins for setups\n\n"

        "*Portfolio & Smart Risk*\n"
        "• Portfolio SL / TP automation\n"
        "• Advanced portfolio risk controls\n\n"
        
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=pro_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
      
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
        "• `/feedback` — Share your review\n"
         "• `/privacy` - View our privacy policy and terms\n"
        "• `/support` — Contact support"
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
	
    keyboard = [
  	  [
  	      InlineKeyboardButton("🔔 Alerts", callback_data="alerts"),
  	      InlineKeyboardButton("📈 Popular Commands", callback_data="popular_commands"),
     	   InlineKeyboardButton("📊 Markets", callback_data="markets")
	    ],
	    [
      	  InlineKeyboardButton("💰 Trade", callback_data="trade"),
      	  InlineKeyboardButton("📁 Portfolio", callback_data="portfolio"),
       	 InlineKeyboardButton("📚 Learn", callback_data="learn")
	    ],
 	   [
      	  InlineKeyboardButton("🚀 Pro Features", callback_data="pro_features"),
     	   InlineKeyboardButton("📲 Upgrade", callback_data="upgrade_menu"),
      	  InlineKeyboardButton("👤 Account", callback_data="account")
    	]
	]

    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
    f"👋 Welcome, *{name}*.\n\n"
    f"This bot helps you make trading decisions using market data,\n"
    f"technical indicators, and structured analysis — not hype.\n\n"
    f"It’s built to find *opportunity and protection* in both rising and falling markets.\n\n"
    f"You don’t need to set anything up. Start here:\n\n"
    f"`/btc` — Live BTC market analysis\n"
    f"`/today` — Trade or wait? Market risk & bias\n"
    f"`/set` — Create a price alert\n"
    f"`/menu` — Explore all features\n\n"
    f"What this bot focuses on:\n"
    f"• Market context (trend, regime, levels)\n"
    f"• Risk-aware alerts, not random noise\n"
    f"• Clear answers to when *not* to trade\n\n"
    f"No financial advice.\n"
    f"Just market intelligence.\n\n"
    f"Tip: Most users start with `/set`."
)

    await query.edit_message_text(text=welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
