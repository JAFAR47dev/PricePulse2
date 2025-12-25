"""
Tasks and Rewards System Handlers

This module handles:
- Daily streak tracking and rewards
- Referral system and rewards
- Task progress display
- Reward claiming
"""

from datetime import datetime, timedelta, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# Local imports
from tasks.models import (
    get_task_progress,
    init_task_progress,
    update_daily_streak,
    get_referral_rewards,
    REFERRAL_TIERS,
)
from models.user_activity import update_last_active
from models.db import get_connection
from models.user import set_user_plan


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_progress_bar(current: int, total: int, length: int = 5) -> str:
    """
    Create a visual progress bar.
    
    Args:
        current: Current progress value
        total: Total/maximum value
        length: Length of the bar in characters
    
    Returns:
        String representation of progress bar
    """
    filled = min(int((current / total) * length), length)
    return "▓" * filled + "░" * (length - filled)


def format_check_mark(condition: bool) -> str:
    """Return checkmark or X based on condition"""
    return "✅" if condition else "❌"


def get_bot_username() -> str:
    """Get bot username (configure this in your config)"""
    # TODO: Load from environment or config
    return "EliteTradeSignalBot"


# ============================================================================
# MAIN TASKS MENU
# ============================================================================

async def tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Display the tasks and rewards menu.
    Shows current progress, available rewards, and claim buttons.
    """
    user_id = update.effective_user.id
    
    # Track user activity
    await update_last_active(user_id, command_name="/tasks")
    
    try:
        # Initialize user's task progress if doesn't exist
        init_task_progress(user_id)
        
        # Fetch current progress
        progress = get_task_progress(user_id)
        referral_count, claimed_tiers = get_referral_rewards(user_id)
        
        # Extract progress data
        streak_days = progress.get("daily_streak", 0)
        streak_reward_claimed = progress.get("streak_reward_claimed", 0)
        
        # Generate referral link
        bot_username = get_bot_username()
        referral_link = f"https://t.me/{bot_username}?start={user_id}"
        
        # Build menu text
        text = _build_tasks_menu_text(
            streak_days,
            streak_reward_claimed,
            referral_count,
            referral_link
        )
        
        # Build action buttons
        keyboard = _build_tasks_menu_buttons(
            streak_days,
            streak_reward_claimed,
            referral_count,
            claimed_tiers
        )
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Send or edit message
        if update.message:
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
    
    except Exception as e:
        error_msg = "⚠️ Unable to load tasks menu. Please try again later."
        print(f"Error in tasks_menu for user {user_id}: {e}")
        
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.answer(error_msg, show_alert=True)


def _build_tasks_menu_text(
    streak_days: int,
    streak_reward_claimed: int,
    referral_count: int,
    referral_link: str
) -> str:
    """Build the formatted text for tasks menu"""
    
    return (
        "*🎁 REWARD CENTER*\n"
        "_Complete tasks and earn FREE Pro access!_\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*🔥 DAILY STREAK CHALLENGE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Use the bot daily for 14 consecutive days\n\n"
        f"📅 Current Streak: *{streak_days}/14 days*\n"
        f"{'🎁 Reward: *3 Days PRO Access*' if streak_days >= 14 else '⏳ Keep going!'}\n"
        f"🎯 Status: {format_check_mark(streak_reward_claimed)}\n"
        f"📊 Progress: `{create_progress_bar(streak_days, 14, 10)}` {int(streak_days/14*100)}%\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*👥 REFERRAL REWARDS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Invite friends & unlock Pro access:\n"
        "• *1 Invite* → 1 Day PRO\n"
        "• *3 Invites* → 7 Days PRO\n"
        "• *5 Invites* → 14 Days PRO\n\n"
        f"👥 Total Invites: *{referral_count}*\n"
        f"📊 Progress: `{create_progress_bar(referral_count, 5)}` {referral_count}/5\n\n"
        f"🔗 *Your Referral Link:*\n`{referral_link}`\n\n"
        
        "_💡 Tip: Share your link to start earning rewards!_"
    )


def _build_tasks_menu_buttons(
    streak_days: int,
    streak_reward_claimed: int,
    referral_count: int,
    claimed_tiers: list
) -> list:
    """Build interactive buttons for tasks menu"""
    
    keyboard = []
    
    # Daily streak reward button
    if streak_days >= 14 and not streak_reward_claimed:
        keyboard.append([
            InlineKeyboardButton(
                "🎁 Claim Daily Streak Reward (3 Days PRO)",
                callback_data="claim_streak_reward"
            )
        ])
    
    # Referral tier reward buttons
    for tier, days in sorted(REFERRAL_TIERS.items()):
        if referral_count >= tier and tier not in claimed_tiers:
            keyboard.append([
                InlineKeyboardButton(
                    f"🎁 Claim {days}-Day PRO ({tier} Referral{'s' if tier > 1 else ''})",
                    callback_data=f"claim_referral_tier:{tier}"
                )
            ])
    
    # Refresh button
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh_tasks_menu")
    ])
    
    return keyboard


# ============================================================================
# DAILY STREAK HANDLER
# ============================================================================

async def handle_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle daily streak updates and notifications.
    
    Called on each qualifying user interaction to update streak count
    and send milestone/reward notifications.
    """
    if not update.message:
        return  # Only process actual messages
    
    user_id = update.effective_user.id
    message_text = update.message.text
    
    try:
        # Update the daily streak
        daily_streak, milestone_hit, reward_ready = update_daily_streak(
            user_id,
            message_text
        )
        
        # If None returned, message didn't count for streak
        if daily_streak is None:
            return
        
        # Send milestone congratulations
        if milestone_hit:
            await _send_milestone_message(update, milestone_hit)
        
        # Send reward claim prompt when 14-day streak is achieved
        if reward_ready:
            await _send_reward_ready_message(update)
    
    except Exception as e:
        print(f"Error in handle_streak for user {user_id}: {e}")
        # Don't notify user of streak errors to avoid confusion


