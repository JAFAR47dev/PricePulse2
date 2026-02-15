import os
import httpx
import urllib.parse
from io import BytesIO
from bs4 import BeautifulSoup
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

SCREENSHOT_ONE_KEY = os.getenv("SCREENSHOT_ONE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


# ✅ Helper: Safe MarkdownV2 escaping
def md2(text: str) -> str:
    """Safely escape text for Telegram MarkdownV2."""
    if not text:
        return ""
    try:
        return escape_markdown(str(text), version=2)
    except Exception:
        # Fallback manual escaping
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        result = str(text)
        for char in special_chars:
            result = result.replace(char, f'\\{char}')
        return result


# ✅ Helper: Capture screenshot using ScreenshotOne
async def capture_screenshot(url: str, context: ContextTypes.DEFAULT_TYPE):
    """Capture a screenshot of the given URL using ScreenshotOne API."""
    try:
        encoded_url = urllib.parse.quote(url, safe="")
        screenshot_url = (
            f"https://api.screenshotone.com/take"
            f"?access_key={SCREENSHOT_ONE_KEY}"
            f"&url={encoded_url}"
            f"&format=png&viewport_width=1280&viewport_height=720"
            f"&full_page=false"
        )

        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.get(screenshot_url)

        if resp.status_code != 200:
            try:
                err = resp.json()
                code = err.get("error_code", "unknown")
                msg = err.get("error_message", resp.text[:200])
            except Exception:
                code, msg = "unknown", resp.text[:200]

            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ Screenshot API error ({code}):\n`{md2(msg)}`",
                    parse_mode="MarkdownV2"
                )
            return None

        return BytesIO(resp.content)

    except httpx.TimeoutException:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text="❌ Screenshot timeout after 40 seconds",
                parse_mode="MarkdownV2"
            )
        return None
    except Exception as e:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ Screenshot Exception:\n`{md2(str(e))}`",
                parse_mode="MarkdownV2"
            )
        return None


