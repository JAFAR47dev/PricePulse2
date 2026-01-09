from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import BOT_USERNAME
from telegram.ext import ContextTypes, CallbackQueryHandler
from models.task import save_proof

def build_tasks_message(user_id: int):
    return f"""📋 *Complete These to Unlock a Surprise Gift 🎁*

Help us grow and earn something special. Complete all 3 tasks below:

---

1️⃣ *Invite 3 New Users*
Bring in 3 friends who start the bot and set up at least 1 alert.

🔗 *Your referral link:*
https://t.me/{BOT_USERNAME}?start=ref{user_id}

➡️ /checkreferrals

---

2️⃣ *Post in a Large Crypto Group or Channel (5k+ members)*
Tell others about this bot in a big Telegram crypto group or channel. Share why you like it.

➡️ [Submit Proof](https://t.me/{BOT_USERNAME}?start=submitproof_task2)

---

3️⃣ *Post on Twitter or Reddit*
Make a post with a screenshot or short review about the bot on X or Reddit. Must mention at least 1 feature.

➡️ [Submit Proof](https://t.me/{BOT_USERNAME}?start=submitproof_task3)

---

✅ When you're done, the surprise reward will be unlocked for you 🎁
Keep going — you're almost there! 🚀
"""

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = build_tasks_message(user_id)
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)
    
    

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