async def _send_milestone_message(update: Update, milestone: int):
    """Send congratulatory message for streak milestones"""
    
    milestone_messages = {
        1: (
            "🎉 *Great start!*\n\n"
            "You've begun your streak journey!\n"
            "Come back tomorrow to keep it going."
        ),
        4: (
            "🔥 *4-day streak!*\n\n"
            "You're building a habit!\n"
            "Keep it up to reach 7 days."
        ),
        7: (
            "⭐ *Amazing! 1 week streak!*\n\n"
            "You're halfway to unlocking your FREE 3-day Pro access.\n"
            "Don't break the chain now!"
        ),
        9: (
            "💪 *9-day streak! You're on fire!*\n\n"
            "Just 5 more days until your reward.\n"
            "Keep up the momentum!"
        ),
        12: (
            "🌟 *12-day streak! Almost there!*\n\n"
            "Only 2 more days until you unlock FREE Pro access.\n"
            "The finish line is in sight!"
        )
    }
    
    message = milestone_messages.get(
        milestone,
        f"🎉 Congrats! You reached a *{milestone}-day streak!*\n\n"
        f"Keep going to reach 14 days and claim your FREE 3-day Pro access."
    )
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def _send_reward_ready_message(update: Update):
    """Send message when 14-day streak reward is ready"""
    
    keyboard = [[
        InlineKeyboardButton(
            "🎁 Claim 3-Day Pro Access",
            callback_data="claim_streak_reward"
        )
    ]]
    
    await update.message.reply_text(
        "🔥 *Incredible! You completed a 14-day streak!*\n\n"
        "You've earned *3 days of FREE Pro access* with:\n"
        "✨ Unlimited AI interactions\n"
        "🚀 Priority support\n"
        "🎯 Advanced features\n\n"
        "Click below to claim your reward:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ============================================================================
# REWARD CLAIMING
# ============================================================================

async def claim_streak_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle streak reward claim callback.
    Grants 3-day Pro access to user who completed 14-day streak.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    conn = None
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check eligibility
        cursor.execute("""
            SELECT daily_streak, streak_reward_claimed
            FROM task_progress
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        
        if not row:
            await query.edit_message_text(
                "❌ *Error:* No streak data found.\n"
                "Please use the bot to start your streak!",
                parse_mode="Markdown"
            )
            return
        
        daily_streak, already_claimed = row
        
        # Validate eligibility
        if daily_streak < 14:
            await query.edit_message_text(
                f"❌ *Streak incomplete!*\n\n"
                f"Current streak: *{daily_streak}/14 days*\n"
                f"Keep using the bot daily to reach 14 days!",
                parse_mode="Markdown"
            )
            return
        
        if already_claimed:
            await query.edit_message_text(
                "ℹ️ *Already claimed!*\n\n"
                "You've already claimed this reward.\n"
                "Keep your streak going for future rewards!",
                parse_mode="Markdown"
            )
            return
        
        # Calculate Pro expiry (3 days from now)
        expiry_date = datetime.now(timezone.utc) + timedelta(days=3)
        expiry_str = expiry_date.isoformat()
        
        # Update task_progress table
        cursor.execute("""
            UPDATE task_progress
            SET streak_reward_claimed = 1,
                pro_expiry_date = ?
            WHERE user_id = ?
        """, (expiry_str, user_id))
        
        conn.commit()
        
        # Upgrade user's plan in main users table
        set_user_plan(user_id, "pro", expiry_str)
        
        # Format success message
        expiry_formatted = expiry_date.strftime("%B %d, %Y at %H:%M UTC")
        
        await query.edit_message_text(
            "🎉 *Congratulations!*\n\n"
            "Your *3-day Pro access* has been activated!\n\n"
            "✨ *Benefits unlocked:*\n"
            "• Unlimited AI interactions\n"
            "• Priority support\n"
            "• Advanced features\n"
            "• Ad-free experience\n\n"
            f"📅 Valid until: *{expiry_formatted}*\n\n"
            "Enjoy your Pro access! 🚀",
            parse_mode="Markdown"
        )
    
    except Exception as e:
        print(f"Error claiming streak reward for user {user_id}: {e}")
        await query.edit_message_text(
            "⚠️ *Error claiming reward*\n\n"
            "An error occurred while processing your reward.\n"
            "Please try again or contact support.",
            parse_mode="Markdown"
        )
    
    finally:
        if conn:
            conn.close()


async def claim_referral_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle referral tier reward claim callback.
    Grants Pro access based on referral tier achieved.
    """
    query = update.callback_query
    await query.answer()
    
    # Extract tier from callback data (format: "claim_referral_tier:1")
    try:
        tier = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Invalid reward tier.")
        return
    
    user_id = query.from_user.id
    conn = None
    
    try:
        # Validate tier exists
        if tier not in REFERRAL_TIERS:
            await query.edit_message_text("❌ Invalid referral tier.")
            return
        
        # Get referral progress
        referral_count, claimed_tiers = get_referral_rewards(user_id)
        
        # Check if already claimed
        if tier in claimed_tiers:
            await query.edit_message_text(
                f"ℹ️ You've already claimed the tier {tier} reward!",
                parse_mode="Markdown"
            )
            return
        
        # Check if eligible
        if referral_count < tier:
            await query.edit_message_text(
                f"❌ *Insufficient referrals!*\n\n"
                f"You need *{tier} referral{'s' if tier > 1 else ''}* to claim this reward.\n"
                f"Current: *{referral_count}*",
                parse_mode="Markdown"
            )
            return
        
        # Calculate Pro days for this tier
        pro_days = REFERRAL_TIERS[tier]
        expiry_date = datetime.now(timezone.utc) + timedelta(days=pro_days)
        expiry_str = expiry_date.isoformat()
        
        # Update database
        conn = get_connection()
        cursor = conn.cursor()
        
        # Mark tier as claimed
        claimed_tiers.append(tier)
        cursor.execute("""
            UPDATE task_progress
            SET referral_rewards_claimed = ?
            WHERE user_id = ?
        """, (",".join(map(str, claimed_tiers)), user_id))
        
        conn.commit()
        
        # Grant Pro access
        set_user_plan(user_id, "pro", expiry_str)
        
        # Success message
        expiry_formatted = expiry_date.strftime("%B %d, %Y at %H:%M UTC")
        
        await query.edit_message_text(
            f"🎉 *Tier {tier} Reward Claimed!*\n\n"
            f"You've unlocked *{pro_days} days of Pro access!*\n\n"
            f"📅 Valid until: *{expiry_formatted}*\n\n"
            "Thank you for sharing! Keep inviting friends for more rewards! 🚀",
            parse_mode="Markdown"
        )
    
    except Exception as e:
        print(f"Error claiming referral reward for user {user_id}, tier {tier}: {e}")
        await query.edit_message_text(
            "⚠️ *Error claiming reward*\n\n"
            "Please try again or contact support.",
            parse_mode="Markdown"
        )
    
    finally:
        if conn:
            conn.close()


async def refresh_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh button callback to reload tasks menu"""
    query = update.callback_query
    await query.answer("🔄 Refreshing...")
    await tasks_menu(update, context)