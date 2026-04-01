# notifications/handler.py
#
# Telegram handler for the /notifications command and all its callbacks.
#
# Register in your main.py:
#   from notifications.handler import notifications_command, notifications_callback
#   application.add_handler(CommandHandler("notifications", notifications_command))
#   application.add_handler(CallbackQueryHandler(notifications_callback, pattern="^notif_"))
#
# Callback patterns handled:
#   notif_settings        — show settings menu
#   notif_pause           — toggle notifications on/off
#   notif_mute_<id>       — deactivate a specific signal alert
#   notif_alerts          — show & manage signal alerts
#   notif_add_alert       — start add-alert flow (step 1: coin)
#   notif_alert_coin_<X>  — step 2: strategy
#   notif_alert_strat_<X>_<coin> — step 3: timeframe
#   notif_alert_tf_<X>_<strat>_<coin> — step 4: confirm & save
#   notif_del_<id>        — delete a signal alert
#   notif_history         — show last 10 notifications
#   notif_tf_<tf>         — update preferred timeframe

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active

from notifications.db import (
    ensure_prefs,
    update_prefs,
    get_user_alerts,
    add_alert,
    deactivate_alert,
    get_recent_history,
)

# ============================================================================
# DISPLAY MAPS
# ============================================================================

STRATEGY_NAMES = {
    "strat_1": "Strong Bounce Setup",
    "strat_2": "Breakout with Momentum",
    "strat_3": "Reversal After Sell-Off",
    "strat_4": "Trend Turning Bullish",
    "strat_5": "Deep Pullback Opportunity",
    "ANY":     "Any Strategy",
}

TF_NAMES = {
    "5m":  "5 Min",  "15m": "15 Min", "30m": "30 Min",
    "1h":  "1 Hour", "4h":  "4 Hours", "1d":  "1 Day",
    "ANY": "Any Timeframe",
}

# Popular coins shown in the add-alert coin picker
POPULAR_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP",
                 "ADA", "AVAX", "DOT", "LINK", "MATIC"]


# ============================================================================
# /notifications — MAIN COMMAND
# ============================================================================

async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point. Shows the notifications home screen with current status
    and quick-action buttons.
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/notifications")

    prefs = ensure_prefs(user_id)
    plan  = get_user_plan(user_id)
    is_pro = is_pro_plan(plan)

    status_icon = "🟢" if prefs["is_enabled"] else "🔴"
    freq_label  = "Twice daily" if prefs["frequency"] == "twice" else "Once daily"
    tf_label    = TF_NAMES.get(prefs["preferred_tf"], prefs["preferred_tf"])

    text = (
        f"🔔 <b>Notification Centre</b>\n\n"
        f"Status    : {status_icon} {'Active' if prefs['is_enabled'] else 'Paused'}\n"
        f"Schedule  : {freq_label} ({prefs['morning_time']} "
        f"{'& ' + prefs['evening_time'] + ' ' if prefs['frequency'] == 'twice' else ''}UTC)\n"
        f"Timeframe : {tf_label}\n\n"
        f"<b>Daily Brief</b> — top 3 setups + 3 weakest coins sent to you every morning"
        f"{' & evening' if prefs['frequency'] == 'twice' else ''}.\n\n"
    )

    if is_pro:
        alerts = get_user_alerts(user_id)
        text += f"<b>Signal Alerts</b> — {len(alerts)}/5 active\n"
        text += "Get notified the moment a coin matches your criteria.\n"
    else:
        text += "🔒 <b>Signal Alerts</b> — Pro only\n"
        text += "Upgrade to set per-coin triggers.\n"

    keyboard = _home_keyboard(is_pro, prefs["is_enabled"])
    await update.message.reply_text(text, parse_mode="HTML",
                                    reply_markup=keyboard)


def _home_keyboard(is_pro: bool, is_enabled: bool) -> InlineKeyboardMarkup:
    pause_label = "▶️ Resume Alerts" if not is_enabled else "⏸ Pause Alerts"
    rows = [
        [InlineKeyboardButton("⚙️ Preferences", callback_data="notif_settings")],
        [InlineKeyboardButton(pause_label, callback_data="notif_pause")],
        [InlineKeyboardButton("📋 History", callback_data="notif_history")],
    ]
    if is_pro:
        rows.insert(1, [InlineKeyboardButton(
            "🎯 Signal Alerts", callback_data="notif_alerts"
        )])
    else:
        rows.insert(1, [InlineKeyboardButton(
            "🔒 Signal Alerts (Pro)", callback_data="upgrade_menu"
        )])
    return InlineKeyboardMarkup(rows)


