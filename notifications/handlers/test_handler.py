# notifications/handlers/test_handler.py
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from notifications.models import get_user_notification_settings
from notifications.services.notification_data import get_notification_data
from notifications.scheduler import send_notification_with_retry


async def test_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered when user taps 'Send Test Notification'.
    Sends a clean, well-formatted live preview of user notifications.
    """
    query = update.callback_query
    user_id = query.from_user.id

    # ✅ Answer callback IMMEDIATELY
    await query.answer("📤 Sending test notification...", show_alert=False)

    # --- Fetch user settings ---
    settings = get_user_notification_settings(user_id)

    # ✅ FIX: Ensure delivery defaults to "private" if group_id is None
    delivery = settings.get("delivery", "private")
    group_id = settings.get("group_id")
    
    # If delivery is "group" but no group_id exists, fallback to private
    if delivery == "group" and not group_id:
        print(f"[TestNotification] User {user_id} has delivery='group' but no group_id, using private instead")
        delivery = "private"
    
    user = {
        "user_id": user_id,
        "delivery": delivery,
        "group_id": group_id,
        **settings  # Include all other settings
    }

    # --- Fetch notification data (cached for speed) ---
    try:
        notif_data = await get_notification_data(ttl=60)
    except Exception as e:
        print(f"[TestNotification] Failed to fetch data: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Failed to fetch notification data. Please try again later."
        )
        return

    # ✅ Build message using scheduler's build_message function
    from notifications.scheduler import build_message
    
    try:
        message = await build_message(user, notif_data)
    except Exception as e:
        print(f"[TestNotification] Failed to build message: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Failed to format notification. Please try again."
        )
        return

    # --- Send the message using the user's preferred method ---
    try:
        success, error = await send_notification_with_retry(
            context.bot,
            user,
            message
        )
        
        if success:
            print(f"[TestNotification] Successfully sent to user {user_id}")
            # Optionally send confirmation to user
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Test notification sent successfully! Check your configured delivery location."
            )
        else:
            print(f"[TestNotification] Failed to send to user {user_id}: {error}")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ Failed to send test notification.\n\n*Reason:* {error}\n\nPlease check your notification settings with /notifications",
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"[TestNotification] Exception sending to user {user_id}: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ An error occurred. Please try again later."
        )