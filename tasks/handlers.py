from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from tasks.models import get_task_progress, init_task_progress
from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from tasks.models import (
    get_task_progress,
    init_task_progress,
    update_daily_streak
    )

async def tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Ensure DB row exists
    init_task_progress(user_id)
    progress = get_task_progress(user_id)

    from tasks.models import get_referral_rewards

    referral_count, claimed_tiers = get_referral_rewards(user_id)

    referral_link = f"https://t.me/EliteTradeSignalBot?start={user_id}"

    streak_days = progress.get("daily_streak", 0)
    streak_reward_claimed = progress.get("streak_reward_claimed", 0)

    def check(x): return "✅" if x else "❌"

    # PROGRESS BAR for referrals
    def referral_bar(count):
        filled = min(count, 5)  # max 5/5
        return "▓" * filled + "░" * (5 - filled)

    # --------------------------
    # GUI TEXT
    # --------------------------
    text = (
        "*🔥 YOUR REWARD CENTER — Complete Tasks, Earn Free PRO Access!*\n\n"

        "==============================\n"
        "🕒 *DAILY STREAK CHALLENGE*\n"
        "==============================\n"
        "Use the bot every day for *14 days* to unlock:\n"
        "🎁 *3 Days FREE PRO Access*\n\n"
        f"📅 Current Streak: *{streak_days}/14*\n"
        f"🎯 Reward Claimed: {check(streak_reward_claimed)}\n\n"

        "==============================\n"
        "👥 *REFERRAL REWARDS*\n"
        "==============================\n"
        "Invite friends & earn PRO days automatically:\n"
        "• 1 Invite → *1 Day PRO*\n"
        "• 3 Invites → *7 Days PRO*\n"
        "• 5 Invites → *14 Days PRO*\n\n"
        f"🔗 Your Link:\n`{referral_link}`\n\n"
        f"👥 Total Invites: *{referral_count}*\n"
        f"📊 Progress: `{referral_bar(referral_count)}` (max 5)\n\n"

        )
    # --------------------------
    # BUTTONS
    # --------------------------
    keyboard = []

    # DAILY STREAK reward button
    if streak_days >= 14 and not streak_reward_claimed:
        keyboard.append([InlineKeyboardButton("🎁 Claim Daily Streak Reward", callback_data="claim_streak_reward")])

    # REFERRAL REWARD BUTTONS
    from tasks.models import REFERRAL_TIERS

    for tier, days in REFERRAL_TIERS.items():
        if referral_count >= tier and tier not in claimed_tiers:
            keyboard.append([
                InlineKeyboardButton(f"🎁 Claim {days}-Day PRO (Tier {tier})", callback_data=f"claim_referral_tier:{tier}")
            ])

    # Refresh button
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="check_status")])

    # --------------------------
    # SEND MESSAGE
    # --------------------------
    if update.message:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
        
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def handle_streak(update, context):
    user_id = update.effective_user.id
    message_text = update.message.text if update.message else None

    streak, milestone, reward_ready = update_daily_streak(user_id, message_text)

    if streak is None:
        return  # no change today

    # Milestone messages
    if milestone:
        await update.message.reply_text(
            f"🎉 Congrats! You reached a {milestone}-day streak!\n"
            f"Keep going to reach 14 days and claim your FREE 3-day Pro access."
        )

    # Reward claim
    if reward_ready:
        keyboard = [
            [InlineKeyboardButton("🎁 Claim 3-Day Pro Access", callback_data="claim_streak_reward")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔥 Amazing! You completed a 14-day streak!\nClick below to claim your 3-day FREE Pro access.",
            reply_markup=reply_markup
        )
        
from datetime import datetime, timedelta
from models.db import get_connection
from models.user import set_user_plan

async def claim_streak_reward(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    conn = get_connection()
    cursor = conn.cursor()

    # Check if already claimed
    cursor.execute("""
        SELECT streak_reward_claimed FROM task_progress WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    if not row or row[0] == 1:
        await query.edit_message_text("❌ Reward already claimed or streak incomplete.")
        conn.close()
        return

    # Calculate expiry for 3-day Pro access
    expiry_date = datetime.utcnow() + timedelta(days=3)
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")

    # Update task_progress table
    cursor.execute("""
        UPDATE task_progress
        SET streak_reward_claimed = 1, pro_expiry_date = ?
        WHERE user_id = ?
    """, (expiry_str, user_id))
    conn.commit()
    conn.close()

    # Upgrade user in main users table
    set_user_plan(user_id, "pro", expiry_str)

    # Send confirmation to user
    await query.edit_message_text(
        f"🎉 You claimed your 3-day Pro access!\n"
        f"Valid until: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )