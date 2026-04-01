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
from models.user import set_user_plan, get_user_plan


# Valid Pro plan types
VALID_PRO_PLANS = ["pro_monthly", "pro_yearly", "pro_lifetime"]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_progress_bar(current: int, total: int, length: int = 5) -> str:
    """Create a visual progress bar."""
    filled = min(int((current / total) * length), length)
    return "▓" * filled + "░" * (length - filled)


def format_check_mark(condition: bool) -> str:
    """Return checkmark or X based on condition"""
    return "✅" if condition else "❌"


def get_bot_username() -> str:
    """Get bot username"""
    return "EliteTradeSignalBot"


def calculate_new_expiry(user_id: int, bonus_days: int) -> str:
    """
    Calculate new expiry date based on current plan status.
    
    Returns:
        ISO format datetime string or "lifetime"
    """
    current_plan = get_user_plan(user_id)
    
    if current_plan == "pro_lifetime":
        return "lifetime"
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT plan_expiry_date
            FROM users
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        current_expiry_str = row[0] if row else None
        
        if current_plan in VALID_PRO_PLANS and current_expiry_str:
            try:
                if current_expiry_str.lower() == "lifetime":
                    return "lifetime"
                
                # Parse existing expiry (timezone-aware)
                if "+" in current_expiry_str or current_expiry_str.endswith("Z"):
                    current_expiry = datetime.fromisoformat(current_expiry_str.replace('Z', '+00:00'))
                else:
                    # Add UTC timezone if missing
                    current_expiry = datetime.fromisoformat(current_expiry_str).replace(tzinfo=timezone.utc)
                
                now = datetime.now(timezone.utc)
                
                # Extend from existing expiry if still valid, otherwise from now
                if current_expiry > now:
                    new_expiry = current_expiry + timedelta(days=bonus_days)
                else:
                    new_expiry = now + timedelta(days=bonus_days)
                
                return new_expiry.isoformat()
            
            except (ValueError, AttributeError) as e:
                print(f"⚠️ Error parsing expiry date for user {user_id}: {e}")
                # Fallback to now + bonus days
                pass
        
        # For free users or if parsing failed
        new_expiry = datetime.now(timezone.utc) + timedelta(days=bonus_days)
        return new_expiry.isoformat()
    
    finally:
        conn.close()


# ============================================================================
# MAIN TASKS MENU
# ============================================================================

