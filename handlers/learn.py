# handlers/learn.py
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load glossary once
with open("utils/glossary.json") as f:
    GLOSSARY = json.load(f)

ITEMS_PER_PAGE = 6  # Number of terms per page

# /learn command entry
async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    await send_learn_page(update, page=0)

# Callback: pagination like learn_page_1
async def learn_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[-1])
    await send_learn_page(update, page, edit=True, query=query)

# Callback: show selected term like learn_5_0
async def learn_term_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    idx = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    await send_term_detail(query, idx, page)

# Callback: show random term
async def learn_random_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = random.randint(0, len(GLOSSARY) - 1)
    page = idx // ITEMS_PER_PAGE  # For back button context

    await send_term_detail(query, idx, page)

# Helper: show term detail with back + random buttons
async def send_term_detail(query, idx, page):
    term = GLOSSARY[idx]
    text = f"*{term['term']}*\n\n{term['description']}"

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"learn_page_{page}"),
            InlineKeyboardButton("🎲 Random", callback_data="learn_random")
        ]
    ])

    await query.edit_message_text(text=text, reply_markup=markup, parse_mode="Markdown")

# Helper: show glossary page
async def send_learn_page(update, page=0, edit=False, query=None):
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    buttons = []

    for i, term in enumerate(GLOSSARY[start:end], start=start):
        buttons.append([
            InlineKeyboardButton(term["term"], callback_data=f"learn_{i}_{page}")
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"learn_page_{page - 1}"))
    if end < len(GLOSSARY):
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"learn_page_{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(buttons)
    text = "📘 *Crypto Basics*\nTap a term to learn more."

    if edit and query:
        await query.edit_message_text(text=text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text=text, reply_markup=markup, parse_mode="Markdown")