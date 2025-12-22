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
        return await update.message.reply_text(
            "❌ Usage: /links [coin] (e.g. /links btc)"
        )

    symbol = context.args[0].upper()
    coin_id = COINGECKO_IDS.get(symbol)

    if not coin_id:
        return await update.message.reply_text("❌ Unsupported or unknown coin symbol.")

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        name = data.get("name", symbol)
        links = data.get("links", {})

        text_lines = [
            f"🔗 *Official Links for {name}*",
            ""
        ]

        # 🌐 Website
        homepage = next((h for h in links.get("homepage", []) if h), None)
        if homepage:
            text_lines.append(f"🌐 Website: [Visit]({homepage})")

        # 🐦 Twitter / X
        twitter = links.get("twitter_screen_name")
        if twitter:
            text_lines.append(f"🐦 X: [@{twitter}](https://twitter.com/{twitter})")

        # 📣 Telegram
        telegram = links.get("telegram_channel_identifier")
        if telegram:
            text_lines.append(f"📣 Telegram: [Join](https://t.me/{telegram})")

        # 💬 Discord
        discord = links.get("chat_url", [])
        discord_link = next((d for d in discord if "discord" in d.lower()), None)
        if discord_link:
            text_lines.append(f"💬 Discord: [Join]({discord_link})")

        # 👽 Reddit
        reddit = links.get("subreddit_url")
        if reddit:
            text_lines.append(f"👽 Reddit: [Subreddit]({reddit})")

        # 💻 GitHub
        github_repos = links.get("repos_url", {}).get("github", [])
        if github_repos:
            text_lines.append(f"💻 GitHub: [Repo]({github_repos[0]})")

        # 📘 Facebook
        facebook = links.get("facebook_username")
        if facebook:
            text_lines.append(f"📘 Facebook: [Page](https://facebook.com/{facebook})")

        # 🧵 Bitcointalk
        bitcointalk = links.get("bitcointalk_thread_identifier")
        if bitcointalk:
            text_lines.append(
                f"🧵 Bitcointalk: [Thread](https://bitcointalk.org/index.php?topic={bitcointalk})"
            )

        # ✍️ Medium
        medium = links.get("medium")
        if medium:
            text_lines.append(f"✍️ Medium: [Blog]({medium})")

        if len(text_lines) <= 2:
            text_lines.append("⚠️ No official links found.")

        await update.message.reply_text(
            "\n".join(text_lines),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    except Exception as e:
        print("Links command error:", e)
        await update.message.reply_text(
            "⚠️ Could not fetch links. Try a valid coin like /links eth"
        )