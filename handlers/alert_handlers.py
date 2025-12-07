from telegram import Update
from datetime import datetime
from telegram.ext import ContextTypes
from utils.prices import get_crypto_prices
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, CommandHandler
from services.alert_service import delete_all_alerts
from utils.auth import is_pro_plan
from models.user import get_user_plan
from models.alert import (
    create_price_alert,
    create_percent_alert,
    create_volume_alert,
    create_risk_alert,
    create_indicator_alert
    )


# Conversation states for removing alerts
REMOVE_CONFIRM = range(1)

from models.user import can_create_price_alert

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This is a *Pro-only* feature.\nUpgrade to unlock AI backtesting.\n\n👉 /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    args = context.args
    

    if len(args) < 2:
        await update.message.reply_text("❌ Usage:\n/set price BTC > 70000\n/set percent ETH 5\n/set volume SOL 1.2 1h\n/set risk BTC 30000 35000 [repeat]")
        return

 
    alert_type = args[0].lower()
    handlers = {
        "price": handle_price_alert,
        "percent": handle_percent_alert,
        "volume": handle_volume_alert,
        "risk": handle_risk_alert,
        "custom": handle_custom_alert,
    }

    if alert_type not in handlers:
        await update.message.reply_text("❌ Invalid alert type. Use one of: price, percent, volume, risk, custom")
        return

    # Enforce Free Plan limits
    if plan == "free" and alert_type != "price":
        await update.message.reply_text("🚫 Advanced alerts are for *Pro users* only.\nUse /upgrade to unlock.", parse_mode="Markdown")
        return

    await handlers[alert_type](update, context, args[1:], plan)
    
async def handle_price_alert(update, context, args, plan):
    if len(args) < 3:
        await update.message.reply_text("❌ Usage: /set price BTC > 70000 [repeat]")
        return

    user_id = update.effective_user.id
    symbol = args[0].upper()
    condition = args[1]
    try:
        target_price = float(args[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid price format.")
        return

    # Persistent alert
    repeat = 1 if len(args) > 3 and args[3].lower() == "repeat" else 0

    from models.user import get_user_plan
    from models.alert import create_price_alert

    # Fetch current plan (optional, still available if you need it elsewhere)
    plan = get_user_plan(user_id)

    # ✅ No limits for free or Pro users
    create_price_alert(user_id, symbol, condition, target_price, repeat)

    msg = f"✅ Price alert set: {symbol} {condition} {target_price}"
    if repeat:
        msg += " 🔁 (persistent alert)"
    if update.callback_query:
        await update.callback_query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)
        
async def handle_percent_alert(update, context, args, plan):
    
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    # 🔒 Plan check
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade to unlock.",
            parse_mode="Markdown"
        )
        return

    # 🧩 Argument validation
    if len(args) < 2:
        await update.message.reply_text("❌ Usage: /set percent BTC 5 [repeat]")
        return

    symbol = args[0].upper()

    try:
        threshold = float(args[1])
        if threshold <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Enter a valid percentage (e.g., 5)")
        return

    repeat = 1 if len(args) > 2 and args[2].lower() == "repeat" else 0

    # ⚙️ Await the async price fetch properly
    price_data = await get_crypto_prices([symbol])
    if not price_data or symbol not in price_data:
        await update.message.reply_text("⚠️ Could not fetch current price. Try again later.")
        return

    base_price = price_data[symbol]

    # 💾 Store the alert in DB
    create_percent_alert(user_id, symbol, base_price, threshold, repeat)

    msg = (
        f"✅ Percent alert set: Notify when {symbol}  moves ±{threshold}% from ${base_price:.2f}"
    )
    if repeat:
        msg += " 🔁 (persistent alert)"
    if update.callback_query:
        await update.callback_query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)
        
from utils.indicators import get_volume_comparison 