# ============================================================================
# CALLBACK ROUTER
# ============================================================================

async def notifications_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes all notif_ callbacks to the correct sub-handler."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "notif_settings":
        await _show_settings(query)
    elif data == "notif_pause":
        await _toggle_pause(query)
    elif data.startswith("notif_mute_"):
        alert_id = int(data.replace("notif_mute_", ""))
        await _mute_alert(query, alert_id)
    elif data == "notif_alerts":
        await _show_alerts(query)
    elif data == "notif_add_alert":
        await _add_alert_step1_coin(query)
    elif data.startswith("notif_alert_coin_"):
        coin = data.replace("notif_alert_coin_", "")
        await _add_alert_step2_strategy(query, coin)
    elif data.startswith("notif_alert_strat_"):
        payload = data.replace("notif_alert_strat_", "")
        strat_key, coin = payload.rsplit("|", 1)
        await _add_alert_step3_timeframe(query, coin, strat_key)
    elif data.startswith("notif_alert_tf_"):
        # format: notif_alert_tf_{tf}|{strat}|{coin}
        payload = data.replace("notif_alert_tf_", "")
        parts = payload.split("|")
        if len(parts) == 3:
            tf, strat, coin = parts
            await _add_alert_confirm(query, coin, strat, tf)
    elif data.startswith("notif_del_"):
        alert_id = int(data.replace("notif_del_", ""))
        await _delete_alert(query, alert_id)
    elif data == "notif_history":
        await _show_history(query)
    elif data.startswith("notif_tf_"):
        tf = data.replace("notif_tf_", "")
        await _update_preferred_tf(query, tf)
    elif data == "notif_back":
        await _back_to_home(query)


# ============================================================================
# SETTINGS
# ============================================================================

async def _show_settings(query) -> None:
    """Show preferences screen."""
    user_id = query.from_user.id
    prefs   = ensure_prefs(user_id)
    tf      = TF_NAMES.get(prefs["preferred_tf"], prefs["preferred_tf"])

    text = (
        "⚙️ <b>Notification Preferences</b>\n\n"
        f"Schedule  : {prefs['morning_time']} UTC"
        f"{' & ' + prefs['evening_time'] + ' UTC' if prefs['frequency'] == 'twice' else ''}\n"
        f"Timeframe : {tf}\n\n"
        "Choose your preferred timeframe for the daily brief:"
    )

    tf_buttons = []
    tfs = [("1h", "1 Hour"), ("4h", "4 Hours"), ("1d", "1 Day")]
    for tf_key, tf_name in tfs:
        active = "✅ " if prefs["preferred_tf"] == tf_key else ""
        tf_buttons.append(
            InlineKeyboardButton(
                f"{active}{tf_name}",
                callback_data=f"notif_tf_{tf_key}"
            )
        )

    keyboard = InlineKeyboardMarkup([
        tf_buttons,
        [InlineKeyboardButton("⬅️ Back", callback_data="notif_back")],
    ])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _update_preferred_tf(query, tf: str) -> None:
    """Save preferred timeframe and return to settings."""
    user_id = query.from_user.id
    update_prefs(user_id, preferred_tf=tf)
    await _show_settings(query)


async def _toggle_pause(query) -> None:
    """Toggle notifications on/off."""
    user_id = query.from_user.id
    prefs   = ensure_prefs(user_id)
    new_val = 0 if prefs["is_enabled"] else 1
    update_prefs(user_id, is_enabled=new_val)
    await _back_to_home(query)


# ============================================================================
# SIGNAL ALERTS — VIEW & DELETE
# ============================================================================

