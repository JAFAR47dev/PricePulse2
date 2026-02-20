from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, ContextTypes

from notifications.models import update_user_notification_setting

ASK_GROUP = 101


async def refresh_notify_menu(update, context):
    """Return to main notify settings menu."""
    from notifications.handlers.notify_menu import notify_command
    return await notify_command(update, context)


async def delivery_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show delivery method options."""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("✅ Private Delivery", callback_data="notify_delivery_private")],
        [InlineKeyboardButton("📌 Group/Channel Delivery", callback_data="notify_delivery_group")],
        [InlineKeyboardButton("🔙 Back", callback_data="notify_delivery_back")]
    ]

    await query.edit_message_text(
        "📬 *Choose Delivery Method:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ConversationHandler.END


async def handle_delivery_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle private/group delivery selection."""
    query = update.callback_query
    user_id = query.from_user.id
    choice = query.data.split("_")[-1]

    if choice == "back":
        # Clear the flow state
        context.user_data.pop("awaiting_group_forward", None)
        return await refresh_notify_menu(update, context)

    if choice == "private":
        update_user_notification_setting(user_id, "delivery", "private")
        update_user_notification_setting(user_id, "group_id", None)
        await query.answer("✅ Delivery set to Private.")
        return await refresh_notify_menu(query, context)

    if choice == "group":
    	update_user_notification_setting(user_id, "delivery", "group")
    
    	# Set flag for global router
    	context.user_data["awaiting_group_forward"] = True
    
    	keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data="notify_delivery_back")]]
    
    	await query.edit_message_text(
       	 "📌 *To link a group or channel:*\n\n"
      	  "1. Go to your group/channel\n"
        	"2. Find any message from **another member**\n"
        	"   (or system messages like 'User joined')\n"
       	 "3. Forward that message to me\n\n"
       	 "✅ Supports: Public/Private Groups, Public/Private Channels\n\n"
       	 "💡 **Important:** Don't forward your own messages - "
        	"they won't contain group info!",
        	parse_mode="Markdown",
        	reply_markup=InlineKeyboardMarkup(keyboard)
  	  )
    
    	return ConversationHandler.END
    
async def catch_group_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle forwarded message from group/channel (called from global router).
    Supports: groups, supergroups, channels (public and private).
    Returns True if handled, False otherwise.
    """
    try:
        msg = update.message
        user_id = msg.from_user.id
        
        print(f"[catch_group_forward] Processing message from user {user_id}")
        
        # Method 1: Check forward_origin (preferred for channels and groups)
        if hasattr(msg, 'forward_origin') and msg.forward_origin:
            forward_origin = msg.forward_origin
            print(f"[catch_group_forward] Forward origin type: {forward_origin.type}")
            
            chat_id = None
            chat_title = "Unknown"
            chat_type_display = "Chat"
            type_icon = "💬"
            
            # Handle different forward origin types
            if forward_origin.type == "channel":
                print("[catch_group_forward] Processing channel forward")
                chat_id = forward_origin.chat.id
                chat_title = forward_origin.chat.title or "Unknown Channel"
                chat_type_display = "Channel"
                type_icon = "📢"
                
            elif forward_origin.type == "chat":
                print("[catch_group_forward] Processing chat forward")
                chat_id = forward_origin.sender_chat.id
                chat_title = forward_origin.sender_chat.title or "Unknown Group"
                
                if hasattr(forward_origin.sender_chat, 'type'):
                    if forward_origin.sender_chat.type == "supergroup":
                        chat_type_display = "Supergroup"
                        type_icon = "👥"
                    else:
                        chat_type_display = "Group"
                        type_icon = "👥"
                else:
                    chat_type_display = "Group"
                    type_icon = "👥"
            
            elif forward_origin.type == "hidden_user":
                print("[catch_group_forward] Hidden user forward detected")
                await msg.reply_text(
                    "⚠️ Cannot link this chat due to privacy settings.\n\n"
                    "Please forward a message from a group or channel where you're an admin."
                )
                return True
            
            # If we got a valid chat_id, save it
            if chat_id:
                print(f"[catch_group_forward] Extracted chat_id: {chat_id}")
                
                update_user_notification_setting(user_id, "group_id", chat_id)
                context.user_data.pop("awaiting_group_forward", None)
                
                # Get username if available
                chat_username = "Private"
                if forward_origin.type == "channel" and hasattr(forward_origin.chat, 'username') and forward_origin.chat.username:
                    chat_username = f"@{forward_origin.chat.username}"
                elif forward_origin.type == "chat" and hasattr(forward_origin.sender_chat, 'username') and forward_origin.sender_chat.username:
                    chat_username = f"@{forward_origin.sender_chat.username}"
                
                await msg.reply_text(
                    f"✅ **{chat_type_display} linked successfully!**\n\n"
                    f"{type_icon} **Name:** {chat_title}\n"
                    f"🔗 **Username:** {chat_username}\n"
                    f"🆔 **ID:** `{chat_id}`",
                    parse_mode="Markdown"
                )
                
                await refresh_notify_menu(msg, context)
                return True
        
        # Method 2: Check if forwarded from chat (legacy fallback)
        if hasattr(msg, 'forward_from_chat') and msg.forward_from_chat:
            chat = msg.forward_from_chat
            print(f"[catch_group_forward] Using forward_from_chat: {chat.type}")
            
            if chat.type in ["group", "supergroup", "channel"]:
                chat_id = chat.id
                chat_title = chat.title or "Unknown"
                
                update_user_notification_setting(user_id, "group_id", chat_id)
                context.user_data.pop("awaiting_group_forward", None)
                
                type_name = "Channel" if chat.type == "channel" else "Group"
                type_icon = "📢" if chat.type == "channel" else "👥"
                
                await msg.reply_text(
                    f"✅ **{type_name} linked successfully!**\n\n"
                    f"{type_icon} **Name:** {chat_title}\n"
                    f"🆔 **ID:** `{chat_id}`",
                    parse_mode="Markdown"
                )
                
                await refresh_notify_menu(msg, context)
                return True
        
        # If we reach here, it's not a valid group/channel forward
        print("[catch_group_forward] No valid forward detected")
        await msg.reply_text(
            "⚠️ **Unable to detect group/channel.**\n\n"
            "📝 **Please follow these steps:**\n"
            "1. Go to your group\n"
            "2. Find a message from **another member** or **system message** (like 'User joined')\n"
            "3. Forward that message to me\n\n"
            "💡 **Why?** Messages you write yourself are forwarded as 'from you', not 'from the group'."
        )
        return True
        
    except Exception as e:
        print(f"[catch_group_forward] ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            await update.message.reply_text(
                "⚠️ An error occurred while processing your forward.\n"
                "Please try again or contact support."
            )
        except:
            pass
        
        context.user_data.pop("awaiting_group_forward", None)
        return True
        
def get_delivery_handler():
    """Only handles callback queries, not text messages."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(delivery_menu_handler, pattern="^notify_delivery_menu$"),
            CallbackQueryHandler(handle_delivery_choice, pattern="^notify_delivery_")
        ],
        states={},  # No states needed - global router handles text
        fallbacks=[],
        name="delivery_handler",
        persistent=False
    )