async def handle_volume_alert(update, context, args, plan):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    # 🔒 Restrict to Pro users
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade to unlock.",
            parse_mode="Markdown"
        )
        return

    # ✅ Usage check
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: `/set volume <symbol> <multiplier> [timeframe] [repeat]`\n\n"
            "Example: `/set volume BTCUSDT 2.5 4h repeat`\n\n"
            "_Default timeframe: 1h_",
            parse_mode="Markdown"
        )
        return

    # 🎯 Parse symbol and multiplier
    symbol = args[0].upper()

    try:
        multiplier = float(args[1])
        if multiplier <= 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Multiplier must be a number greater than 1 (e.g., 2.5)")
        return

    # 🕒 Timeframe handling (default = 1h)
    valid_timeframes = ["15m", "30m", "1h", "4h", "1d" , "7d", "14d", "30d", "90d", "180d", "365"]
    timeframe = "1h"

    if len(args) > 2:
        tf_candidate = args[2].lower()
        if tf_candidate in valid_timeframes:
            timeframe = tf_candidate
        elif tf_candidate != "repeat":
            await update.message.reply_text(
                f"⚠️ Invalid timeframe: `{tf_candidate}`\n\n"
                f"Please use one of: `{'`, `'.join(valid_timeframes)}`\n"
                f"_Example: /set volume BTC 2.5 4h repeat_",
                parse_mode="Markdown"
            )
            return

    # 🔁 Check for 'repeat'
    repeat = 1 if "repeat" in [a.lower() for a in args] else 0

    # 📊 Fetch current + average volume
    try:
        current_volume, average_volume = await get_volume_comparison(symbol, timeframe)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not fetch volume data for {symbol}.\n{e}")
        return

    # 💡 Calculate trigger volume
    trigger_volume = round(average_volume * multiplier, 2)

    # 💾 Store alert
    create_volume_alert(user_id, symbol, multiplier, timeframe, repeat)

    # ✅ Confirmation message with real data
    msg = (
        f"✅ Volume Alert Created!\n\n"
        f"• Symbol: {symbol}\n"
        f"• Timeframe: {timeframe}\n"
        f"• Average Volume: {average_volume:,} USD\n"
        f"• Current Volume: {current_volume:,} USD\n"
        f"• Trigger When Volume ≥ {trigger_volume:,} USD\n"
        f"• Multiplier: {multiplier}×\n"
        f"• Repeat: {'Yes' if repeat else 'No'}"
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)
        
    
async def handle_risk_alert(update, context, args, plan):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

  
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade to unlock.",
            parse_mode="Markdown"
        )
        return

    if len(args) < 3:
        await update.message.reply_text("❌ Usage: /set risk BTC 30000 35000 [repeat]")
        return

    symbol = args[0].upper()

    try:
        stop_price = float(args[1])
        take_price = float(args[2])
        if stop_price <= 0 or take_price <= 0 or stop_price >= take_price:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Enter valid numbers for Stop-Loss and Take-Profit. Ensure stop is lower than take.")
        return

    repeat = 1 if len(args) > 3 and args[3].lower() == "repeat" else 0

  
    create_risk_alert(user_id, symbol, stop_price, take_price, repeat)

    msg = (
        f"✅ Risk alert set for {symbol}:\n"
        f"• Stop-Loss: ${stop_price:.2f}\n"
        f"• Take-Profit: ${take_price:.2f}\n"
        f"{'🔁 Repeat enabled' if repeat else ''}"
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)
        
from utils.indicator_rules import validate_indicator_rule

