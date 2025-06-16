from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from models.db import get_connection
from config import ADMIN_ID

async def review_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT tp.user_id, u.username, tp.task1_done, tp.task2_done, tp.task3_done,
               tp.proof1, tp.proof2, tp.proof3
        FROM task_progress tp
        LEFT JOIN users u ON tp.user_id = u.user_id
        WHERE tp.proof1 IS NOT NULL OR tp.proof2 IS NOT NULL OR tp.proof3 IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 No task submissions to review.")
        return

    for row in rows:
        user_id, username, t1, t2, t3, p1, p2, p3 = row
        username_display = f"@{username}" if username else f"(ID: {user_id})"
        text = f"👤 User: `{username_display}`\n"

        for i, (done, proof) in enumerate([(t1, p1), (t2, p2), (t3, p3)], start=1):
            if done == 0:
                text += f"• Task {i}: ❌ Not submitted\n"
            elif proof:
                text += f"• Task {i}: 🕓 Submitted – [View Below]\n"
            else:
                text += f"• Task {i}: 🕓 Submitted\n"

        await update.message.reply_text(
            text,
            parse_mode="Markdown"
        )

        # Send separate proof message per task
        for i, proof in enumerate([p1, p2, p3], start=1):
            if not proof:
                continue

            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_task|{user_id}|{i}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_task|{user_id}|{i}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Escape proof for MarkdownV2
            try:
                escaped_proof = escape_markdown(str(proof), version=2)
            except:
                escaped_proof = "⚠️ Could not render proof"

            # If proof is a file_id, assume image
            if str(proof).startswith("AgA"):
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=proof,
                    caption=f"📎 *Proof for Task {i} from* `{username_display}`:\n\n{escaped_proof}",
                    parse_mode="MarkdownV2",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    f"📎 *Proof for Task {i} from* `{username_display}`:\n\n{escaped_proof}",
                    parse_mode="MarkdownV2",
                    reply_markup=reply_markup
                )