from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from models.db import get_connection
from datetime import datetime


async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Fetch from DB
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT plan, expiry_date 
        FROM users 
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    # Default: if user is not found in DB treat as free
    if not row:
        plan = "free"
        expiry = None
    else:
        plan, expiry = row

    # Normalize
    plan = plan.lower() if plan else "free"

    # --- FREE PLAN ---
    if plan == "free":
        keyboard = [
            [InlineKeyboardButton("🚀 Upgrade to Pro", callback_data="upgrade_menuu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🆓 *Your Current Plan:* Free\n\n"
            "You are using the basic version of PricePulseBot.\n\n"
            "🔥 Unlock Pro to enjoy advanced alerts, watchlist, portfolio automation, "
            "multi-coin scanners, whale tracker, and more!",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    # --- PRO LIFETIME ---
    if plan == "pro_lifetime":
        await update.message.reply_text(
            "♾️ *Your Current Plan:* PRO LIFETIME\n\n"
            "You're fully upgraded forever — your plan never expires.\n"
            "Thank you for supporting PricePulseBot! 🚀",
            parse_mode="Markdown"
        )
        return

    # --- PRO MONTHLY / PRO YEARLY ---
    if plan in ["pro_monthly", "pro_yearly"]:
        days_left_str = "Unknown"

        if expiry:
            try:
                # Convert string timestamp → datetime object
                if isinstance(expiry, str):
                    expiry = datetime.fromisoformat(expiry)

                if isinstance(expiry, datetime):
                    now = datetime.utcnow()
                    delta = expiry - now
                    days_left = max(delta.days, 0)  # Avoid negative days
                    days_left_str = f"{days_left} day{'s' if days_left != 1 else ''} left"
            except Exception as e:
                print("⚠️ Error parsing expiry date:", e)

            expiry_str = expiry.strftime("%Y-%m-%d") if isinstance(expiry, datetime) else expiry
        else:
            expiry_str = "Unknown"

        plan_name = "Pro Monthly" if plan == "pro_monthly" else "Pro Yearly"

        await update.message.reply_text(
            f"⭐ *Your Current Plan:* {plan_name}\n\n"
            f"🕒 *Expires on:* `{expiry_str}` ({days_left_str})\n\n"
            "Thank you for being a Pro user! 🚀",
            parse_mode="Markdown"
        )
        return

    # Fallback (should not happen)
    await update.message.reply_text("⚠️ Could not determine your plan. Contact support.")