async def handle_indicator_alert(update, context, args, plan):
    user_id = update.effective_user.id

    # --- Ensure Pro Plan ---
    if not is_pro_plan(plan):
        msg = (
            "🔒 *Indicator Alerts are for Pro users only.*\n"
            "Upgrade with /upgrade to unlock."
        )
        if update.callback_query:
            return await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
        return await update.message.reply_text(msg, parse_mode="Markdown")

    # --- Validate args format ---
    if len(args) < 2:
        return await update.message.reply_text("❌ Invalid alert payload.")

    symbol = args[0].upper()
    condition = args[1]
    repeat = 1 if (len(args) > 2 and args[2]) else 0

    
    # --- Single indicator rule expected ---
    indicator_rule = {
        "indicator": condition.get("indicator"),
        "operator": condition.get("operator"),
        "value": condition.get("value"),
        "timeframe": condition.get("timeframe", "1h")
    }

    # Validate indicator using your file
    ok, error = validate_indicator_rule(indicator_rule)
    if not ok:
        return await update.message.reply_text(error, parse_mode="Markdown")

    # Build readable indicator text
    ind_text = (
        f"{indicator_rule['indicator'].upper()} "
        f"{indicator_rule['operator']} {indicator_rule['value']} "
        f"({indicator_rule['timeframe']})"
        )
    
    readable_condition = ind_text
    
    # Insert into DB
    create_indicator_alert(
        user_id=user_id,
        symbol=symbol,
        indicator=indicator_rule["indicator"],
        operator=indicator_rule["operator"],
        value=indicator_rule["value"],
        timeframe=indicator_rule.get("timeframe", "1h"),
        repeat=repeat
    )

    # --- Confirmation Message ---
    msg = (
        "✅ *Indicator Alert Created*\n\n"
        f"• *Symbol:* {symbol}\n"
        f"• *Condition:* {readable_condition}\n"
        f"• *Repeat:* {'Yes 🔁' if repeat else 'No'}"
    )

    if update.callback_query:
        return await update.callback_query.message.reply_text(msg, parse_mode="Markdown")

    return await update.message.reply_text(msg, parse_mode="Markdown")

    
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from models.alert import (
    get_price_alerts, get_percent_alerts, get_volume_alerts,
    get_risk_alerts, get_indicator_alerts, get_portfolio_value_limits,
    delete_price_alert, delete_percent_alert, delete_volume_alert,
    delete_risk_alert, delete_indicator_alert, delete_portfolio_limit,
    delete_portfolio_target
)

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    
    keyboard = [
        [
            InlineKeyboardButton("💰 Price Alerts", callback_data="remove:price"),
            InlineKeyboardButton("📈 Percent Alerts", callback_data="remove:percent")
        ],
        [
            InlineKeyboardButton("📊 Volume Alerts", callback_data="remove:volume"),
            InlineKeyboardButton("⚠️ Risk Alerts", callback_data="remove:risk")
        ],
        [
            InlineKeyboardButton("🤖 Indicator Alerts", callback_data="remove:indicator"),
            InlineKeyboardButton("💼 Portfolio Loss Limit", callback_data="remove:portfoliolimit")
        ],
        [
            InlineKeyboardButton("🎯 Portfolio Target", callback_data="remove:portfoliotarget"),
            InlineKeyboardButton("❌ Close", callback_data="close_menu")
        ]
    ]

    await update.message.reply_text(
        "🗑 *Select what you want to remove:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    
def format_alert_label(alert_type: str, row: tuple) -> str:
    """
    Converts raw DB tuple rows into readable labels for inline keyboards.
    """

    if alert_type == "price":
        # row: (id, symbol, condition, target_price, repeat)
        _, symbol, condition, target, _ = row
        return f"{symbol} {condition} {target}"

    elif alert_type == "percent":
        # row: (id, symbol, base_price, threshold_percent, repeat)
        _, symbol, base, percent, _ = row
        return f"{symbol} Δ{percent}% (Base {base})"

    elif alert_type == "volume":
        # row: (id, symbol, timeframe, multiplier, repeat)
        _, symbol, timeframe, mult, _ = row
        return f"{symbol} Vol x{mult} ({timeframe})"

    elif alert_type == "risk":
        # row: (id, symbol, stop_price, take_price, repeat)
        _, symbol, stop, take, _ = row
        return f"{symbol} SL {stop} / TP {take}"
    
    elif alert_type == "indicator":
        # row: (id, user_id, symbol, indicator, condition, timeframe, repeat, created_at)
        _, symbol, indicator, condition, timeframe, _ = row
        
        # --- FIX: Unpack condition dict ---
        operator = condition.get("operator", "?")
        value = condition.get("value", "?")
        condition_text = f"{operator} {value}"

        return f"{symbol} {indicator.upper()} {condition_text} ({timeframe})"
    
    else:
        return "Unknown Alert"
            
async def remove_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    alert_type = query.data.split(":")[1]

    # portfolio limits (no ID list)
    if alert_type == "portfoliolimit":
        deleted = delete_portfolio_limit(user_id)
        if deleted:
            await query.edit_message_text("✅ Portfolio Loss Limit removed.")
        else:
            await query.edit_message_text("⚠️ No portfolio loss limit set.")
        return

    if alert_type == "portfoliotarget":
        deleted = delete_portfolio_target(user_id)
        if deleted:
            await query.edit_message_text("✅ Portfolio Profit Target removed.")
        else:
            await query.edit_message_text("⚠️ No portfolio target set.")
        return

    # Alert lists ------------------------------------------
    fetch_map = {
        "price": get_price_alerts,
        "percent": get_percent_alerts,
        "volume": get_volume_alerts,
        "risk": get_risk_alerts,
        "indicator": get_indicator_alerts,
    }

    alerts = fetch_map[alert_type](user_id)

    if not alerts:
        await query.edit_message_text(f"⚠️ No {alert_type} alerts found.")
        return

    keyboard = []

    for a in alerts:
        alert_id = a[0]
        label = format_alert_label(alert_type, a)

        keyboard.append([
            InlineKeyboardButton(
                label,
                callback_data="noop"
            ),
            InlineKeyboardButton(
                "❌ Delete",
                callback_data=f"remove_confirm:{alert_type}:{alert_id}"
            )
        ])

    await query.edit_message_text(
        f"🗑 *Select alert to delete:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    
async def remove_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    _, alert_type, alert_id = query.data.split(":")
    alert_id = int(alert_id)

    delete_map = {
        "price": delete_price_alert,
        "percent": delete_percent_alert,
        "volume": delete_volume_alert,
        "risk": delete_risk_alert,
        "indicator": delete_indicator_alert,
    }

    deleted = delete_map[alert_type](user_id, alert_id)

    if deleted:
        await query.edit_message_text(f"✅ Deleted {alert_type} alert ID {alert_id}.")
    else:
        await query.edit_message_text(f"❌ Could not delete. It may not exist.")
        
from telegram import Update
from telegram.ext import CallbackContext

async def close_menu_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()  # Avoid the “loading” circle
    try:
        await query.message.delete()
    except:
        # Fallback: just edit text to blank if bot can't delete
        await query.edit_message_text("Closed.")
            
from models.alert import (
    get_price_alerts, get_percent_alerts, get_volume_alerts,
    get_risk_alerts, get_indicator_alerts, get_portfolio_value_limits
)
from models.watchlist import get_watchlist_alerts
from models.db import get_connection
from telegram import Update
from telegram.ext import ContextTypes

async def alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    alert_sections = []

    # === PRICE ALERTS ===
    price_rows = get_price_alerts(user_id)
    if price_rows:
        text = "💰 *Price Alerts:*\n"
        for alert_id, symbol, cond, target, repeat in price_rows:
            rep = "🔁" if repeat else ""
            text += f"#P-{alert_id}: {symbol} {cond} {target} {rep}\n→ /remove \n\n"
        alert_sections.append(text)

    # === PERCENT ALERTS ===
    percent_rows = get_percent_alerts(user_id)
    if percent_rows:
        text = "📉 *Percent Alerts:*\n"
        for alert_id, symbol, base, threshold, repeat in percent_rows:
            rep = "🔁" if repeat else ""
            text += f"#%-{alert_id}: {symbol} ±{threshold}% from ${base:.2f} {rep}\n→ /remove \n\n"
        alert_sections.append(text)

    # === VOLUME ALERTS ===
    volume_rows = get_volume_alerts(user_id)
    if volume_rows:
        text = "📊 *Volume Alerts:*\n"
        for alert_id, symbol, tf, mult, repeat in volume_rows:
            rep = "🔁" if repeat else ""
            text += f"#V-{alert_id}: {symbol} volume > {mult}x avg ({tf}) {rep}\n→ /remove \n\n"
        alert_sections.append(text)

    # === RISK ALERTS ===
    risk_rows = get_risk_alerts(user_id)
    if risk_rows:
        text = "🛡 *Risk Alerts (SL/TP):*\n"
        for alert_id, symbol, sl, tp, repeat in risk_rows:
            rep = "🔁" if repeat else ""
            text += f"#R-{alert_id}: {symbol} SL: {sl} / TP: {tp} {rep}\n→ /remove \n\n"
        alert_sections.append(text)

    # === INDICATOR ALERTS ===
    indicator_rows = get_indicator_alerts(user_id)
    if indicator_rows:
        text = "📊 *Indicator Alerts:*\n"
        for row in indicator_rows:
            alert_id, symbol, indicator, condition, timeframe, repeat = row

            rep = "🔁" if repeat else ""

            # Format indicator name for display
            pretty_indicator = indicator.upper()
            
            # --- FIX: Unpack condition dict ---
            operator = condition.get("operator", "?")
            value = condition.get("value", "?")
            condition_text = f"{operator} {value}"

            text += (
                f"#I-{alert_id}: {symbol} {pretty_indicator} {condition_text} [{timeframe}] {rep}\n"
                f"→ /remove \n\n"
            )

        alert_sections.append(text)
    
    from models.alert import get_portfolio_value_limits

    # === PORTFOLIO VALUE LIMITS ===
    limits = get_portfolio_value_limits(user_id)
    if limits:
        text = "🎯 *Portfolio Value Limits:*\n"
    
        # Loss limit
        if limits["loss_limit"] and limits["loss_limit"] > 0:
            repeat_text = " (🔁 Repeat)" if limits.get("repeat_loss") else ""
            text += f"• 🔻 Loss Limit: ${limits['loss_limit']:.2f}{repeat_text}\n→ /remove \n"
    
        # Profit target
        if limits["profit_target"] and limits["profit_target"] > 0:
            repeat_text = " (🔁 Repeat)" if limits.get("repeat_profit") else ""
            text += f"• 🚀 Target: ${limits['profit_target']:.2f}{repeat_text}\n→ /remove \n"
    
        text += "\n"
        alert_sections.append(text)
    
    # === WATCHLIST ENTRIES ===
    watchlist_rows = get_watchlist_alerts(user_id)
    if watchlist_rows:
        text = "🔔 *Watchlist Alerts:*\n"
        for alert_id, symbol, base_price, threshold_percent, timeframe in watchlist_rows:
            text += (
                f"#W-{alert_id}: {symbol} @ {base_price:.2f}, ± {threshold_percent}% ({timeframe})\n"
                f"→ Use `/removewatch {symbol}` to delete\n\n"
            )
        alert_sections.append(text)
    
    # === FINAL OUTPUT ===
    if not alert_sections:
        await update.message.reply_text("📭 You have no active alerts or watchlist items.")
    else:
        output = "*📋 Your Active Alerts:*\n\n" + "\n".join(alert_sections)
        await update.message.reply_text(output, parse_mode="Markdown")
        
from telegram.ext import (
    CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)


async def watch_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    # ✅ Pro-only restriction
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade to unlock.",
            parse_mode="Markdown"
        )
        return

    # ✅ Fetch command arguments
    args = context.args

    if len(args) < 3:
        await update.message.reply_text("❌ Usage: /watch BTC 5 1h")
        return

    symbol = args[0].upper()
    try:
        threshold = float(args[1])
        if threshold <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid threshold. Enter a number greater than 0.")
        return

    timeframe = args[2].lower()
    if timeframe not in ["1h", "4h", "24h", "7d"]:
        await update.message.reply_text("❌ Invalid timeframe. Use one of: 1h, 4h, 24h, 7d")
        return

    # ✅ Await the coroutine properly
    base_prices = await get_crypto_prices(symbol)

    if not base_prices:
        await update.message.reply_text("⚠️ Failed to fetch live price. Try again.")
        return

    # ✅ Handle API response safely
    if isinstance(base_prices, dict):
        base_price = base_prices.get(symbol.upper()) or base_prices.get(f"{symbol.upper()}USDT")
    else:
        base_price = base_prices

    if base_price is None:
        await update.message.reply_text("⚠️ Could not retrieve valid price data. Try again later.")
        return

    # ✅ Save to DB
    from models.db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO watchlist (user_id, symbol, base_price, threshold_percent, timeframe)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, symbol.upper(), float(base_price), threshold, timeframe)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Watching *{symbol}* for ±{threshold}% price move from *${base_price:,.2f}* over `{timeframe}`.",
        parse_mode="Markdown"
    )


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

  
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade to unlock.",
            parse_mode="Markdown"
        )
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT symbol, base_price, threshold_percent, timeframe FROM watchlist WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 You have no active watchlist items.")
        return

    message = "🔍 *Your Watchlist:*\n\n"
    for i, (symbol, price, threshold, tf) in enumerate(rows, start=1):
        message += f"{i}. {symbol} — ±{threshold}% from ${price:.2f} ({tf})\n"

    message += "\nUse `/removewatch <symbol>` to delete an entry."

    await update.message.reply_text(message, parse_mode="Markdown")

