from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
import feedparser

CRYPTO_NEWS_RSS = "https://cryptopanic.com/news/rss/"

async def crypto_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        loading = await update.message.reply_text("📰 Fetching latest crypto news...")

        feed = feedparser.parse(CRYPTO_NEWS_RSS)
        entries = feed.entries[:5]  # Get top 5

        if not entries:
            await loading.edit_text("❌ No news found at the moment.")
            return

        message = "*📰 Latest Crypto News:*\n\n"
        for entry in entries:
            title = entry.title
            link = entry.link
            message += f"• [{title}]({link})\n"

        await loading.edit_text(message, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        print(f"/news error: {e}")
        await update.message.reply_text("⚠️ Failed to fetch crypto news. Try again later.")
        