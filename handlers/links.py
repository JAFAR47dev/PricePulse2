# handlers/links.py
import os
import json
import aiohttp
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load environment variables
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Prepare headers with API key if available
HEADERS = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}

# Load CoinGecko symbol-to-ID mapping
base_dir = os.path.dirname(os.path.abspath(__file__))
ids_path = os.path.join(base_dir, "../utils/coingecko_ids.json")

try:
    with open(ids_path, "r") as f:
        COINGECKO_IDS = json.load(f)
    # Normalize to uppercase for case-insensitive lookup
    COINGECKO_IDS = {k.upper(): v for k, v in COINGECKO_IDS.items()}
except FileNotFoundError:
    print(f"Warning: coingecko_ids.json not found at {ids_path}")
    COINGECKO_IDS = {}


def extract_links(links_data):
    """Extract and validate links from CoinGecko API response"""
    extracted = {}
    
    if not links_data or not isinstance(links_data, dict):
        return extracted
    
    # 🌐 Website (homepage)
    homepage_list = links_data.get("homepage", [])
    if isinstance(homepage_list, list):
        homepage = next((h for h in homepage_list if h and h.strip()), None)
        if homepage:
            extracted["website"] = homepage.strip()
    
    # 🐦 Twitter/X
    twitter = links_data.get("twitter_screen_name")
    if twitter and twitter.strip():
        extracted["twitter"] = twitter.strip()
    
    # 📣 Telegram
    telegram = links_data.get("telegram_channel_identifier")
    if telegram and telegram.strip():
        extracted["telegram"] = telegram.strip()
    
    # 💬 Discord (from chat_url list)
    chat_urls = links_data.get("chat_url", [])
    if isinstance(chat_urls, list):
        discord_link = next(
            (url for url in chat_urls if url and "discord" in url.lower()),
            None
        )
        if discord_link:
            extracted["discord"] = discord_link.strip()
    
    # 👽 Reddit
    reddit = links_data.get("subreddit_url")
    if reddit and reddit.strip():
        extracted["reddit"] = reddit.strip()
    
    # 💻 GitHub
    repos = links_data.get("repos_url", {})
    if isinstance(repos, dict):
        github_repos = repos.get("github", [])
        if isinstance(github_repos, list) and github_repos:
            first_repo = github_repos[0]
            if first_repo and first_repo.strip():
                extracted["github"] = first_repo.strip()
    
    # 📘 Facebook
    facebook = links_data.get("facebook_username")
    if facebook and facebook.strip():
        extracted["facebook"] = facebook.strip()
    
    # 🧵 Bitcointalk
    bitcointalk = links_data.get("bitcointalk_thread_identifier")
    if bitcointalk:
        extracted["bitcointalk"] = str(bitcointalk).strip()
    
    # ✍️ Medium
    medium = links_data.get("official_forum_url", [])
    if isinstance(medium, list):
        medium_link = next(
            (url for url in medium if url and "medium.com" in url.lower()),
            None
        )
        if medium_link:
            extracted["medium"] = medium_link.strip()
    
    return extracted


async def links_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/links")
    await handle_streak(update, context)

    if len(context.args) != 1:
        return await update.message.reply_text(
            "❌ Usage: `/links [coin]`\n\n"
            "Examples:\n"
            "`/links btc`\n"
            "`/links eth`\n"
            "`/links doge`",
            parse_mode=ParseMode.MARKDOWN
        )

    symbol = context.args[0].upper()
    coin_id = COINGECKO_IDS.get(symbol)

    if not coin_id:
        return await update.message.reply_text(
            f"❌ Unknown coin symbol: *{symbol}*\n\n"
            "Please use a valid symbol like BTC, ETH, or DOGE.",
            parse_mode=ParseMode.MARKDOWN
        )

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=15) as response:
                if response.status == 404:
                    return await update.message.reply_text(
                        f"❌ Coin *{symbol}* not found on CoinGecko.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                if response.status == 429:
                    return await update.message.reply_text(
                        "⚠️ Rate limit exceeded. Please try again in a moment."
                    )
                
                if response.status != 200:
                    raise Exception(f"API returned status {response.status}")
                
                data = await response.json()

        # Extract coin info
        name = data.get("name", symbol)
        links_data = data.get("links", {})
        
        # Extract all available links
        links = extract_links(links_data)

        # Build response message
        text_lines = [f"🔗 *Official Links for {name} ({symbol})*", ""]

        # Add links in order of importance
        if "website" in links:
            text_lines.append(f"🌐 Website: [Visit]({links['website']})")
        
        if "twitter" in links:
            text_lines.append(
                f"🐦 X: [@{links['twitter']}](https://twitter.com/{links['twitter']})"
            )
        
        if "telegram" in links:
            text_lines.append(
                f"📣 Telegram: [Join](https://t.me/{links['telegram']})"
            )
        
        if "discord" in links:
            text_lines.append(f"💬 Discord: [Join]({links['discord']})")
        
        if "reddit" in links:
            text_lines.append(f"👽 Reddit: [Subreddit]({links['reddit']})")
        
        if "github" in links:
            text_lines.append(f"💻 GitHub: [Repository]({links['github']})")
        
        if "facebook" in links:
            text_lines.append(
                f"📘 Facebook: [Page](https://facebook.com/{links['facebook']})"
            )
        
        if "bitcointalk" in links:
            text_lines.append(
                f"🧵 Bitcointalk: [Thread](https://bitcointalk.org/index.php?topic={links['bitcointalk']})"
            )
        
        if "medium" in links:
            text_lines.append(f"✍️ Medium: [Blog]({links['medium']})")

        # Check if any links were found
        if len(text_lines) <= 2:
            text_lines.append("⚠️ No official links available for this coin.")
        
        text_lines.append("")
        text_lines.append("_Data from CoinGecko_")

        await update.message.reply_text(
            "\n".join(text_lines),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    except aiohttp.ClientError as e:
        print(f"Links command network error: {e}")
        await update.message.reply_text(
            "⚠️ Network error. Please check your connection and try again."
        )
    except json.JSONDecodeError as e:
        print(f"Links command JSON error: {e}")
        await update.message.reply_text(
            "⚠️ Failed to parse response from CoinGecko. Try again later."
        )
    except Exception as e:
        print(f"Links command error: {type(e).__name__}: {e}")
        await update.message.reply_text(
            f"⚠️ Could not fetch links for *{symbol}*.\n"
            "Please try again or use a different coin symbol.",
            parse_mode=ParseMode.MARKDOWN
        )