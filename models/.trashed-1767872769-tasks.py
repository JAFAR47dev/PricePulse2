import sqlite3
from models.db import get_connection

def init_task_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            user_id INTEGER PRIMARY KEY,
            invited_count INTEGER DEFAULT 0,
            invited_verified INTEGER DEFAULT 0,
            task2_proof TEXT,
            task2_verified INTEGER DEFAULT 0,
            task3_proof TEXT,
            task3_verified INTEGER DEFAULT 0,
            reward_given INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    
    
# FILE: handlers/tasks.py (continuation)
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler
from models.task import save_proof

async def handle_task_proof_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query or update.callback_query
    message = update.message or query.message if query else None
    user_id = update.effective_user.id

    if update.message:
        task_id = update.message.text.split("=submitproof_task")[-1].strip()
    else:
        task_id = update.data.split("submitproof_task")[-1].strip()

    if task_id not in ["2", "3"]:
        await message.reply_text("❌ Invalid task ID.")
        return

    context.user_data["proof_task"] = int(task_id)
    await message.reply_text("📸 Please send your proof (image or text) now:")


async def handle_task_proof_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    task_id = context.user_data.get("proof_task")

    if not task_id:
        await update.message.reply_text("❌ No task in progress. Use /tasks to start.")
        return

    proof = update.message.text or update.message.caption or "[Image Proof]"
    save_proof(user_id, task_id, proof)

    await update.message.reply_text(
        "✅ Your proof has been submitted for admin review.",
    )
    context.user_data.pop("proof_task", None)


def save_proof(user_id, task_id, proof):
    conn = get_connection()
    cursor = conn.cursor()

    if task_id == 2:
        cursor.execute("UPDATE user_tasks SET task2_proof = ? WHERE user_id = ?", (proof, user_id))
    elif task_id == 3:
        cursor.execute("UPDATE user_tasks SET task3_proof = ? WHERE user_id = ?", (proof, user_id))

    conn.commit()
    conn.close()



