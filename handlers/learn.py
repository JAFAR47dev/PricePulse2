# handlers/learn.py
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

# Load glossary once
with open("utils/glossary.json") as f:
    GLOSSARY = json.load(f)

ITEMS_PER_PAGE = 6  # Number of terms per page

# /learn entry command
async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_learn_page(update, page=0)

# Handles pagination callback: learn_page_1, learn_page_2, etc
async def learn_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    page = int(query.data.split("_")[-1])
    await send_learn_page(update, page, edit=True, query=query)

# Handles actual term display: learn_5, learn_13
async def learn_term_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[1])
    term = GLOSSARY[idx]

    text = f"*{term['term']}*\n\n{term['description']}"
    await query.edit_message_text(text=text, parse_mode="Markdown")

# Helper: sends paginated term buttons
async def send_learn_page(update, page=0, edit=False, query=None):
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    buttons = []

    for i, term in enumerate(GLOSSARY[start:end], start=start):
        buttons.append([InlineKeyboardButton(term["term"], callback_data=f"learn_{i}")])

    # Pagination buttons
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
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")