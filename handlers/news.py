import feedparser
import requests
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Multiple RSS sources as fallback
CRYPTO_NEWS_SOURCES = [
    "https://cointelegraph.com/rss",
    "https://cryptonews.com/news/feed/",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
]

# --- Reusable function for notifications ---
async def get_latest_crypto_news() -> str:
    """Fetch top 5 crypto news and return a formatted Markdown string."""
    
    for source in CRYPTO_NEWS_SOURCES:
        try:
            # Fetch RSS feed with timeout using requests first
            response = requests.get(source, timeout=10)
            response.raise_for_status()
            
            # Then parse the content
            feed = feedparser.parse(response.content)
            
            # Better check for valid feed
            if not feed or not hasattr(feed, 'entries') or len(feed.entries) == 0:
                print(f"[News] No entries from {source}, trying next source...")
                continue
            
            entries = feed.entries[:5]  # Top 5 news
            
            message = "*📰 Latest Crypto News:*\n\n"
            for entry in entries:
                title = entry.get('title', 'Untitled')
                link = entry.get('link', '')
                
                # Clean up title (remove HTML entities, excessive spaces)
                title = title.strip().replace('\n', ' ')[:100]  # Max 100 chars
                
                if link:
                    message += f"• [{title}]({link})\n"
                else:
                    message += f"• {title}\n"
            
            print(f"[News] Successfully fetched from {source}")
            return message
        
        except requests.Timeout:
            print(f"[News] Timeout fetching from {source}")
            continue
        except requests.RequestException as e:
            print(f"[News] Request error with {source}: {e}")
            continue
        except Exception as e:
            print(f"[News] Error parsing {source}: {e}")
            continue
    
    # If all sources fail
    return "⚠️ Unable to fetch news from available sources. Please try again later."

# ============================================================================
# DATA FUNCTION (for notifications)
# ============================================================================

async def get_latest_crypto_news_data() -> list:
    """
    Fetch top 5 crypto news and return raw data as list of dicts.
    
    Returns:
        list: [{'title': str, 'url': str}, ...] or empty list on error
    """
    for source in CRYPTO_NEWS_SOURCES:
        try:
            response = requests.get(source, timeout=10)
            response.raise_for_status()
            
            feed = feedparser.parse(response.content)
            
            if not feed or not hasattr(feed, 'entries') or len(feed.entries) == 0:
                continue
            
            entries = feed.entries[:5]
            
            news_list = []
            for entry in entries:
                title = entry.get('title', 'Untitled').strip().replace('\n', ' ')[:100]
                link = entry.get('link', '')
                
                if link:
                    news_list.append({'title': title, 'url': link})
            
            if news_list:
                print(f"[News Data] Successfully fetched from {source}")
                return news_list
        
        except Exception as e:
            print(f"[News Data] Error with {source}: {e}")
            continue
    
    return []
    
# --- Keep original command working ---
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

async def crypto_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/news")
    await handle_streak(update, context)
    
    loading = await update.message.reply_text("📰 Fetching latest crypto news...")
    
    message = await get_latest_crypto_news()
    
    await loading.edit_text(
        message, 
        parse_mode=ParseMode.MARKDOWN, 
        disable_web_page_preview=True
    )
