from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from models.user_activity import update_last_active

help_pages = {
    1: "*📖 Core Features (Free)*\n\n"
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
       "• `/news` — Get latest 5 crypto headlines\n"
       "• `/cod` — Coin of the day\n"
       "• `/global` — Crypto market overview\n"
       "• `/gas` — ETH gas fees\n"
       "• `/markets btc` — Prices on major exchanges\n"
       "• `/fav` — Keep track of your favorite crypto\n"
       "• `/links btc` — Official links for any coin\n\n"
    
       "📚 *Education & Fun:*\n"
       "• `/learn` — Crypto terms explained\n"
       "• `/funfact` — Random crypto fact\n\n"
    
       "📐 *Utilities:*\n"
       "• `/calc btc 100` — Crypto/fiat calculator\n"
       "• `/conv 2 eth to usd` — Crypto conversion\n"
       "• `/hmap` — Heatmap of top 100 coins\n"
       "• `/comp btc eth` – Compare 2–3 coins\n",
    
    2: "*💎 Pro-Only Features (Advanced Alerts, Portfolio, Trackers)*\n\n"
       "📈 *Advanced Alerts:*\n"
       "• `/set (percent) ` — Alert on % price changes\n"
       "• `/set (volume)` — Volume spike alert\n"
       "• `/set (risk) ` — Stop-loss / Take-profit alerts\n"
       "• `/set (indicator) ` — Indicator alerts\n\n"

       "🧾 *Portfolio Management:*\n"
       "• `/portfolio` — View total value of assets\n"
       "• `/add BTC 1.2` — Add coins to portfolio\n"
       "• `/removeasset BTC` — Remove a coin\n"
       "• `/clearpf` — Clear all assets\n"
       "• `/pflimit 15000 [repeat]` — Set a loss alert with optional repeat keyword\n"
       "• `/pftarget 25000 [repeat]` — Set a profit alert with optional repeat keyword\n\n"

       "🔔 *Watchlist Tools:*\n"
       "• `/watch BTC 5 1h` — Alert for ±% moves\n"
       "• `/watchlist` — View all watch alerts\n"
       "• `/removewatch BTC` — Remove coin from watchlist\n\n"
    
       "🐋 *On-Chain Tools:*\n"
       "• `/track` – Track whale wallets\n"
       "• `/untrack` – Stop tracking\n"
       "• `/mywhales` – View whale alerts\n",
    
    3: "*🤖 AI Tools & Screeners (Pro)*\n\n"
       "• `/prediction BTC 1h` – AI price prediction\n"
       "• `/aiscan` – Detect patterns: divergence, crosses, etc.\n"
       "• `/bt BTC 1h rsi` – Backtest strategies with AI summary\n"
       "• `/screen` – Scan top 200 coins for setups\n"
       "• `/signals` — Get trading signals\n"
        "• `/regime` — Market regime overview\n"
        "• `/today` — Today's market summary\n",

    4: "*🎁 Growth and Navigation*\n\n"
       "• `/tasks` — Complete tasks to earn FREE Pro\n"
       "• `/referral` — Get your referral link\n\n"

       "🧭 *Navigation & Info:*\n"
       "• `/start` — Launch welcome menu\n"
       "• `/help` — View detailed guide\n"
       "• `/upgrade` — See Pro benefits & upgrade steps\n"
       "• `/myplan` — Check your subscription plan and expiry date\n"
       "• `/feedback` — Share your review\n"
       "• `/notifications` — Enable/disable bot notifications\n"
       "• `/addtogroup` — Add bot to your Telegram group\n",

    5: "*🌍 Forex Tools & Community*\n\n"
       "• `/fx eurusd` – Live forex rates\n"
       "• `/fxchart` – Forex Charts\n"
       "• `/fxsessions` – Open forex markets\n"
       "• [Join Community](https://t.me/+tSWwj5w7S8hkZmM0) – Questions & updates\n\n"
       "🚀 *We’re building the smartest Telegram crypto bot!*"
}

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/help")
    page = 1
    keyboard = [
        [InlineKeyboardButton("⏭️ Next", callback_data=f"help_page|{page+1}")],
        [InlineKeyboardButton("❌ Close", callback_data="help_close")]
    ]
    await update.message.reply_text(
        help_pages[page],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )

async def handle_help_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "help_close":
        await query.edit_message_text("ℹ️ Closed help menu.")
        return

    if data.startswith("help_page|"):
        _, page_str = data.split("|")
        page = int(page_str)

        text = help_pages.get(page, "⚠️ Page not found.")
        buttons = []

        if page > 1:
            buttons.append(InlineKeyboardButton("⏮️ Back", callback_data=f"help_page|{page-1}"))
        if page < len(help_pages):
            buttons.append(InlineKeyboardButton("⏭️ Next", callback_data=f"help_page|{page+1}"))

        buttons_markup = [buttons] if buttons else []
        buttons_markup.append([InlineKeyboardButton("❌ Close", callback_data="help_close")])

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons_markup),
            disable_web_page_preview=True
        )