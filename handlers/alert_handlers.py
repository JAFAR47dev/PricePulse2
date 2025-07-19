from telegram import Update
from datetime import datetime
from telegram.ext import ContextTypes
from services.price_service import get_crypto_price
from models.user import get_user_plan
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, CommandHandler
from services.alert_service import delete_all_alerts
from utils.auth import is_pro_plan

# Conversation states for removing alerts
REMOVE_CONFIRM = range(1)

from models.user import can_create_price_alert

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from models.user import get_user_plan
    plan = get_user_plan(user_id)

    args = context.args
    

    if len(args) < 2:
        await update.message.reply_text("❌ Usage:\n/set price BTCUSDT > 70000\n/set percent ETH 5\n/set risk BTC 30000 35000 [repeat]")
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
        await update.message.reply_text("🚫 Advanced alerts are for *Pro users* only.\nUse /upgrade@EliteTradeSignalBot to unlock.", parse_mode="Markdown")
        return

    await handlers[alert_type](update, context, args[1:], plan)
    
async def handle_price_alert(update, context, args, plan):
    if len(args) < 3:
        await update.message.reply_text("❌ Usage: /set price BTCUSDT > 70000 [repeat]")
        return

    user_id = update.effective_user.id
    symbol = args[0].upper()
    condition = args[1]
    try:
        target_price = float(args[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid price format.")
        return

    repeat = 1 if len(args) > 3 and args[3].lower() == "repeat" else 0
    from models.user import get_user_plan

    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    # Enforce daily limit for free plan
    if plan == "free":
        if repeat:
            await update.message.reply_text("🔒 Persistent alerts are Pro-only.")
            return

            
    from models.alert import create_price_alert
    create_price_alert(user_id, symbol, condition, target_price, repeat)

    await update.message.reply_text(f"✅ Price alert set: {symbol} {condition} {target_price}")
    
async def handle_percent_alert(update, context, args, plan):
   
    from models.user import get_user_plan

    user_id = update.effective_user.id
    plan = get_user_plan(user_id)


    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade@EliteTradeSignalBot to unlock.",
            parse_mode="Markdown"
        )
        return

    if len(args) < 2:
        await update.message.reply_text("❌ Usage: /set percent BTCUSDT 5 [repeat]")
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

    base_price = get_crypto_price(symbol)
    if base_price is None:
        await update.message.reply_text("⚠️ Could not fetch current price. Try again later.")
        return

    from models.alert import create_percent_alert
    create_percent_alert(user_id, symbol, base_price, threshold, repeat)

    await update.message.reply_text(
        f"✅ Percent alert set: Notify when *{symbol}* moves ±{threshold}% from ${base_price:.2f}",
        parse_mode="Markdown"
    )
    
async def handle_volume_alert(update, context, args, plan):
    from models.user import get_user_plan

    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    #if plan != "pro":
#        await update.message.reply_text("🔒 This feature is for Pro users. Use /upgrade to unlock.")
#        return
        
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade@EliteTradeSignalBot to unlock.",
            parse_mode="Markdown"
        )
        return
        
   

    if len(args) < 2:
        await update.message.reply_text("❌ Usage: /set volume BTCUSDT 2.5 [repeat]")
        return

    symbol = args[0].upper()

    try:
        multiplier = float(args[1])
        if multiplier <= 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Multiplier must be a number greater than 1 (e.g., 2.5)")
        return

    repeat = 1 if len(args) > 2 and args[2].lower() == "repeat" else 0

    from models.alert import create_volume_alert
    create_volume_alert(user_id, symbol, multiplier, "1h", repeat)

    await update.message.reply_text(
        f"✅ Volume alert set: *{symbol}* spikes above {multiplier}× average volume.",
        parse_mode="Markdown"
    )
    
async def handle_risk_alert(update, context, args, plan):
    from models.user import get_user_plan

    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

   # if plan != "pro":
#        await update.message.reply_text("🔒 This feature is for Pro users. Use /upgrade to unlock.")
#        return
        
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade@EliteTradeSignalBot to unlock.",
            parse_mode="Markdown"
        )
        return

    if len(args) < 3:
        await update.message.reply_text("❌ Usage: /set risk BTCUSDT 30000 35000 [repeat]")
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

    from models.alert import create_risk_alert
    create_risk_alert(user_id, symbol, stop_price, take_price, repeat)

    message = (
        f"✅ Risk alert set for *{symbol}*:\n"
        f"• Stop-Loss: ${stop_price:.2f}\n"
        f"• Take-Profit: ${take_price:.2f}\n"
        f"{'🔁 Repeat enabled' if repeat else ''}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")
    
async def handle_custom_alert(update, context, args, plan):
    from models.user import get_user_plan

    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

   # if plan != "pro":