async def fetch_tradingview_ideas(symbol: str = None, limit: int = 1):
    """Fetch the top trending crypto idea from TradingView."""
    
    # Build the URL based on whether a symbol is provided
    if symbol:
        url = f"https://www.tradingview.com/symbols/{symbol.upper()}/ideas/"
    else:
        url = "https://www.tradingview.com/markets/cryptocurrencies/ideas/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.tradingview.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin"
    }

    try:
        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)

            if resp.status_code != 200:
                print(f"❌ TradingView page error ({resp.status_code})")
                return []

            # Parse HTML
            soup = BeautifulSoup(resp.text, 'html.parser')
            ideas = []
            
            # Try multiple selectors to find idea cards
            # TradingView uses different class names, so we try several approaches
            
            # Method 1: Look for idea cards with data-id attribute
            idea_cards = soup.find_all('div', attrs={'data-id': True}, limit=limit + 2)
            
            if not idea_cards:
                # Method 2: Look for article elements
                idea_cards = soup.find_all('article', limit=limit + 2)
            
            if not idea_cards:
                # Method 3: Look for specific card class patterns
                idea_cards = soup.find_all('div', class_=lambda x: x and 'card' in x.lower(), limit=limit + 2)
            
            print(f"Found {len(idea_cards)} potential idea cards")
            
            for card in idea_cards:
                if len(ideas) >= limit:
                    break
                    
                try:
                    # Extract link first (most important)
                    link_elem = card.find('a', href=lambda x: x and '/chart/' in x)
                    if not link_elem:
                        link_elem = card.find('a', href=True)
                    
                    if not link_elem or not link_elem.get('href'):
                        continue
                    
                    link = link_elem['href']
                    if not link.startswith('http'):
                        link = f"https://www.tradingview.com{link}"
                    
                    # Extract title
                    title = None
                    # Try to find title in various places
                    title_elem = (
                        card.find('h2') or 
                        card.find('h3') or 
                        card.find('a', {'class': lambda x: x and 'title' in str(x).lower()}) or
                        link_elem
                    )
                    
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    
                    if not title or len(title) < 3:
                        title = "Trading Idea"
                    
                    # Extract description
                    description = "Check out this trading idea on TradingView"
                    desc_elem = card.find('p') or card.find('div', class_=lambda x: x and 'description' in str(x).lower())
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)
                    
                    # Extract ticker/symbol
                    ticker = ""
                    ticker_elem = card.find('span', class_=lambda x: x and ('ticker' in str(x).lower() or 'symbol' in str(x).lower()))
                    if ticker_elem:
                        ticker = ticker_elem.get_text(strip=True)
                    
                    ideas.append({
                        "title": title[:200],  # Limit title length
                        "link": link,
                        "description": description[:400],  # Limit description
                        "ticker": ticker,
                    })
                    
                    print(f"✅ Extracted idea: {title[:50]}")
                    
                except Exception as e:
                    print(f"⚠️ Error parsing idea card: {e}")
                    continue
            
            # If we still have no ideas, create a fallback popular chart
            if not ideas:
                print("⚠️ No ideas found via scraping, using fallback popular chart")
                fallback_symbol = symbol.upper() + 'USD' if symbol else 'BTCUSD'
                
                ideas.append({
                    "title": f"{fallback_symbol} Technical Analysis",
                    "link": f"https://www.tradingview.com/chart/?symbol={fallback_symbol}",
                    "description": f"View the latest technical analysis and trading ideas for {fallback_symbol} on TradingView",
                    "ticker": fallback_symbol,
                })
            
            return ideas

    except Exception as e:
        print(f"❌ TradingView fetch exception: {e}")
        
        # Return fallback idea if everything fails
        if symbol:
            return [{
                "title": f"{symbol.upper()} Chart Analysis",
                "link": f"https://www.tradingview.com/chart/?symbol={symbol.upper()}USD",
                "description": f"View live chart and technical analysis for {symbol.upper()}",
                "ticker": symbol.upper(),
            }]
        else:
            return [{
                "title": "Bitcoin (BTC) Analysis",
                "link": "https://www.tradingview.com/chart/?symbol=BTCUSD",
                "description": "View the latest Bitcoin technical analysis and price action",
                "ticker": "BTCUSD",
            }]


# ✅ Main command: /insights
async def insights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch and display the top trending crypto trade idea with screenshot."""
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/insights")
    await handle_streak(update, context)

    symbol = context.args[0].upper() if context.args else None
    
    status_msg = await update.message.reply_text("🔍 Fetching top TradingView idea...")

    ideas = await fetch_tradingview_ideas(symbol, limit=1)
    
    if not ideas:
        await status_msg.edit_text("⚠️ No trending ideas found. Try again later.")
        return

    await status_msg.delete()

    # Get the single idea
    idea = ideas[0]
    
    try:
        # Prepare caption
        title = md2(idea["title"])
        link = idea["link"]  # Don't escape the raw URL
        description = md2(idea["description"][:300])  # Show more description since it's just one

        # Build caption with proper escaping
        caption = f"*{title}*\n\n{description}\n\n[📈 View on TradingView]({link})"

        # Capture screenshot
        image_bytes = await capture_screenshot(idea["link"], context)

        if image_bytes:
            await update.message.reply_photo(
                photo=InputFile(image_bytes, filename="tradingview_idea.png"),
                caption=caption,
                parse_mode="MarkdownV2"
            )
        else:
            # Fallback to text if screenshot fails
            await update.message.reply_text(
                caption,
                parse_mode="MarkdownV2",
                disable_web_page_preview=False
            )

    except Exception as e:
        print(f"❌ Error sending idea: {e}")
        # Try sending without markdown as last resort
        try:
            plain_text = f"{idea['title']}\n\n{idea['description'][:300]}\n\nView: {idea['link']}"
            await update.message.reply_text(plain_text)
        except Exception:
            await update.message.reply_text("⚠️ Error displaying the trading idea. Please try again.")