async def _show_alerts(query) -> None:
    """Show user's active signal alerts with delete buttons."""
    user_id = query.from_user.id
    plan    = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await query.edit_message_text(
            "🔒 Signal alerts are a <b>Pro</b> feature.\n\n"
            "Upgrade to get notified the moment a coin matches your criteria.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 Upgrade to Pro", callback_data="upgrade_menu"),
                InlineKeyboardButton("⬅️ Back", callback_data="notif_back"),
            ]])
        )
        return

    alerts  = get_user_alerts(user_id)
    rows    = []

    if alerts:
        text = f"🎯 <b>Your Signal Alerts</b> ({len(alerts)}/5)\n\n"
        for a in alerts:
            sym   = a["symbol"]
            strat = STRATEGY_NAMES.get(a["strategy_key"], a["strategy_key"])
            tf    = TF_NAMES.get(a["timeframe"], a["timeframe"])
            text += f"• <b>{sym}</b> | {strat} | {tf} | min score {a['min_score']}\n"
            rows.append([InlineKeyboardButton(
                f"🗑 Delete — {sym} {tf}",
                callback_data=f"notif_del_{a['id']}"
            )])
    else:
        text = (
            "🎯 <b>Signal Alerts</b>\n\n"
            "You have no active alerts yet.\n"
            "Add one below to get notified when a coin matches a strategy."
        )

    if len(alerts) < 5:
        rows.append([InlineKeyboardButton("➕ Add Alert", callback_data="notif_add_alert")])

    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="notif_back")])

    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(rows))


async def _delete_alert(query, alert_id: int) -> None:
    """Soft-delete a signal alert and refresh the list."""
    user_id = query.from_user.id
    deactivate_alert(alert_id, user_id)
    await _show_alerts(query)


async def _mute_alert(query, alert_id: int) -> None:
    """
    Mute button pressed from inside a signal notification.
    Deactivates the alert and confirms to the user.
    """
    user_id = query.from_user.id
    success = deactivate_alert(alert_id, user_id)

    if success:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Alert muted", callback_data="notif_alerts"
            )
        ]]))
    else:
        await query.answer("Alert not found or already removed.", show_alert=True)


# ============================================================================
# SIGNAL ALERTS — ADD FLOW (3 steps)
# ============================================================================

async def _add_alert_step1_coin(query) -> None:
    """Step 1: Pick a coin."""
    text = (
        "🎯 <b>Add Signal Alert</b> — Step 1 of 3\n\n"
        "Which coin do you want to watch?\n"
        "<i>Select a coin or choose Any to watch all top 100.</i>"
    )

    # 2 coins per row
    coin_rows = []
    for i in range(0, len(POPULAR_COINS), 2):
        row = [
            InlineKeyboardButton(c, callback_data=f"notif_alert_coin_{c}")
            for c in POPULAR_COINS[i:i+2]
        ]
        coin_rows.append(row)

    coin_rows.append([
        InlineKeyboardButton("🌐 Any Top 100", callback_data="notif_alert_coin_ANY")
    ])
    coin_rows.append([
        InlineKeyboardButton("⬅️ Back", callback_data="notif_alerts")
    ])

    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(coin_rows))


async def _add_alert_step2_strategy(query, coin: str) -> None:
    """Step 2: Pick a strategy."""
    coin_label = coin if coin != "ANY" else "Any coin"
    text = (
        f"🎯 <b>Add Signal Alert</b> — Step 2 of 3\n\n"
        f"Coin: <b>{coin_label}</b>\n\n"
        "Which strategy should trigger this alert?"
    )

    strat_rows = [
        [InlineKeyboardButton(
            name,
            callback_data=f"notif_alert_strat_{key}|{coin}"
        )]
        for key, name in STRATEGY_NAMES.items()
        if key != "ANY"
    ]
    strat_rows.append([
        InlineKeyboardButton(
            "⚡ Any Strategy",
            callback_data=f"notif_alert_strat_ANY|{coin}"
        )
    ])
    strat_rows.append([
        InlineKeyboardButton("⬅️ Back", callback_data="notif_add_alert")
    ])

    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(strat_rows))


async def _add_alert_step3_timeframe(query, coin: str, strat_key: str) -> None:
    """Step 3: Pick a timeframe."""
    coin_label  = coin if coin != "ANY" else "Any coin"
    strat_label = STRATEGY_NAMES.get(strat_key, strat_key)

    text = (
        f"🎯 <b>Add Signal Alert</b> — Step 3 of 3\n\n"
        f"Coin     : <b>{coin_label}</b>\n"
        f"Strategy : <b>{strat_label}</b>\n\n"
        "Which timeframe?"
    )

    tf_items = [("1h", "1 Hour"), ("4h", "4 Hours"), ("1d", "1 Day"),
                ("ANY", "Any Timeframe")]
    tf_rows = []
    for i in range(0, len(tf_items), 2):
        row = [
            InlineKeyboardButton(
                name,
                callback_data=f"notif_alert_tf_{tf_key}|{strat_key}|{coin}"
            )
            for tf_key, name in tf_items[i:i+2]
        ]
        tf_rows.append(row)

    tf_rows.append([
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data=f"notif_alert_coin_{coin}"
        )
    ])

    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(tf_rows))


