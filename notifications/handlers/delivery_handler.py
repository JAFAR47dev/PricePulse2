from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, MessageHandler, ConversationHandler, filters, ContextTypes

from notifications.models import update_user_notification_setting

ASK_GROUP = 101 


async def refresh_notify_menu(update, context):
    """Return to main notify settings menu."""
    from notifications.handlers.notify_menu import notify_command
    return await notify_command(update, context)


async def delivery_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked Delivery Method → show private/group choices."""
    query = update.callback_query

    keyboard = [
        [InlineKeyboardButton("✅ Private Delivery", callback_data="notify_delivery_private")],
        [InlineKeyboardButton("📌 Group Delivery", callback_data="notify_delivery_group")],
        [InlineKeyboardButton("🔙 Back", callback_data="notify_delivery_back")]
    ]

    await query.edit_message_text(
        "📬 *Choose Delivery Method:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ConversationHandler.END


async def handle_delivery_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user selects private or group."""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # ✅ Handle Back
    if data == "notify_delivery_back":
        return await refresh_notify_menu(update, context)

    choice = data.split("_")[-1]  # private / group

    # ✅ PRIVATE
    if choice == "private":
        update_user_notification_setting(user_id, "delivery", "private")
        update_user_notification_setting(user_id, "group_id", None)

        await query.answer("✅ Delivery set to Private.")
        return await refresh_notify_menu(query, context)

    # ✅ GROUP
    if choice == "group":
        update_user_notification_setting(user_id, "delivery", "group")

        keyboard = [
            [InlineKeyboardButton("✅ I've forwarded the message", callback_data="notify_group_done")],
            [InlineKeyboardButton("🔙 Back", callback_data="notify_delivery_back")]
        ]

        await query.edit_message_text(
            "📌 *To link a group:*\n"
            "1. Open your group\n"
            "2. Forward **any message** from that group to this bot\n\n"
            "Tap below once you forwarded it 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return ASK_GROUP


async def catch_group_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Detect forwarded group message and safely store the group_id.
    Fully resilient to ANY message type or missing attributes.
    """
    msg = update.message

    # Safety check: message may not exist (e.g. callback updates)
    if not msg:
        return

    user_id = msg.from_user.id

    try:
        # Some forwarded messages DO NOT provide forward_from_chat.
        # Using getattr prevents AttributeError.
        fwd_chat = getattr(msg, "forward_from_chat", None)

        if not fwd_chat:
            # Not forwarded from a chat → ignore silently
            return

        # Check if forwarded chat is actually a group
        if getattr(fwd_chat, "type", None) not in ["group", "supergroup"]:
            return

        # Extract group ID safely
        group_id = getattr(fwd_chat, "id", None)
        if not group_id:
            print("[Delivery] forward_from_chat found but contains no ID.")
            return

        # Save link
        update_user_notification_setting(user_id, "group_id", group_id)

        await msg.reply_text(
            f"✅ Group linked successfully!\nSaved ID: `{group_id}`",
            parse_mode="Markdown"
        )

        return await refresh_notify_menu(msg, context)

    except Exception as e:
        print(f"[Delivery] Error in catch_group_forward: {e}")
        # Graceful fallback (doesn’t break user flow)
        try:
            await msg.reply_text(
                "⚠️ Something went wrong while reading the forwarded message.\n"
                "Please try forwarding a message from your group again.",
                parse_mode="Markdown",
            )
        except:
            pass

        return

async def confirm_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped confirmation but didn't forward"""
    query = update.callback_query
    await query.answer("Please forward a group message first 😊")
    return ASK_GROUP


def get_delivery_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(delivery_menu_handler, pattern="^notify_delivery_menu$"),
            CallbackQueryHandler(handle_delivery_choice, pattern="^notify_delivery_")
        ],
        states={
            ASK_GROUP: [
                MessageHandler(filters.FORWARDED & filters.ChatType.PRIVATE, catch_group_forward),
                CallbackQueryHandler(confirm_group_link, pattern="notify_group_done"),
                # ✅ Back button inside group linking
                CallbackQueryHandler(handle_delivery_choice, pattern="notify_delivery_back")
            ],
        },
        fallbacks=[],
        name="delivery_handler",
        persistent=False
    )