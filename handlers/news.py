import feedparser
from tasks.handlers import handle_streak

CRYPTO_NEWS_RSS = "https://cryptopanic.com/news/rss/"

# --- Reusable function for notifications ---
async def get_latest_crypto_news() -> str:
    """Fetch top 5 crypto news and return a formatted Markdown string."""
    try:
        feed = feedparser.parse(CRYPTO_NEWS_RSS)
        entries = feed.entries[:5]  # Top 5 news

        if not entries:
            return "❌ No news found at the moment."

        message = "*📰 Latest Crypto News:*\n\n"
        for entry in entries:
            title = entry.title
            link = entry.link
            message += f"• [{title}]({link})\n"

        return message

    except Exception as e:
        print(f"[News] Error fetching crypto news: {e}")
        return "⚠️ Failed to fetch crypto news."


# --- Keep original command working ---
from telegram import Update
from telegram.ext import ContextTypes

async def crypto_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_streak(update, context)
    loading = await update.message.reply_text("📰 Fetching latest crypto news...")
    message = await get_latest_crypto_news()
    await loading.edit_text(message, parse_mode="Markdown", disable_web_page_preview=True)