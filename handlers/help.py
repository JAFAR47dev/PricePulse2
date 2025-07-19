from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

help_pages = {
    1: "*📖 Core Features (Free)*\n\n"
       "• `/set price BTC > 65000` – Price alert\n"
       "• `/alerts` – View all alerts\n"
       "• `/remove TYPE ID` – Remove specific alert\n"
       "• `/removeall` – Remove all alerts\n"
       "• `/c BTC` or `/chart BTC` – 1h TradingView chart\n"
       "• `/BTC` – Full coin info: price, % change, volume, etc.\n"
       "• `/trend BTC` – Technical analysis (1h only)\n"
       "• `/best`, `/worst` – Top 3 Gainers/Losers (24h)\n"
       "• `/news` – Latest 5 crypto headlines\n"
       "• `/comp BTC ETH SOL` – Compare market data\n"
       "• `/cod` – Coin of the Day\n"
       "• `/conv 1 btc to usd` – Crypto & fiat conversion\n"
       "• `/hmap` – Top 50 coin heatmap\n"
       "• `/learn` – Key crypto terms\n"
       "• `/funfact` – Random crypto facts\n"
       "• `/markets BTC` – Exchange prices\n"
       "• `/links BTC` – Official coin links\n",

    2: "*💎 Pro-Only Features (Advanced Alerts, Portfolio, AI)*\n\n"
       "🔔 *Advanced Alerts:*\n"
       "• `/set percent BTC 5` – % move alert\n"
       "• `/set volume BTC 2x` – Volume spike alert\n"
       "• `/set risk BTC 50000 60000` – SL/TP alert\n"
       "• `/set custom BTC > 50000 MACD > 0` – Custom indicators\n\n"
       "📈 *Portfolio & Watchlist:*\n"
       "• `/addasset BTC 0.5` / `/portfolio` – Track holdings\n"
       "• `/portfoliolimit 15000` – Set loss alert\n"
       "• `/portfoliotarget 25000` – Set profit alert\n"
       "• `/removeasset BTC`, `/clearportfolio`\n"
       "• `/watch BTC 5 1h` – Watch % change\n"
       "• `/watchlist` / `/removewatch BTC`\n",

    3: "*🤖 AI Tools & Screeners (Pro)*\n\n"
       "• `/prediction BTC 1h` – AI price prediction\n"
       "• `/aistrat` – Natural language alert builder\n"
       "• `/aiscan` – Detect patterns: divergence, crosses, etc.\n"
       "• `/bt BTC 1h` – Backtest strategies with AI summary\n"
       "• `/screen` – Scan top 200 coins for setups\n"
       "• `/track` – Whale wallet tracker (on-chain alerts)\n",

    4: "*🎁 Get Pro for Free + Referrals*\n\n"
       "• `/tasks` – Complete 3 growth tasks to unlock 30-day Pro\n"
       "• Tasks directly help grow user base\n"
       "• `/referral` – Get your unique referral link\n"
       "• Earn rewards for each invited user\n\n"
       "*🔓 Plans Overview:*\n"
       "• Free: Price alerts, basic charts/tools\n"
       "• Pro: AI tools, portfolio, advanced alerts, screener, more\n"
       "• Use `/upgrade` for pricing & crypto payment\n",

    5: "*🌍 Forex Tools & Community*\n\n"
       "• `/fx eurusd` – Live forex rates\n"
       "• `/fxcal` – Upcoming forex events (7 days)\n"
       "• `/fxconv 100 gbp to usd` – Fiat conversions\n"
       "• `/fxsessions` – Open forex markets\n\n"
       "• `/start` – Onboarding, social proof, buttons\n"
       "• [Join Community](https://t.me/+tSWwj5w7S8hkZmM0) – Questions & updates\n"
       "• Admin support via `/tasks` or DM if needed\n\n"
       "🚀 *We’re building the smartest Telegram crypto bot!*"
}

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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