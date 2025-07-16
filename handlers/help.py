from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

help_pages = {
    1: "*📖 Alerts & Market Tools (Free)*\n\n"
       "• `/set price BTC > 65000` – Alert when price crosses value \n"
       "• `/alerts` – View your active alerts\n"
       "• `/remove TYPE ID` – Remove a specific alert\n"
       "• `/removeall` – Delete all alerts\n"
       "• `/chart BTC` – 1h TradingView chart\n"
       "• `/BTC` – Coin info: price, % change, ATH, market cap\n"
       "• `/trend BTC` – Technicals (1h only)\n"
       "• `/best` / `/worst` – Top 3 gainers/losers\n"
       "• `/news` – Latest 5 crypto headlines\n",

    2: "*💎 Advanced Features (Pro)*\n\n"
       "• `/set percent BTC 5` – Alert on % changes\n"
       "• `/set volume BTC 2x` – Volume spike alert\n"
       "• `/set risk BTC 50000 60000` – Stop-loss / take-profit\n"
       "• `/set custom BTC > 50000 EMA > 200` – Combine price + indicators\n"
       "• `/chart BTC 4h`, `/trend ETH 1d` – All timeframes\n"
       "• `/prediction BTC 1h` – AI-based price prediction\n"
       "• `/watch BTC 5 1h` – Watchlist alert\n"
       "• `/watchlist` / `/removewatch BTC`\n"
       "• `/portfolio`, `/addasset`, `/removeasset`, `/clearportfolio`\n"
       "• `/portfoliolimit`, `/portfoliotarget`\n",

    3: "*🎯 Get 1 Month Pro Free*\n\n"
       "• `/tasks` – Complete 3 simple tasks:\n"
       "   ┗ Helps promote the bot and grow users\n"
       "• After approval, enjoy 30 days of Pro access!\n\n"
       "*📢 Referral System:*\n"
       "• `/referral` – Get your referral link\n"
       "• Invite friends and earn rewards\n\n"
       "*🔼 Plans:*\n"
       "• Free: Unlimited price alerts, 1h chart only\n"
       "• Pro: Unlimited alerts, AI tools, portfolio, watchlist\n"
       "• Use `/upgrade` to view Pro benefits\n",

    4: "*🌐 Community & Support*\n\n"
       "• `/start` – Welcome menu with quick access buttons\n"
       "• [Join Group](https://t.me/+tSWwj5w7S8hkZmM0) – Ask questions or share ideas\n"
       "• Need help? Use `/tasks` or DM admin\n\n"
       "We’re building the most powerful crypto assistant for Telegram 🚀"
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
        