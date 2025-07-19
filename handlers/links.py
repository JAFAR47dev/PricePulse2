# handlers/links.py
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

async def links_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /links [coin]")

    coin = context.args[0].lower()

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        name = data.get("name", coin.upper())
        links = data.get("links", {})

        homepage = links.get("homepage", [""])[0]
        twitter = links.get("twitter_screen_name", "")
        reddit = links.get("subreddit_url", "")
        github = links.get("repos_url", {}).get("github", [])

        text = f"🔗 *Official Links for {name}*\n\n"

        if homepage:
            text += f"🌐 Website: [Visit]({homepage})\n"
        if twitter:
            text += f"🐦 Twitter: [@{twitter}](https://twitter.com/{twitter})\n"
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