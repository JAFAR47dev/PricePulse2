# handlers/set_alert/callback_handler.py

# handlers/set_alert/callback_handler.py
from telegram import Update
from telegram.ext import ContextTypes
from .flow_manager import ask_symbol_input  # We will create this next step
from utils.indicator_rules import (
    SUPPORTED_INDICATORS,
    SUPPORTED_INTERVALS,
    validate_indicator_rule
) 
async def alert_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle selection of alert type from inline keyboard.
    Save it to context.user_data["alert_flow"]["type"] and move to symbol input step.
    """
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    # Ensure the callback matches pattern
    if not query.data.startswith("set_alert_type:"):
        return

    alert_type = query.data.split(":")[1]

    # Save to user_data
    context.user_data["alert_flow"]["type"] = alert_type
    context.user_data["alert_flow"]["step"] = "symbol_input"

    # Move to next step: symbol input handler
    await ask_symbol_input(update, context)


from .flow_manager import ask_for_details

async def symbol_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Capture user's coin symbol input and move to details step.
    """
    alert_flow = context.user_data.get("alert_flow", {})
    if not alert_flow or alert_flow.get("step") != "symbol_input":
        return  # Ignore if not expecting symbol

    symbol = update.message.text.strip().upper()

    # Basic validation: 1-5 alphanumeric characters
    if not symbol.isalnum() or len(symbol) > 5:
        await update.message.reply_text(
            "❌ Invalid symbol. Try again with a valid coin symbol (e.g., BTC, ETH)."
        )
        return

    # Save symbol and advance step
    alert_flow["symbol"] = symbol
    alert_flow["step"] = "details_input"  # next step: collect alert details
    await ask_for_details(update, context)
    

from .flow_manager import ask_persistence 

async def details_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Capture alert parameters entered by the user and advance to persistence step.
    """
    alert_flow = context.user_data.get("alert_flow", {})
    if not alert_flow or alert_flow.get("step") != "details_input":
        return  # Ignore if not expecting details

    alert_type = alert_flow.get("type")
    user_input = update.message.text.strip()

    try:
        if alert_type == "price":
            condition, target = user_input.split()
            if condition not in (">", "<"):
                raise ValueError
            alert_flow["condition"] = condition
            alert_flow["target"] = float(target)

        elif alert_type == "percent":
            alert_flow["threshold"] = float(user_input)

        elif alert_type == "volume":
            parts = user_input.split()
            alert_flow["multiplier"] = float(parts[0])
            alert_flow["timeframe"] = parts[1] if len(parts) > 1 else "1h"

        elif alert_type == "risk":
            stop_loss, take_profit = map(float, user_input.split())
            if stop_loss >= take_profit:
                raise ValueError
            alert_flow["stop_loss"] = stop_loss
            alert_flow["take_profit"] = take_profit
       
    
        elif alert_type == "indicator":
            user_text = user_input.strip()
            tokens = user_text.split()

            if len(tokens) < 3:
                example_list = "\n".join(
                    f"• `{rule['example']}`" 
                    for rule in SUPPORTED_INDICATORS.values()
                    if "example" in rule
                )
                return await update.message.reply_text(
                    "❌ Invalid format.\n\n"
                    "**Correct format:**\n"
                    "`indicator operator value [timeframe]`\n\n"
                    "**Examples:**\n"
                    f"{example_list}",
                    parse_mode="Markdown"
                )

            indicator_raw = tokens[0].lower()
            operator_raw = tokens[1]
            value_raw = tokens[2]
            timeframe_raw = tokens[3].lower() if len(tokens) > 3 else "1h"
            
            # --- Timeframe validation ---
            if timeframe_raw not in SUPPORTED_INTERVALS:
                supported_tf = ", ".join(SUPPORTED_INTERVALS)
                return await update.message.reply_text(
                    f"❌ Unsupported timeframe: `{timeframe_raw}`\n\n"
                    f"**Supported intervals:**\n{supported_tf}",
                    parse_mode="Markdown"
                )

            # Validate numeric value
            try:
                numeric_value = float(value_raw)
            except:
                return await update.message.reply_text(
                    f"❌ `{value_raw}` is not a valid number.\n"
                    "Example: `rsi < 30 1h`",
                    parse_mode="Markdown"
                )

            # Build the parsed rule
            condition_data = {
                "indicator": indicator_raw,
                "operator": operator_raw,
                "value": numeric_value,
                "timeframe": timeframe_raw
            }

            # --- Validate using indicator_rules.py ---
            ok, error_message = validate_indicator_rule(condition_data)
            if not ok:
                return await update.message.reply_text(
                    error_message,
                    parse_mode="Markdown"
                )

            # Save to alert_flow for the next step
            alert_flow["condition"] = condition_data
            alert_flow["indicator_block"] = user_text
           
          
       
    except Exception:
        await update.message.reply_text("❌ Invalid input format. Please try again.")
        return

    alert_flow["step"] = "repeat_selection"  # matches your persistence button handler
    await ask_persistence(update, context)
    
from .flow_manager import confirm_alert

async def persistence_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle user's choice for persistent alert.
    """
    query = update.callback_query
    await query.answer()  # Acknowledge button press

    alert_flow = context.user_data.get("alert_flow", {})
    if not alert_flow or alert_flow.get("step") != "repeat_selection":
        return  # ignore if not expecting repeat

    # Extract yes/no from callback_data: "set_alert_persistence:yes"
    choice = query.data.split(":")[1]  # "yes" or "no"
    alert_flow["repeat"] = 1 if choice == "yes" else 0

    # Update step → next is confirm
    alert_flow["step"] = "confirm_alert"

    import asyncio

    msg = await query.edit_message_text(
        f"🔁 Persistent: {'Yes' if alert_flow['repeat'] else 'No'}\n\n"
    "✅ Now confirm your alert."
    )

    await asyncio.sleep(0.3)
    await msg.delete()

    # Display final summary
    await confirm_alert(update, context)
    

from .flow_manager import handle_final_alert_creation

async def confirmation_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the Confirm / Cancel buttons for alert setup.
    """
    query = update.callback_query
    await query.answer()

    alert_flow = context.user_data.get("alert_flow", {})
    if not alert_flow or alert_flow.get("step") != "confirm_alert":
        return  # Ignore irrelevant clicks

    # Extract "yes" or "no" from callback data
    choice = query.data.split(":")[1]  # yes/no

    if choice == "yes":
        # ✅ Save the alert
        await handle_final_alert_creation(update, context, alert_flow)
        await query.edit_message_text("🎉 Alert successfully created!")

    else:
        # ❌ Cancel
        context.user_data.pop("alert_flow", None)
        await query.edit_message_text("❌ Alert creation cancelled.")