async def remove_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("❌ Usage: /removewatch <symbol>\nExample: /removewatch BTC")
        return

    symbol = args[0].upper()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE user_id = ? AND symbol = ?", (user_id, symbol))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted:
        await update.message.reply_text(f"✅ {symbol} removed from your watchlist.")
    else:
        await update.message.reply_text(f"❌ {symbol} is not in your watchlist.")
        

from services.alert_service import delete_all_alerts

async def remove_all_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    delete_all_alerts(user_id)

    await update.message.reply_text("🗑️ All your alerts have been deleted successfully.")
    
async def remove_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_remove"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_remove")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ *Are you sure you want to delete ALL your alerts?*\n"
        "This includes *Price, Percent, Volume, Risk, Indicator, Portfolio,* and *Watchlist* alerts.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return REMOVE_CONFIRM
    
async def remove_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    delete_all_alerts(user_id)

    await query.edit_message_text("✅ All your alerts have been permanently deleted.")
    return ConversationHandler.END

async def remove_all_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Alert deletion cancelled.")
    return ConversationHandler.END
    

    
def register_alert_handlers(app):
    #app.add_handler(CommandHandler("set", set_alert))
    app.add_handler(CommandHandler("alerts", alerts))
    app.add_handler(CommandHandler("watch", watch_coin))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("removewatch", remove_watch))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CallbackQueryHandler(remove_type_handler, pattern=r"^remove:"))
    app.add_handler(CallbackQueryHandler(remove_confirm_handler, pattern=r"^remove_confirm:"))
    app.add_handler(CallbackQueryHandler(close_menu_callback, pattern="^close_menu$"))
    remove_all_conv = ConversationHandler(
        entry_points=[CommandHandler("removeall", remove_all_start)],  # ✅ Only this
        states={
            REMOVE_CONFIRM: [
                CallbackQueryHandler(remove_all_confirm, pattern="^confirm_remove$"),
                CallbackQueryHandler(remove_all_cancel, pattern="^cancel_remove$")
            ]
        },
        fallbacks=[],
        per_message=False  # Recommended unless you're using only CallbackQueryHandler
    )

    app.add_handler(remove_all_conv)  # ✅ Add only this
    