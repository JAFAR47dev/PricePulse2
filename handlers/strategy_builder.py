import os
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from dotenv import load_dotenv
from utils.auth import is_pro_plan
from models.user import get_user_plan
from models.ai_alerts import save_ai_strategy
from models.user_activity import update_last_active

load_dotenv()

AWAITING_STRATEGY_INPUT = 1

async def strategy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        return await update.message.reply_text(
            "❌ This is a *Pro-only* feature. Upgrade to Pro to access AI strategy builder.\n\n👉 /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )

    await update.message.reply_text(
        "🧠 *Describe your trading strategy in plain English.*\n\nExample:\n"
        "`Alert me when BTC is oversold, MACD flips bullish, and price is 3% below 7d average`",
        parse_mode=ParseMode.MARKDOWN
    )
    return AWAITING_STRATEGY_INPUT


async def handle_strategy_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    await update.message.reply_text("🔍 Parsing your strategy... Please wait.")

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""
You are a crypto trading assistant. A user describes a strategy in plain English. Extract the core logic and convert it into structured alert instructions.

Reply in this format:
- Coin: [Symbol]
- Condition 1: [Description]
- Condition 2: [Description]
- Condition 3: [Description]
- Summary: [Short explanation of what this strategy does]

User input: "{user_input}"
"""
                    }
                ]
            },
            timeout=20
        )

        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"].strip()

            # Save to session memory for later confirmation
            context.user_data["parsed_strategy"] = content

            buttons = [
                [
                    InlineKeyboardButton("✅ Confirm Strategy", callback_data="confirm_strategy"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_strategy")
                ]
            ]

            await update.message.reply_text(
                f"🛠 *Custom Alert Strategy:*\n\n{content}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            print("Strategy Builder error:", response.status_code, response.text)
            await update.message.reply_text("❌ Failed to parse strategy. Try again later.")
            return ConversationHandler.END

    except Exception as e:
        print("Strategy Builder exception:", e)
        await update.message.reply_text("⚠️ An error occurred. Please try again later.")
        return ConversationHandler.END



async def confirm_strategy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    strategy = context.user_data.get("parsed_strategy")
    if not strategy:
        await query.edit_message_text("⚠️ No strategy to confirm.")
        return

    user_id = query.from_user.id

    # Parse structured data from the confirmed strategy text
    lines = strategy.splitlines()
    symbol = None
    conditions = []
    summary = ""

    for line in lines:
        if line.lower().startswith("coin:"):
            symbol = line.split(":", 1)[1].strip()
        elif line.lower().startswith("condition"):
            condition = line.split(":", 1)[1].strip()
            conditions.append(condition)
        elif line.lower().startswith("summary:"):
            summary = line.split(":", 1)[1].strip()

    if not symbol or not conditions:
        await query.edit_message_text("⚠️ Failed to parse strategy. Please try again.")
        return

    # Save to DB
    save_ai_strategy(user_id, symbol, conditions, summary)

    # Confirm to user
    await query.edit_message_text(
        "✅ Strategy confirmed and saved!\n\n"
        "We’ll monitor the conditions and notify you when they're met."
    )
    context.user_data.pop("parsed_strategy", None)
    
async def cancel_strategy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):  
    query = update.callback_query  
    await query.answer()  
    context.user_data.pop("parsed_strategy", None)  
  
    await query.edit_message_text("❌ Strategy cancelled. You can try again using /aistrat") 