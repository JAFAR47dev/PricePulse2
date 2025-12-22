import os
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from notifications.scheduler import send_emergency_broadcast

# Get your Telegram user ID from environment variable
OWNER_ID = int(os.getenv("ADMIN_ID", "0"))


def is_owner(user_id: int) -> bool:
    """Check if user is the bot owner"""
    return user_id == OWNER_ID


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast command - owner only"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ This command is only available to the bot owner.")
        return
    
    # Set broadcast mode in user_data
    context.user_data["broadcast_mode"] = True
    
    await update.message.reply_text(
        "📢 *Emergency Broadcast*\n\n"
        "Send me the message you want to broadcast to all users.\n\n"
        "You can use:\n"
        "• Plain text\n"
        "• *Bold* with asterisks\n"
        "• _Italic_ with underscores\n"
        "• `Code` with backticks\n"
        "• [Links](https://example.com)\n\n"
        "Send /cancel to abort.",
        parse_mode="Markdown"
    )


async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the broadcast message - called from global router"""
    message = update.message.text
    
    # Clear broadcast mode
    context.user_data.pop("broadcast_mode", None)
    
    await update.message.reply_text(
        "📤 *Broadcasting message...*\n\n"
        "This may take a few minutes depending on the number of users.",
        parse_mode="Markdown"
    )
    
    # Send the broadcast
    stats = await send_emergency_broadcast(
        context.application,
        message,
        all_users=True
    )
    
    # Report results
    if "error" in stats:
        await update.message.reply_text(
            f"❌ *Broadcast Failed*\n\n"
            f"Error: {stats['error']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"✅ *Broadcast Complete!*\n\n"
            f"📊 *Statistics:*\n"
            f"• ✅ Sent: {stats['sent']}\n"
            f"• ❌ Failed: {stats['failed']}\n"
            f"• 🚫 Blocked: {stats['blocked']}\n\n"
            f"Total users: {stats['sent'] + stats['failed'] + stats['blocked']}",
            parse_mode="Markdown"
        )


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the broadcast"""
    # Clear broadcast mode
    context.user_data.pop("broadcast_mode", None)
    await update.message.reply_text("❌ Broadcast cancelled.")


async def broadcast_specific(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast to specific users - /broadcast_to user_id1 user_id2 ..."""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ This command is only available to the bot owner.")
        return
    
    # Parse command: /broadcast_to 123456 789012 Your message here
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "❌ *Usage:*\n"
            "`/broadcast_to USER_ID1 USER_ID2 ... Your message`\n\n"
            "*Example:*\n"
            "`/broadcast_to 123456789 987654321 Hello users!`",
            parse_mode="Markdown"
        )
        return
    
    # Extract user IDs (numbers at the start)
    user_ids = []
    message_parts = []
    
    for arg in args:
        if arg.isdigit() and not message_parts:
            user_ids.append(int(arg))
        else:
            message_parts.append(arg)
    
    if not user_ids or not message_parts:
        await update.message.reply_text(
            "❌ Please provide both user IDs and a message."
        )
        return
    
    message = " ".join(message_parts)
    
    await update.message.reply_text(
        f"📤 Broadcasting to {len(user_ids)} specific users..."
    )
    
    # Send the broadcast
    stats = await send_emergency_broadcast(
        context.application,
        message,
        all_users=False,
        user_ids=user_ids
    )
    
    # Report results
    await update.message.reply_text(
        f"✅ *Targeted Broadcast Complete!*\n\n"
        f"📊 *Statistics:*\n"
        f"• ✅ Sent: {stats['sent']}\n"
        f"• ❌ Failed: {stats['failed']}\n"
        f"• 🚫 Blocked: {stats['blocked']}",
        parse_mode="Markdown"
    )


async def broadcast_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Preview what a broadcast will look like"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ This command is only available to the bot owner.")
        return
    
    # Get message from command args
    if not context.args:
        await update.message.reply_text(
            "❌ *Usage:*\n"
            "`/broadcast_preview Your message here`",
            parse_mode="Markdown"
        )
        return
    
    message = " ".join(context.args)
    
    await update.message.reply_text(
        "👀 *Broadcast Preview*\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"{message}\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "This is how users will see your message.",
        parse_mode="Markdown"
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin statistics"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ This command is only available to the bot owner.")
        return
    
    from notifications.models import get_all_active_users
    from notifications.scheduler import get_scheduler_status
    
    # Get user stats
    all_users = get_all_active_users()
    active_count = len([u for u in all_users if u.get("frequency") != "off"])
    
    # Get scheduler status
    scheduler_status = get_scheduler_status()
    
    await update.message.reply_text(
        "📊 *Bot Admin Dashboard*\n\n"
        f"👥 *Users:*\n"
        f"• Total: {len(all_users)}\n"
        f"• Active notifications: {active_count}\n"
        f"• Inactive: {len(all_users) - active_count}\n\n"
        f"⚙️ *Scheduler:*\n"
        f"• Status: {scheduler_status['status']}\n"
        f"• Next run: {scheduler_status['jobs'][0]['next_run'] if scheduler_status['jobs'] else 'N/A'}\n\n"
        f"📡 *Commands:*\n"
        f"• `/broadcast` - Send to all users\n"
        f"• `/broadcast_to` - Send to specific users\n"
        f"• `/broadcast_preview` - Preview message\n"
        f"• `/admin` - Show this dashboard",
        parse_mode="Markdown"
    )


def register_broadcast_handlers(app):
    """Register broadcast command handlers (not the message handler)"""
    app.add_handler(CommandHandler("broadcast", broadcast_start))
    app.add_handler(CommandHandler("broadcast_to", broadcast_specific))
    app.add_handler(CommandHandler("broadcast_preview", broadcast_preview))
    app.add_handler(CommandHandler("cancel", broadcast_cancel))
    app.add_handler(CommandHandler("admin", admin_stats))
    