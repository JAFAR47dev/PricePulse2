async def send_auto_delete(context, send_func_or_msg, *args, **kwargs):
    try:
        # If it's already a Message object (not a callable), use it directly
        if hasattr(send_func_or_msg, "chat") and hasattr(send_func_or_msg, "message_id"):
            message = send_func_or_msg
        else:
            # Otherwise, it's a coroutine function like context.bot.send_message
            message = await send_func_or_msg(*args, **kwargs)

        user_id = message.chat.id
        from models.user import get_user_auto_delete_minutes
        minutes = get_user_auto_delete_minutes(user_id)

        if minutes and minutes > 0:
            context.application.job_queue.run_once(
                lambda ctx: message.delete(),
                when=minutes * 60,
                name=f"autodel_{user_id}_{message.message_id}",
            )

    except Exception as e:
        print("Auto-delete error:", e)