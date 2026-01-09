from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
from models.user import set_user_plan
from config import ADMIN_ID

VALID_PLANS = ["free", "pro_monthly", "pro_yearly", "pro_lifetime"]

async def set_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ Usage: /setplan <user_id> <free|pro_monthly|pro_yearly|pro_lifetime>")
        return

    try:
        target_user = int(args[0])
        plan = args[1].lower()
        if plan not in VALID_PLANS:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid plan. Try: `free`, `pro_monthly`, `pro_yearly`, or `pro_lifetime`", parse_mode="Markdown")
        return

    # Calculate expiry if needed
    expires_at = None
    if plan == "pro_monthly":
        expires_at = datetime.utcnow() + timedelta(days=30)
    elif plan == "pro_yearly":
        expires_at = datetime.utcnow() + timedelta(days=365)

    set_user_plan(target_user, plan, expires_at)

    expiry_str = f"\n🕒 Expires: {expires_at.strftime('%Y-%m-%d')}" if expires_at else ""
    await update.message.reply_text(
        f"✅ User {target_user} has been set to *{plan.upper()}* plan.{expiry_str}",
        parse_mode="Markdown"
    )
    
from telegram import Update
from telegram.ext import ContextTypes
from models.db import get_connection
import asyncio

PROLIST_TIMEOUT = 120  # seconds (2 minutes)

async def pro_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admins only.")
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, username, plan, expiry_date 
        FROM users
        WHERE plan LIKE 'pro%'
        ORDER BY expiry_date IS NULL DESC, expiry_date ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        response = await update.message.reply_text("📭 No Pro users found.")
        # Delete response message after timeout
        asyncio.create_task(delete_message_after_delay(context, update.message.chat_id, response.message_id, PROLIST_TIMEOUT))
        return

    monthly_count = yearly_count = lifetime_count = 0
    msg = "*📋 Current Pro Users:*\n\n"

    for uid, username, plan, expiry in rows:
        name = f"@{username}" if username else f"`{uid}`"
        plan_name = plan.replace("pro_", "").capitalize()
        expiry_display = expiry if expiry else "♾️ Lifetime"

        msg += f"• {name} — *{plan_name}* — {expiry_display}\n"

        if uid == ADMIN_ID:
            continue

        if "month" in plan.lower():
            monthly_count += 1
        elif "year" in plan.lower():
            yearly_count += 1
        elif "life" in plan.lower():
            lifetime_count += 1

    revenue = (
        f"\n\n💰 *Expected Revenue Summary (Auto-expires):*\n"
        f"🗓️ Monthly ({monthly_count}): ${monthly_count * 10}\n"
        f"📅 Yearly ({yearly_count}): ${yearly_count * 99}\n"
        f"♾️ Lifetime ({lifetime_count}): ${lifetime_count * 249}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 *Total:* ${(monthly_count*10)+(yearly_count*99)+(lifetime_count*249)}"
    )

    sent = await update.message.reply_text(msg + revenue, parse_mode="Markdown")
    
    # Delete the results after 2 minutes
    asyncio.create_task(delete_message_after_delay(context, update.message.chat_id, sent.message_id, PROLIST_TIMEOUT))
    
    
async def delete_message_after_delay(context, chat_id, message_id, delay=PROLIST_TIMEOUT):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id, message_id)
    except:
        pass