# handlers/links.py
import requests
import os
import json
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load CoinGecko symbol-to-ID mapping
with open("utils/coingecko_ids.json", "r") as f:
    COINGECKO_IDS = json.load(f)

async def links_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/links")
    await handle_streak(update, context)
    if len(context.args) != 1:
        return await update.message.reply_text("❌ Usage: /links [coin] (e.g. /links btc)")

    symbol = context.args[0].upper()
    coin_id = COINGECKO_IDS.get(symbol)

    if not coin_id:
        return await update.message.reply_text("❌ Unsupported or unknown coin symbol.")

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        name = data.get("name", symbol)
        links = data.get("links", {})

        homepage = links.get("homepage", [""])[0]
        twitter = links.get("twitter_screen_name", "")
        reddit = links.get("subreddit_url", "")
        github = links.get("repos_url", {}).get("github", [])

        text = f"🔗 *Official Links for {name}*\n\n"

        if homepage:
            text += f"🌐 Website: [Visit]({homepage})\n"
        if twitter:
            text += f"🐦 X: [@{twitter}](https://twitter.com/{twitter})\n"
        if reddit:
            text += f"👽 Reddit: [Subreddit]({reddit})\n"
        if github:
            text += f"💻 GitHub: [{github[0]}]({github[0]})\n"

        if text.strip() == f"🔗 *Official Links for {name}*":
            text += "⚠️ No official links found."

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Links command error:", e)
        await update.message.reply_text("⚠️ Could not fetch links. Try a valid coin like /links eth")