async def tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the tasks and rewards menu."""
    user_id = update.effective_user.id
    
    await update_last_active(user_id, command_name="/tasks")
    
    try:
        init_task_progress(user_id)
        
        progress = get_task_progress(user_id)
        referral_count, claimed_tiers = get_referral_rewards(user_id)
        
        streak_days = progress.get("daily_streak", 0)
        streak_reward_claimed = progress.get("streak_reward_claimed", 0)
        
        bot_username = get_bot_username()
        referral_link = f"https://t.me/{bot_username}?start={user_id}"
        
        text = _build_tasks_menu_text(
            streak_days,
            streak_reward_claimed,
            referral_count,
            referral_link
        )
        
        keyboard = _build_tasks_menu_buttons(
            streak_days,
            streak_reward_claimed,
            referral_count,
            claimed_tiers
        )
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
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
        print(f"❌ Error in tasks_menu for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        
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
    
    # Streak section
    if streak_days >= 14 and streak_reward_claimed:
        streak_section = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "*🔥 DAILY STREAK CHALLENGE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 *Streak Mastery: {streak_days} days!*\n\n"
            "✅ 14-Day Challenge Completed!\n"
            "✅ Reward Claimed: 3 Days PRO\n\n"
            f"📊 Current Streak: *{streak_days} days*\n"
            "_Keep your streak alive! Daily usage keeps you sharp._\n\n"
        )
    elif streak_days >= 14 and not streak_reward_claimed:
        streak_section = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "*🔥 DAILY STREAK CHALLENGE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎉 *Challenge Complete!*\n\n"
            f"📅 Current Streak: *{streak_days}/14 days*\n"
            "🎁 Reward: *3 Days PRO Access* (Ready to claim!)\n"
            f"📊 Progress: `{create_progress_bar(14, 14, 10)}` 100%\n\n"
        )
    else:
        streak_section = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "*🔥 DAILY STREAK CHALLENGE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Use the bot daily for 14 consecutive days to earn 3 days Pro access\n\n"
            f"📅 Current Streak: *{streak_days}/14 days*\n"
            "⏳ Keep going!\n"
            f"📊 Progress: `{create_progress_bar(streak_days, 14, 10)}` {int(streak_days/14*100)}%\n\n"
        )
    
    return (
        "*🎁 REWARD CENTER*\n"
        "_Complete tasks and earn FREE Pro access!_\n\n"
        
        f"{streak_section}"
        
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
    
    return keyboard


# ============================================================================
# REWARD CLAIMING
# ============================================================================

async def claim_streak_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle streak reward claim"""
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
        
        # Debug logging
        print(f"[Streak Claim] User {user_id}: streak={daily_streak}, claimed={already_claimed}")
        
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
        
        # Calculate new expiry
        BONUS_DAYS = 3
        current_plan = get_user_plan(user_id)
        expiry_str = calculate_new_expiry(user_id, BONUS_DAYS)
        
        print(f"[Streak Claim] User {user_id}: current_plan={current_plan}, new_expiry={expiry_str}")
        
        # Update task_progress
        cursor.execute("""
            UPDATE task_progress
            SET streak_reward_claimed = 1,
                pro_expiry_date = ?
            WHERE user_id = ?
        """, (expiry_str, user_id))
        
        conn.commit()
        
        # Determine plan to set
        if current_plan == "pro_lifetime":
            plan_to_set = "pro_lifetime"
        elif current_plan in VALID_PRO_PLANS:
            plan_to_set = current_plan
        else:
            plan_to_set = "pro_monthly"
        
        set_user_plan(user_id, plan_to_set, expiry_str)
        
        print(f"✅ [Streak Claim] User {user_id}: Reward claimed successfully")
        
        # Format message
        if expiry_str == "lifetime":
            expiry_message = "Your *Lifetime Pro* status remains active! 🌟"
        else:
            expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
            expiry_formatted = expiry_date.strftime("%B %d, %Y at %H:%M UTC")
            
            if current_plan in VALID_PRO_PLANS:
                expiry_message = f"Your Pro access extended by *{BONUS_DAYS} days*!\n📅 New expiry: *{expiry_formatted}*"
            else:
                expiry_message = f"Your *{BONUS_DAYS}-day Pro access* activated!\n📅 Valid until: *{expiry_formatted}*"
        
        await query.edit_message_text(
            "🎉 *Congratulations!*\n\n"
            f"{expiry_message}\n\n"
            "✨ *Benefits unlocked:*\n"
            "• Unlimited AI interactions\n"
            "• Priority support\n"
            "• Advanced features\n"
            "• Ad-free experience\n\n"
            "Enjoy your Pro access! 🚀",
            parse_mode="Markdown"
        )
    
    except Exception as e:
        print(f"❌ Error claiming streak reward for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        
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
    """Handle referral tier reward claim"""
    query = update.callback_query
    await query.answer()
    
    # Extract tier
    try:
        tier = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Invalid reward tier.")
        return
    
    user_id = query.from_user.id
    conn = None
    
    try:
        # Validate tier
        if tier not in REFERRAL_TIERS:
            await query.edit_message_text("❌ Invalid referral tier.")
            return
        
        # Get referral progress
        referral_count, claimed_tiers = get_referral_rewards(user_id)
        
        # Debug logging
        print(f"[Referral Claim] User {user_id}, Tier {tier}: count={referral_count}, claimed={claimed_tiers}")
        
        # Check if already claimed
        if tier in claimed_tiers:
            await query.edit_message_text(
                f"ℹ️ *Already claimed!*\n\n"
                f"You've already claimed the tier {tier} reward.\n"
                f"Invite more friends to unlock higher tiers!",
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
        
        # Calculate expiry
        pro_days = REFERRAL_TIERS[tier]
        current_plan = get_user_plan(user_id)
        expiry_str = calculate_new_expiry(user_id, pro_days)
        
        print(f"[Referral Claim] User {user_id}, Tier {tier}: current_plan={current_plan}, new_expiry={expiry_str}")
        
        # Update database
        conn = get_connection()
        cursor = conn.cursor()
        
        claimed_tiers.append(tier)
        cursor.execute("""
            UPDATE task_progress
            SET referral_rewards_claimed = ?
            WHERE user_id = ?
        """, (",".join(map(str, claimed_tiers)), user_id))
        
        conn.commit()
        
        # Set plan
        if current_plan == "pro_lifetime":
            plan_to_set = "pro_lifetime"
        elif current_plan in VALID_PRO_PLANS:
            plan_to_set = current_plan
        else:
            plan_to_set = "pro_monthly"
        
        set_user_plan(user_id, plan_to_set, expiry_str)
        
        print(f"✅ [Referral Claim] User {user_id}, Tier {tier}: Reward claimed successfully")
        
        # Format message
        if expiry_str == "lifetime":
            expiry_message = "Your *Lifetime Pro* status remains active! 🌟"
        else:
            expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
            expiry_formatted = expiry_date.strftime("%B %d, %Y at %H:%M UTC")
            
            if current_plan in VALID_PRO_PLANS:
                expiry_message = f"Your Pro access extended by *{pro_days} days*!\n📅 New expiry: *{expiry_formatted}*"
            else:
                expiry_message = f"*{pro_days} days of Pro access* activated!\n📅 Valid until: *{expiry_formatted}*"
        
        await query.edit_message_text(
            f"🎉 *Tier {tier} Reward Claimed!*\n\n"
            f"{expiry_message}\n\n"
            "Thank you for sharing! Keep inviting friends for more rewards! 🚀",
            parse_mode="Markdown"
        )
    
    except Exception as e:
        print(f"❌ Error claiming referral reward for user {user_id}, tier {tier}: {e}")
        import traceback
        traceback.print_exc()
        
        await query.edit_message_text(
            "⚠️ *Error claiming reward*\n\n"
            "An error occurred. Please try again or contact support.",
            parse_mode="Markdown"
        )
    
    finally:
        if conn:
            conn.close()


async def refresh_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh button"""
    query = update.callback_query
    await query.answer("🔄 Refreshing...")
    await tasks_menu(update, context)


# ============================================================================
# DAILY STREAK HANDLER
# ============================================================================

async def handle_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle daily streak updates"""
    if not update.message:
        return
    
    user_id = update.effective_user.id
    message_text = update.message.text
    
    try:
        daily_streak, milestone_hit, reward_ready = update_daily_streak(
            user_id,
            message_text
        )
        
        if daily_streak is None:
            return
        
        if milestone_hit:
            await _send_milestone_message(update, milestone_hit)
        
        if reward_ready:
            await _send_reward_ready_message(update)
    
    except Exception as e:
        print(f"Error in handle_streak for user {user_id}: {e}")


async def _send_milestone_message(update: Update, milestone: int):
    """Send milestone message"""
    milestone_messages = {
        1: "🎉 *Great start!* You've begun your streak!",
        4: "🔥 *4-day streak!* You're building a habit!",
        7: "⭐ *1 week streak!* Halfway to Pro!",
        9: "💪 *9 days!* Almost there!",
        12: "🌟 *12 days!* Just 2 more!",
    }
    
    message = milestone_messages.get(
        milestone,
        f"🎉 *{milestone}-day streak!* Keep going!"
    )
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def _send_reward_ready_message(update: Update):
    """Send reward ready message"""
    keyboard = [[
        InlineKeyboardButton(
            "🎁 Claim 3-Day Pro Access",
            callback_data="claim_streak_reward"
        )
    ]]
    
    await update.message.reply_text(
        "🔥 *14-day streak complete!*\n\n"
        "Claim your *3 days of FREE Pro access* now:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