#        await update.message.reply_text("🔒 This feature is for Pro users. Use /upgrade to unlock.")
#        return
        
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade@EliteTradeSignalBot to unlock.",
            parse_mode="Markdown"
        )
        return

    if len(args) < 4:
        await update.message.reply_text(
            "❌ Usage:\n"
            "/set custom BTCUSDT > 30000 rsi < 30\n"
            "/set custom ETHUSDT < 1800 ema > 20\n"
            "/set custom XRPUSDT > 0.5 macd [repeat]"
        )
        return

    # --- Price condition ---
    symbol = args[0].upper()
    p_cond = args[1]
    try:
        p_val = float(args[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid price value.")
        return

    # --- Indicator condition ---
    remaining = args[3:]
    repeat = 1 if "repeat" in [x.lower() for x in remaining] else 0
    remaining = [x for x in remaining if x.lower() != "repeat"]

    if not remaining:
        await update.message.reply_text("❌ Missing indicator condition.")
        return

    indicator = remaining[0].lower()
    rsi_condition = None
    rsi_value = None

    if indicator == "macd":
        rsi_condition = "macd"
        rsi_value = None

    elif indicator == "rsi":
        if len(remaining) < 3:
            await update.message.reply_text("❌ RSI condition requires a comparison and value.\nExample: rsi < 30")
            return
        rsi_condition = remaining[1]
        try:
            rsi_value = float(remaining[2])
        except ValueError:
            await update.message.reply_text("❌ Invalid RSI value.")
            return

    elif indicator == "ema":
        if len(remaining) < 3 or remaining[1] != ">" or not remaining[2].isdigit():
            await update.message.reply_text("❌ EMA condition must be: ema > 20")
            return
        rsi_condition = f"ema>{remaining[2]}"
        rsi_value = None

    else:
        await update.message.reply_text("❌ Unknown indicator. Use rsi, ema, or macd.")
        return

    # --- Save to database ---
    from models.alert import create_custom_alert
    create_custom_alert(user_id, symbol, p_cond, p_val, rsi_condition, rsi_value, repeat)

    # --- Confirmation message ---
    indicator_name = indicator.upper()

    # Format indicator details
    if indicator == "macd":
        indicator_text = "MACD crossover"
    elif indicator == "rsi":
        indicator_text = f"RSI {rsi_condition} {rsi_value}"
    elif indicator == "ema":
        ema_val = rsi_condition.split(">")[1]
        indicator_text = f"EMA > {ema_val}"
    else:
        indicator_text = rsi_condition  # fallback

    message = (
        f"✅ Custom alert set for *{symbol}*:\n"
        f"• Price: {p_cond} {p_val}\n"
        f"• Indicator: `{indicator_text}`\n"
        f"{'🔁 Repeat enabled' if repeat else ''}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")

from models.alert import (
    delete_price_alert, delete_percent_alert, delete_volume_alert,
    delete_risk_alert, delete_custom_alert,
    delete_portfolio_limit, delete_portfolio_target
)

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "❌ Usage: /remove <type> <ID>\n"
            "Examples:\n"
            "• /remove price 3\n"
            "• /remove custom 12\n"
            "• /remove portfoliolimit\n"
            "• /remove portfoliotarget"
        )
        return

    alert_type = args[0].lower()

    # Handle value-only portfolio removals
    if alert_type in ["portfoliolimit", "portfoliotarget"]:
        if alert_type == "portfoliolimit":
            success = delete_portfolio_limit(user_id)
            label = "Portfolio Loss Limit"
        else:
            success = delete_portfolio_target(user_id)
            label = "Portfolio Profit Target"

        if success:
            await update.message.reply_text(f"✅ {label} removed.")
        else:
            await update.message.reply_text(f"⚠️ {label} was not set.")
        return

    # Handle ID-based removals
    if len(args) < 2:
        await update.message.reply_text("❌ You must specify the alert ID.")
        return

    try:
        alert_id = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Please use a number.")
        return

    delete_funcs = {
        "price": delete_price_alert,
        "percent": delete_percent_alert,
        "volume": delete_volume_alert,
        "risk": delete_risk_alert,
        "custom": delete_custom_alert,
    }

    if alert_type not in delete_funcs:
        await update.message.reply_text("❌ Invalid alert type. Use: price, percent, volume, risk, custom, portfolio, portfoliolimit, portfoliotarget")
        return

    deleted = delete_funcs[alert_type](user_id, alert_id)

    if deleted:
        await update.message.reply_text(f"✅ Removed {alert_type} alert ID {alert_id}.")
    else:
        await update.message.reply_text(f"❌ No {alert_type} alert found with ID {alert_id}, or it doesn't belong to you.")
    
        
from models.alert import (
    get_price_alerts, get_percent_alerts, get_volume_alerts,
    get_risk_alerts, get_custom_alerts, get_portfolio_value_limits
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
            text += f"#P-{alert_id}: {symbol} {cond} {target} {rep}\n→ /remove price {alert_id}\n\n"
        alert_sections.append(text)

    # === PERCENT ALERTS ===
    percent_rows = get_percent_alerts(user_id)
    if percent_rows:
        text = "📉 *Percent Alerts:*\n"
        for alert_id, symbol, base, threshold, repeat in percent_rows:
            rep = "🔁" if repeat else ""
            text += f"#%-{alert_id}: {symbol} ±{threshold}% from ${base:.2f} {rep}\n→ /remove percent {alert_id}\n\n"
        alert_sections.append(text)

    # === VOLUME ALERTS ===
    volume_rows = get_volume_alerts(user_id)
    if volume_rows:
        text = "📊 *Volume Alerts:*\n"
        for alert_id, symbol, tf, mult, repeat in volume_rows:
            rep = "🔁" if repeat else ""
            text += f"#V-{alert_id}: {symbol} volume > {mult}x avg ({tf}) {rep}\n→ /remove volume {alert_id}\n\n"
        alert_sections.append(text)

    # === RISK ALERTS ===
    risk_rows = get_risk_alerts(user_id)
    if risk_rows:
        text = "🛡 *Risk Alerts (SL/TP):*\n"
        for alert_id, symbol, sl, tp, repeat in risk_rows:
            rep = "🔁" if repeat else ""
            text += f"#R-{alert_id}: {symbol} SL: {sl} / TP: {tp} {rep}\n→ /remove risk {alert_id}\n\n"
        alert_sections.append(text)

    # === CUSTOM ALERTS ===
    custom_rows = get_custom_alerts(user_id)
    if custom_rows:
        text = "🧠 *Custom Alerts:*\n"
        for alert_id, symbol, p_cond, p_val, r_cond, r_val, repeat in custom_rows:
            rep = "🔁" if repeat else ""

            # Format indicator part
            if r_cond == "macd":
                indicator_text = "MACD crossover"
            elif r_cond.startswith("ema>"):
                ema_val = r_cond.split(">")[1]
                indicator_text = f"EMA > {ema_val}"
            elif r_cond.lower() in ["<", ">", "<=", ">=", "=", "=="] and r_val is not None:
                indicator_text = f"RSI {r_cond} {r_val}"
            else:
                indicator_text = r_cond.upper()

            text += (
                f"#C-{alert_id}: {symbol} Price {p_cond} {p_val} & {indicator_text} {rep}\n"
                f"→ /remove custom {alert_id}\n\n"
            )
        alert_sections.append(text)

    from models.alert import get_portfolio_value_limits

    # === PORTFOLIO VALUE LIMITS ===
    limits = get_portfolio_value_limits(user_id)
    if limits:
        text = "🎯 *Portfolio Value Limits:*\n"
        if limits["loss_limit"] > 0:
            text += f"• 🔻 Loss Limit: ${limits['loss_limit']:.2f}\n→ /remove portfoliolimit\n"
        if limits["profit_target"] > 0:
            text += f"• 🚀 Target: ${limits['profit_target']:.2f}\n→ /remove portfoliotarget\n"
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
    args = context.args

    plan = get_user_plan(user_id)
    if plan == "free":
        await update.message.reply_text(
            "🔒 /watch is a *Pro-only* feature.\nUpgrade using /upgrade@EliteTradeSignalBot to track coins over time.",
            parse_mode="Markdown"
        )
        return

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

    base_price = get_crypto_price(symbol)
    if base_price is None:
        await update.message.reply_text("⚠️ Failed to fetch live price. Try again.")
        return

    # Save to DB
    from models.db import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO watchlist (user_id, symbol, base_price, threshold_percent, timeframe) VALUES (?, ?, ?, ?, ?)",
        (user_id, symbol, base_price, threshold, timeframe)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Watching *{symbol}* for ±{threshold}% price move from ${base_price:.2f} over `{timeframe}`.",
        parse_mode="Markdown"
    )


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    if plan == "free":
        await update.message.reply_text(
            "🔒 *Pro-only feature.* Upgrade to access your watchlist.\nUse /upgrade@EliteTradeSignalBot to unlock.",
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
        "This includes *Price, Percent, Volume, Risk, Custom, Portfolio,* and *Watchlist* alerts.",
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
    app.add_handler(CommandHandler("set", set_alert))
    app.add_handler(CommandHandler("alerts", alerts))
    app.add_handler(CommandHandler("watch", watch_coin))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("removewatch", remove_watch))
    app.add_handler(CommandHandler("remove", remove))
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
    