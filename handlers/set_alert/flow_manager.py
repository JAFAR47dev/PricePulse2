from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from models.user import get_user_plan
from utils.auth import is_pro_plan

ALERT_TYPES = [
    ("💰 Price", "price"),
    ("📈 Percent", "percent"),
    ("📊 Volume", "volume"),
    ("⚠️ Risk", "risk"),
    ("🤖 Custom", "custom"),
]

async def start_set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Step 1: Ask user which alert type to create.
    Enforces plan restrictions for Free users.
    """

    user_id = update.effective_user.id
    plan = get_user_plan(user_id)
    pro = is_pro_plan(plan)

    context.user_data["alert_flow"] = {"step": "select_type"}

    # ------------------------------------
    # 🟢 PRO USERS → show all buttons
    # ------------------------------------
    if pro:
        row1 = [InlineKeyboardButton("💰 Price", callback_data="set_alert_type:price")]

        row2 = [
            InlineKeyboardButton("📈 Percent", callback_data="set_alert_type:percent"),
            InlineKeyboardButton("📊 Volume", callback_data="set_alert_type:volume")
        ]

        row3 = [
            InlineKeyboardButton("⚠️ Risk", callback_data="set_alert_type:risk"),
            InlineKeyboardButton("🤖 Custom", callback_data="set_alert_type:custom")
        ]

        keyboard = [row1, row2, row3]

    # ------------------------------------
    # 🔴 FREE USERS → price only
    # show disabled buttons for others
    # ------------------------------------
    else:
        row1 = [InlineKeyboardButton("💰 Price", callback_data="set_alert_type:price")]

        row2 = [
            InlineKeyboardButton("📈 Percent (Pro)", callback_data="upgrade_required"),
            InlineKeyboardButton("📊 Volume (Pro)", callback_data="upgrade_required")
        ]

        row3 = [
            InlineKeyboardButton("⚠️ Risk (Pro)", callback_data="upgrade_required"),
            InlineKeyboardButton("🤖 Custom (Pro)", callback_data="upgrade_required")
        ]

        keyboard = [row1, row2, row3]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send message
    if update.message:
        await update.message.reply_text(
            "🎯 *Select the type of alert you want to create:*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.callback_query.message.reply_text(
            "🎯 *Select the type of alert you want to create:*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
async def handle_upgrade_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "🚫 Advanced alerts are for *Pro users only*.\n\n"
        "Upgrade now to unlock:\n"
        "• Percent alerts\n"
        "• Volume alerts\n"
        "• Risk alerts\n"
        "• Custom AI alerts\n\n"
        "Use /upgrade to get full access!",
        parse_mode="Markdown"
    )


async def ask_symbol_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Step 2: Prompt user to enter coin symbol after selecting alert type.
    """
    if "alert_flow" not in context.user_data:
        context.user_data["alert_flow"] = {}

    # Check if alert type was selected
    if "type" not in context.user_data["alert_flow"]:
        await update.message.reply_text("⚠️ Please select an alert type first. Use /set to start.")
        return

    # Ask user for coin symbol
    if update.message:
        await update.message.reply_text(
            "💡 Please enter the *coin symbol* you want to track (e.g., BTC, ETH, SOL):",
            parse_mode="Markdown"
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            "💡 Please enter the *coin symbol* you want to track (e.g., BTC, ETH, SOL):",
            parse_mode="Markdown"
        )

    # Set step state for symbol input
    context.user_data["alert_flow"]["step"] = "symbol_input"
    

async def ask_for_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Step 3: Dynamically prompt user for alert-specific details
    based on alert type stored in alert_flow.
    """
    alert_flow = context.user_data.get("alert_flow", {})
    alert_type = alert_flow.get("type")

    if not alert_type:
        await update.message.reply_text("⚠️ Alert type missing. Start again with /set")
        return

    if alert_type == "price":
        await update.message.reply_text(
            "💰 *Price Alert*\nEnter the condition and target price (e.g., `> 70000`):",
            parse_mode="Markdown"
        )
    elif alert_type == "percent":
        await update.message.reply_text(
            "📈 *Percent Alert*\nEnter the percentage threshold (e.g., `5` for ±5%):",
            parse_mode="Markdown"
        )
    elif alert_type == "volume":
        # Optional: a helper to explain volume input in more detail
        await update.message.reply_text(
            "📊 *Volume Alert*\nEnter multiplier and optional timeframe (e.g., `2.5 4h`). Default timeframe = 1h",
            parse_mode="Markdown"
        )
    elif alert_type == "risk":
        await update.message.reply_text(
            "⚠️ *Risk Alert*\nEnter stop-loss and take-profit separated by space (e.g., `30000 35000`):",
            parse_mode="Markdown"
        )
    elif alert_type == "custom":
        await update.message.reply_text(
            "🤖 *Custom Alert*\nEnter full custom condition (e.g., `BTC > 30000 rsi < 30`):",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Unknown alert type. Start over with /set")
        alert_flow.clear()
        return

    # Set next step for message handler
    alert_flow["step"] = "details_input"


async def ask_persistence(update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ask the user if they want the alert to be persistent (repeat).
    Supports both message-triggered and callback-triggered flow.
    """
    # Ensure alert_flow exists
    alert_flow = context.user_data.setdefault("alert_flow", {})

    # Set current step
    alert_flow["step"] = "repeat_selection"

    # Buttons
    buttons = [
        InlineKeyboardButton("✅ Yes", callback_data="set_alert_persistence:yes"),
        InlineKeyboardButton("🚫 No", callback_data="set_alert_persistence:no"),
    ]
    markup = InlineKeyboardMarkup([buttons])

    # Handle both message and callback contexts
    if update.message:
        await update.message.reply_text(
            "🔁 Do you want this alert to be persistent (repeat)?",
            reply_markup=markup
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            "🔁 Do you want this alert to be persistent (repeat)?",
            reply_markup=markup
        )


