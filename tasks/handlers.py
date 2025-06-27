from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from tasks.models import get_task_progress, init_task_progress
from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from tasks.models import get_task_progress, init_task_progress

async def tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Ensure row exists
    init_task_progress(user_id)
    progress = get_task_progress(user_id)

    def status(val):
        return "✅" if val == 1 else "🕓 Submitted" if val == 2 else "❌"

    referral_link = f"https://t.me/EliteTradeSignalBot?start={user_id}"  # 🔁 Replace with actual username

    text = (
    "*🎯 Complete These 3 Tasks to Unlock 1 Month of Pro Access ($10 Value):*\n\n"

    f"1. {status(progress['task1_done'])} *Invite 3 New Users*\n"
    f"   ↳ Share your referral link:\n"
    f"`{referral_link}`\n"
    "   ✅ Submit *text*, *screenshot*, or *usernames* showing that 3 people joined and used the bot.\n\n"

    f"2. {status(progress['task2_done'])} *Promote the Bot on Social Media*\n"
    "   ↳ Post about the bot on Twitter/X, YouTube (community tab), or a Telegram group/channel.\n"
    "   ✅ Send a *screenshot*, *post link*, or a short *description* of what you posted.\n\n"

    f"3. {status(progress['task3_done'])} *Give Feedback or Testimonial*\n"
    "   ↳ Tell us how the bot has helped you or share a suggestion.\n"
    "   ✅ Send your feedback as *text*, *screenshot*, or *review message*.\n\n"

    "✅ *All 3 tasks must be completed and approved by an admin.*\n"
    "🎁 *Reward:* 30 Days of Full Pro Access!"
)
    
    keyboard = [
    [InlineKeyboardButton("📤 Submit Proof", callback_data="submit_proof")],
    [InlineKeyboardButton("🔄 Check Status", callback_data="check_status")]
]

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes
from tasks.models import get_task_progress

# Handle inline button actions
async def handle_task_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "submit_proof":
        await query.message.reply_text(
            "📤 *How to submit proof:*\n\n"
            "🔹 For links or text: Send like this — `1: your proof here`\n"
            "🔹 For screenshots or files: Just send with caption `1`, `2`, or `3`\n\n"
            "💡 Each number represents the task number.",
            parse_mode="Markdown"
        )
       
    elif query.data == "check_status":
        progress = get_task_progress(user_id)
        status = lambda done: "✅ Done" if done else "❌ Not Done"
        msg = (
            "*📊 Task Completion Status:*\n\n"
            f"1. Invite Friends: {status(progress['task1_done'])}\n"
            f"2. Share in Groups: {status(progress['task2_done'])}\n"
            f"3. Post on Social: {status(progress['task3_done'])}\n\n"
            "If you've submitted proof, please wait for admin review."
        )
        await query.message.reply_text(msg, parse_mode="Markdown")
        

from telegram import Update
from telegram.ext import MessageHandler, filters, ContextTypes
from tasks.models import save_proof

# Message handler for proof submission (text or photo)
async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    proof_saved = False

    # --- TEXT PROOF FORMAT ---
    if update.message.text:
        lines = update.message.text.strip().splitlines()
        for line in lines:
            if ":" in line:
                try:
                    task_num_str, proof = line.split(":", 1)
                    task_num = int(task_num_str.strip())
                    proof = proof.strip()
                    if task_num in [1, 2, 3] and proof:
                        save_proof(user_id, task_num, proof)
                        proof_saved = True
                except Exception as e:
                    continue
    
    # --- PHOTO PROOF FORMAT ---
    elif update.message.photo:
        try:
            caption = update.message.caption.strip() if update.message.caption else ""
            task_num = int(caption)
            if task_num in [1, 2, 3]:
                file_id = update.message.photo[-1].file_id
                save_proof(user_id, task_num, file_id)
                proof_saved = True
        except Exception as e:
            pass
            
    
    # --- DOCUMENT PROOF FORMAT ---
    elif update.message.document:
        try:
            caption = update.message.caption.strip() if update.message.caption else ""
            task_num = int(caption)
            if task_num in [1, 2, 3]:
                file_id = update.message.document.file_id
                save_proof(user_id, task_num, file_id)
                proof_saved = True
        except Exception as e:
            pass

    if proof_saved:
        await update.message.reply_text("✅ Your proof has been submitted. It will be reviewed soon.")
    else:
        await update.message.reply_text(
            "❌ Invalid proof format.\n\n"
            "• Use: `1: your proof` for text/link\n"
            "• Or upload a screenshot with caption: `1`, `2`, or `3`.",
            parse_mode="Markdown"
        )
       
        return ConversationHandler.END
        
from telegram import Update
from telegram.ext import ContextTypes
from models.db import get_connection


async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT task1_done, task2_done, task3_done, proof1, proof2, proof3, approved_by_admin, reward_given FROM task_progress WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("🔍 You haven't started the tasks yet. Use /tasks to get started!")
        return

    task1, task2, task3, proof1, proof2, proof3, approved, reward = row

    def status(val): return "✅" if val == 1 else "🕓 Submitted" if val == 2 else "❌"

    msg = f"""🧾 *Your Task Progress:*\n
• Task 1: {status(task1)} {f"- [{proof1}]" if proof1 else ""}
• Task 2: {status(task2)} {f"- [{proof2}]" if proof2 else ""}
• Task 3: {status(task3)} {f"- [{proof3}]" if proof3 else ""}

🛡️ Admin Approval: {"✅ Approved" if approved else "⏳ Pending"}
🎁 Reward: {"💎 Granted" if reward else "🔒 Locked"}
"""

    await update.message.reply_text(msg, parse_mode="Markdown")
 



