File: handlers/tasks_admin.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup from telegram.ext import ContextTypes from models.task import get_pending_proofs, mark_proof_verified
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update from telegram.ext import ContextTypes, CallbackQueryHandler from models.db import get_connection

ADMIN_ID = 6203961971  # your Telegram user ID

ADMIN_ID = 5633927235 

async def admin_review(update: Update, context: ContextTypes.DEFAULT_TYPE): if update.effective_user.id != ADMIN_ID: await update.message.reply_text("⛔ You are not authorized to use this command.") return

pending = get_pending_proofs()

if not pending:
    await update.message.reply_text("✅ No pending submissions.")
    return

for row in pending:
    proof_id, user_id, task_id, proof_text, verified = row
    label = "Task 2" if task_id == 2 else "Task 3"

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{proof_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{proof_id}")
        ]
    ]

    markup = InlineKeyboardMarkup(keyboard)
    message_text = f"👤 User ID: `{user_id}`\n📌 {label} Submission:\n\n{proof_text}"

    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=markup
    )

handlers/tasks_admin.py (continue here)


async def handle_review_action(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer()

data = query.data.split(':')
if len(data) != 3:
    await query.edit_message_text("❌ Invalid action.")
    return

action, task_num, user_id = data
user_id = int(user_id)

conn = get_connection()
cursor = conn.cursor()

if action == "approve":
    cursor.execute("""
        UPDATE task_progress SET task_status = 1 
        WHERE user_id = ? AND task_id = ?
    """, (user_id, task_num))
    conn.commit()

    # Check if all tasks completed
    cursor.execute("SELECT COUNT(*) FROM task_progress WHERE user_id = ? AND task_status = 1", (user_id,))
    count = cursor.fetchone()[0]

    if count == 3:
        # Notify user of reward unlocked
        await context.bot.send_message(
            chat_id=user_id,
            text="🎁 Congratulations! You’ve completed all 3 tasks. An admin has approved them and your reward is now unlocked!"
        )

    await query.edit_message_text(f"✅ Approved Task {task_num} for user {user_id}")

elif action == "reject":
    cursor.execute("DELETE FROM task_progress WHERE user_id = ? AND task_id = ?", (user_id, task_num))
    conn.commit()
    await query.edit_message_text(f"❌ Rejected Task {task_num} for user {user_id}.")

conn.close()

def register_admin_task_handlers(app): 
    app.add_handler(CallbackQueryHandler(handle_review_action,                                    pattern=r"^(approve|reject):[23]:\d+$"))