from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def confirm_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show a summary of the alert for final confirmation.
    """
    alert_flow = context.user_data.get("alert_flow", {})
    if not alert_flow:
        await update.message.reply_text("⚠️ Something went wrong. Start again with /set")
        return
    
    alert_flow["step"] = "confirm_alert"

    # Build summary message dynamically
    alert_type = alert_flow.get("type", "N/A").capitalize()
    symbol = alert_flow.get("symbol", "N/A")
    repeat = "Yes" if alert_flow.get("repeat") else "No"

    # Include parameters depending on type
    details = ""
    if alert_type.lower() == "price":
        details = f"Condition: {alert_flow.get('condition', '?')} {alert_flow.get('target', '?')}"
    elif alert_type.lower() == "percent":
        details = f"Threshold: {alert_flow.get('threshold', '?')}%"
    elif alert_type.lower() == "volume":
        details = f"Multiplier: {alert_flow.get('multiplier', '?')}× | Timeframe: {alert_flow.get('timeframe', '1h')}"
    elif alert_type.lower() == "risk":
        details = f"Stop: {alert_flow.get('stop_loss', '?')} | Take: {alert_flow.get('take_profit', '?')}"
    elif alert_type.lower() == "custom":
        details = f"Condition: {alert_flow.get('custom_condition', '?')}"

    summary = (
        "✅ *Confirm Alert Setup:*\n\n"
        f"• Type: {alert_type}\n"
        f"• Symbol: {symbol}\n"
        f"• {details}\n"
        f"• Repeat: {repeat}"
    )

    # Inline buttons with the correct callback format
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="set_alert_confirm:yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="set_alert_confirm:no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text(
            summary,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            summary,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
from models.user import get_user_plan
from handlers.alert_handlers import (
    handle_price_alert,
    handle_percent_alert,
    handle_volume_alert,
    handle_risk_alert,
    handle_custom_alert,
)

async def handle_final_alert_creation(update, context, alert_flow):
    """
    Take collected info from alert_flow and call the **existing handlers** to save alert.
    """
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)
    repeat_flag = "repeat" if alert_flow.get("repeat") else None

    alert_type = alert_flow.get("type").lower()

    # Convert flow data into args array expected by existing handlers
    if alert_type == "price":
        args = [
            alert_flow["symbol"],
            alert_flow["condition"],
            str(alert_flow["target"])
        ]
        if repeat_flag:
            args.append(repeat_flag)
        await handle_price_alert(update, context, args, plan)

    elif alert_type == "percent":
        args = [
            alert_flow["symbol"],
            str(alert_flow["threshold"])
        ]
        if repeat_flag:
            args.append(repeat_flag)
        await handle_percent_alert(update, context, args, plan)

    elif alert_type == "volume":
        args = [
            alert_flow["symbol"],
            str(alert_flow["multiplier"]),
            alert_flow.get("timeframe", "1h")
        ]
        if repeat_flag:
            args.append(repeat_flag)
        await handle_volume_alert(update, context, args, plan)

    elif alert_type == "risk":
        args = [
            alert_flow["symbol"],
            str(alert_flow["stop_loss"]),
            str(alert_flow["take_profit"])
        ]
        if repeat_flag:
            args.append(repeat_flag)
        await handle_risk_alert(update, context, args, plan)

    elif alert_type == "custom":
        args = [
            alert_flow["symbol"],
            alert_flow["condition"],
            str(alert_flow["target"]),
        ] + alert_flow["indicator_block"]
        if repeat_flag:
            args.append(repeat_flag)
        await handle_custom_alert(update, context, args, plan)

    # Clear flow after saving
    context.user_data.pop("alert_flow", None)
    
    context.user_data.pop("alert_step", None)

from .callback_handler import (
    alert_type_callback,
    persistence_callback_handler,
    confirmation_callback_handler
)

from .callback_handler import symbol_input_handler
from .callback_handler import details_input_handler

async def set_alert_message_router(update, context):
    # If user is in Favorites flow, ignore /set flow completely
    if context.user_data.get("fav_mode"):
        return

    # Get alert flow
    alert_flow = context.user_data.get("alert_flow")
    
    if not alert_flow or "fav_mode" in context.user_data:
            return
            

    step = alert_flow.get("step")

    if step == "symbol_input":
        return await symbol_input_handler(update, context)

    elif step == "details_input":
        return await details_input_handler(update, context)
        
        
    # Ignore unrelated messages
def register_set_handlers(app):
    # /set command
    app.add_handler(CommandHandler("set", start_set_alert))

    app.add_handler(CallbackQueryHandler(handle_upgrade_required, pattern="^upgrade_required$"))
    
    # Alert type buttons
    app.add_handler(
        CallbackQueryHandler(alert_type_callback, pattern=r"^set_alert_type:")
    )

    # Persistence buttons
    app.add_handler(
        CallbackQueryHandler(persistence_callback_handler, pattern=r"^set_alert_persistence:")
    )

    app.add_handler(  
        CallbackQueryHandler(confirmation_callback_handler, pattern=r"^set_alert_confirm:")  
    )  
  

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            set_alert_message_router
        )
    )
    