from telegram import Update
from telegram.ext import ContextTypes
from models.db import get_connection
from models.user import set_user_plan

async def handle_task_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    try:
        action, user_id, task_num = query.data.split("|")
        user_id = int(user_id)
        task_num = int(task_num)

        conn = get_connection()
        cursor = conn.cursor()

        # Update the task based on action
        if action == "approve_task":
            cursor.execute(f"UPDATE task_progress SET task{task_num}_done = 2 WHERE user_id = ?", (user_id,))
            response_text = f"✅ Task {task_num} approved for user {user_id}."
        elif action == "reject_task":
            cursor.execute(f"UPDATE task_progress SET task{task_num}_done = 0, proof{task_num} = NULL WHERE user_id = ?", (user_id,))
            response_text = f"❌ Task {task_num} rejected for user {user_id}."

        # Commit before next check
        conn.commit()

        # Check if all tasks are approved
        cursor.execute("SELECT task1_done, task2_done, task3_done, reward_given FROM task_progress WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            task1, task2, task3, reward_given = row
            if all(t == 2 for t in [task1, task2, task3]) and not reward_given:
                set_user_plan(user_id, "pro")

                # Flag reward as given
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE task_progress SET reward_given = 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()

                # Notify user
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Congrats! You’ve unlocked *1 month of Pro Access*. Enjoy your features! 💎",
                    parse_mode="Markdown"
                )

        # 🛠 EDIT ORIGINAL MESSAGE (caption or text)
        if query.message.photo:
            await query.edit_message_caption(response_text)
        else:
            await query.edit_message_text(response_text)

    except Exception as e:
        print("❌ Error in handle_task_review_callback:", e)
        try:
            if query.message.photo:
                await query.edit_message_caption("⚠️ Failed to process this request.")
            else:
                await query.edit_message_text("⚠️ Failed to process this request.")
        except Exception as inner_error:
            print("⚠️ Nested error while editing message:", inner_error)