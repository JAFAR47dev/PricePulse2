import os
import httpx
import urllib.parse
from bs4 import BeautifulSoup
from io import BytesIO
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from tasks.handlers import handle_streak

SCREENSHOT_ONE_KEY = os.getenv("SCREENSHOT_ONE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ✅ Helper: Capture screenshot using ScreenshotOne (same as your /c command)
async def capture_screenshot(url: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        encoded_url = urllib.parse.quote(url, safe="")
        screenshot_url = (
            f"https://api.screenshotone.com/take"
            f"?access_key={SCREENSHOT_ONE_KEY}"
            f"&url={encoded_url}"
            f"&format=png&viewport_width=1280&viewport_height=720"
        )

        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.get(screenshot_url)

        if resp.status_code != 200:
            try:
                err = resp.json()
                code = err.get("error_code", "unknown")
                msg = err.get("error_message", resp.text)
            except Exception:
                code, msg = "unknown", resp.text

            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ Screenshot API error ({code}):\n`{escape_markdown(msg, version=2)}`",
                    parse_mode="MarkdownV2"
                )
            return None

        return BytesIO(resp.content)

    except Exception as e:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ Screenshot Exception:\n`{escape_markdown(str(e), version=2)}`",
                parse_mode="MarkdownV2"
            )
        return None
        
from telegram.helpers import escape_markdown

def md2(text: str) -> str:
    try:
        return escape_markdown(text, version=2)
    except:
        return text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)").replace("~", "\\~").replace("`", "\\`").replace(">", "\\>").replace("#", "\\#").replace("+", "\\+").replace("-", "\\-").replace("=", "\\=").replace("|", "\\|").replace("{", "\\{").replace("}", "\\}").replace(".", "\\.").replace("!", "\\!")
        

import httpx

async def fetch_tradingview_ideas(symbol: str = None, limit: int = 3):
    url = "https://scanner.tradingview.com/crypto/scan"

    payload = {
        "filter": [],
        "options": {"lang": "en"}
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        resp = await client.post(url, json=payload)

        if resp.status_code != 200:
            print(f"❌ TradingView JSON error ({resp.status_code})")
            return []

        json_data = resp.json()

    ideas = []

    for item in json_data.get("data", []):
        d = item.get("d")

        # 🔥 Normalize both dict and list types
        if isinstance(d, list):
            # TradingView list format (indexes vary, so we protect everything)
            title = d[0] if len(d) > 0 else "Untitled"
            ticker = d[1] if len(d) > 1 else ""
            link = d[2] if len(d) > 2 else ""
            description = d[3] if len(d) > 3 else ""
        elif isinstance(d, dict):
            # TradingView dict format
            title = d.get("headline", "Untitled")
            ticker = d.get("v_symbol", "")
            link = d.get("scriptUrl", "")
            description = d.get("description", "")
        else:
            # Unknown format → skip safely
            continue

        # Optional filter
        if symbol and symbol.upper() not in title.upper() and symbol.upper() not in ticker.upper():
            continue

        ideas.append({
            "title": str(title),
            "link": str(link),
            "description": str(description),
            "ticker": str(ticker),
        })

        if len(ideas) >= limit:
            break

    return ideas
    
    
# ✅ Main command: /insights
async def insights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_streak(update, context)
    """Fetch and display trending crypto trade ideas with screenshots."""
    symbol = context.args[0].upper() if context.args else None
    await update.message.reply_text("🔍 Fetching latest TradingView ideas...")

    ideas = await fetch_tradingview_ideas(symbol)
    if not ideas:
        await update.message.reply_text("⚠️ No trending ideas found. Try again later.")
        return

    for idea in ideas:
        # Capture live screenshot using ScreenshotOne
        image_bytes = await capture_screenshot(idea["link"], context)

        title = md2(idea["title"])
        link = md2(idea["link"])
        description = md2(idea["description"])

        caption = f"*{title}*\n\n{description}\n[📈 View on TradingView]({link})"

        if image_bytes:
            await update.message.reply_photo(
                photo=InputFile(image_bytes, filename="idea.png"),
                caption=caption,
                parse_mode="MarkdownV2" 
            )
        else:
            await update.message.reply_text(
                caption,
                parse_mode="MarkdownV2"
            )
            
        if not image_bytes:
            await update.message.reply_text(f"*{title}*\n\n{description}\n[📈 View on TradingView]({link})",
                                    parse_mode="MarkdownV2")
            continue