async def _add_alert_confirm(query, coin: str, strat_key: str, tf: str) -> None:
    """Final step: save the alert and confirm."""
    user_id = query.from_user.id

    coin_label  = coin if coin != "ANY" else "Any top-100 coin"
    strat_label = STRATEGY_NAMES.get(strat_key, strat_key)
    tf_label    = TF_NAMES.get(tf, tf)

    try:
        add_alert(
            user_id=user_id,
            symbol=coin,
            strategy_key=strat_key,
            timeframe=tf,
            min_score=5,
            cooldown_minutes=240,
        )

        alerts_remaining = 5 - len(get_user_alerts(user_id))

        text = (
            "✅ <b>Alert Created</b>\n\n"
            f"Coin     : <b>{coin_label}</b>\n"
            f"Strategy : <b>{strat_label}</b>\n"
            f"Timeframe: <b>{tf_label}</b>\n"
            f"Min score: 5  |  Cooldown: 4h\n\n"
            f"You'll be notified as soon as this signal fires.\n"
            f"<i>{alerts_remaining} alert slot{'s' if alerts_remaining != 1 else ''} remaining.</i>"
        )

    except ValueError as e:
        text = (
            f"⚠️ <b>Could not create alert</b>\n\n"
            f"{e}\n\n"
            "Delete an existing alert to make room."
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Manage Alerts", callback_data="notif_alerts")],
        [InlineKeyboardButton("⬅️ Home", callback_data="notif_back")],
    ])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


# ============================================================================
# HISTORY
# ============================================================================

async def _show_history(query) -> None:
    """Show last 10 notifications sent to this user."""
    user_id = query.from_user.id
    history = get_recent_history(user_id, limit=10)

    if not history:
        text = (
            "📋 <b>Notification History</b>\n\n"
            "No notifications sent yet.\n"
            "Your daily briefs and signal alerts will appear here."
        )
    else:
        from datetime import datetime, timezone
        text = "📋 <b>Notification History</b>\n\n"
        for row in history:
            dt   = datetime.fromtimestamp(row["sent_at"], tz=timezone.utc)
            time_str = dt.strftime("%b %-d %H:%M")

            if row["alert_type"] == "daily_brief":
                text += f"📡 Daily Brief · {time_str} UTC\n"
            else:
                sym   = row["symbol"] or "?"
                strat = row["strategy_key"] or "?"
                tf    = TF_NAMES.get(row["timeframe"], row["timeframe"] or "?")
                text += f"⚡ {sym} · {strat} · {tf} · {time_str} UTC\n"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Back", callback_data="notif_back")
    ]])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


# ============================================================================
# BACK TO HOME
# ============================================================================

async def _back_to_home(query) -> None:
    """Rebuild and show the home screen."""
    user_id = query.from_user.id
    prefs   = ensure_prefs(user_id)
    plan    = get_user_plan(user_id)
    is_pro  = is_pro_plan(plan)

    status_icon = "🟢" if prefs["is_enabled"] else "🔴"
    freq_label  = "Twice daily" if prefs["frequency"] == "twice" else "Once daily"
    tf_label    = TF_NAMES.get(prefs["preferred_tf"], prefs["preferred_tf"])

    text = (
        f"🔔 <b>Notification Centre</b>\n\n"
        f"Status    : {status_icon} {'Active' if prefs['is_enabled'] else 'Paused'}\n"
        f"Schedule  : {freq_label} ({prefs['morning_time']} "
        f"{'& ' + prefs['evening_time'] + ' ' if prefs['frequency'] == 'twice' else ''}UTC)\n"
        f"Timeframe : {tf_label}\n\n"
        f"<b>Daily Brief</b> — top 3 setups + 3 weakest coins sent every morning"
        f"{' & evening' if prefs['frequency'] == 'twice' else ''}.\n\n"
    )

    if is_pro:
        alerts = get_user_alerts(user_id)
        text += f"<b>Signal Alerts</b> — {len(alerts)}/5 active\n"
    else:
        text += "🔒 <b>Signal Alerts</b> — Pro only\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=_home_keyboard(is_pro, prefs["is_enabled"])
    )


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