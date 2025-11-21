from telegram import Update
from telegram.ext import ContextTypes
from models.db import get_connection
from utils.auth import is_pro_plan
from models.user import get_user_plan
from utils.prices import get_portfolio_crypto_prices, get_crypto_prices
import os
import requests
from models.user_activity import update_last_active

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

# Stablecoins map (you can expand this)
STABLECOINS = {"USDT", "USDC", "DAI", "TUSD", "BUSD"}

# Common fiat currencies (for validation)
FIAT_CURRENCIES = {"USD", "EUR", "GBP", "NGN", "JPY", "CAD", "AUD", "CHF"}

def get_fiat_to_usd(symbol):
    try:
        if symbol == "USD":
            return 1.0
        url = (
            f"https://www.alphavantage.co/query"
            f"?function=CURRENCY_EXCHANGE_RATE"
            f"&from_currency={symbol}&to_currency=USD"
            f"&apikey={ALPHA_VANTAGE_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        data = response.json()
        rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        return rate
    except Exception as e:
        print("❌ Fiat conversion error:", e)
        return None
        
        

async def add_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ Usage: /addasset BTC 1.2")
        return

    symbol = args[0].upper()
    try:
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Use a number like 1.2")
        return

    # Validate or convert symbol
    if symbol in STABLECOINS or symbol == "USD":
        price_in_usd = 1.0
    elif symbol in FIAT_CURRENCIES:
        price_in_usd = get_fiat_to_usd(symbol)
        if price_in_usd is None:
            await update.message.reply_text("❌ Failed to get live exchange rate. Try again.")
            return
    else:
        # ✅ Await the async function and unpack result
        result = await get_crypto_prices([symbol])
        price_in_usd = result.get(symbol)

        if not price_in_usd:
            await update.message.reply_text("❌ Failed to fetch live crypto price.")
            return

    # Save asset (amount in symbol units)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO portfolio (user_id, symbol, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, symbol) DO UPDATE SET amount = amount + excluded.amount
    """, (user_id, symbol, amount))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Added *{amount} {symbol}* to your portfolio. (1 {symbol} ≈ ${price_in_usd:.2f})",
        parse_mode="Markdown"
    )

    
async def view_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT symbol, amount FROM portfolio WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 Your portfolio is empty. Add assets using /addasset")
        return

    total_value = 0
    total_change_usd = 0

    message = "*📊 Your Portfolio (24h Performance):*\n\n"

    # Collect symbols for bulk fetching
    crypto_symbols = [
        symbol.upper()
        for symbol, _ in rows
        if symbol not in STABLECOINS and symbol not in FIAT_CURRENCIES and symbol != "USD"
    ]

    # Fetch crypto data once
    crypto_data = await get_portfolio_crypto_prices(crypto_symbols) if crypto_symbols else {}

    for symbol, amount in rows:
        symbol = symbol.upper()

        # Determine source
        if symbol in STABLECOINS or symbol == "USD":
            price = 1.0
            pct_change_24h = 0
            change_amt_24h = 0
        elif symbol in FIAT_CURRENCIES:
            price = get_fiat_to_usd(symbol)
            pct_change_24h = 0
            change_amt_24h = 0
        else:
            data = crypto_data.get(symbol, {})
            price = data.get("price")
            pct_change_24h = data.get("change_pct")
            change_amt_24h = data.get("change_amt")  # already price * pct/100

        if price is None:
            message += f"• *{symbol}*: {amount} (⚠️ Price unavailable)\n"
            continue

        # Current value
        value = amount * price
        total_value += value

        # Compute USD change for this asset
        if pct_change_24h is None:
            asset_change_usd = None
        else:
            asset_change_usd = value * (pct_change_24h / 100)
            total_change_usd += asset_change_usd

        # Percent emoji
        if pct_change_24h is None:
            pct_text = "⚠️ N/A"
        elif pct_change_24h > 0:
            pct_text = f"🟢 +{pct_change_24h:.2f}%"
        elif pct_change_24h < 0:
            pct_text = f"🔴 {pct_change_24h:.2f}%"
        else:
            pct_text = "➖ 0%"

        # USD emoji
        if asset_change_usd is None:
            change_usd_text = "⚠️ N/A"
        elif asset_change_usd > 0:
            change_usd_text = f"🟢 +${asset_change_usd:,.2f}"
        elif asset_change_usd < 0:
            change_usd_text = f"🔴 -${abs(asset_change_usd):,.2f}"
        else:
            change_usd_text = "➖ $0"

        # Build message
        message += (
            f"• *{symbol}*: {amount}\n"
            f"  ↳ ${price:.2f} each → *${value:,.2f}*\n"
            f"  ↳ 24h: {pct_text} | {change_usd_text}\n\n"
        )

    # Portfolio-wide 24h % change
    if total_value == 0:
        summary_pct = 0
    else:
        summary_pct = (total_change_usd / (total_value - total_change_usd)) * 100 if (total_value - total_change_usd) != 0 else 0

    if summary_pct > 0:
        summary_pct_text = f"🟢 +{summary_pct:.2f}%"
    elif summary_pct < 0:
        summary_pct_text = f"🔴 {summary_pct:.2f}%"
    else:
        summary_pct_text = "➖ 0%"

    total_change_text = (
        f"🟢 +${total_change_usd:,.2f}" if total_change_usd > 0 else
        f"🔴 -${abs(total_change_usd):,.2f}" if total_change_usd < 0 else "➖ $0"
    )

    message += (
        f"*💰 Total Value:* ${total_value:,.2f}\n"
        f"*📈 24h Change:* {summary_pct_text} ({total_change_text})"
    )

    await update.message.reply_text(message, parse_mode="Markdown")
    

    await update.message.reply_text(message, parse_mode="Markdown")
      

async def remove_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return
        
    args = context.args

    if len(args) < 1:
        await update.message.reply_text(
            "❌ Usage: /removeasset [symbol] [amount(optional)]\nExamples:\n"
            "• /removeasset BTC\n"
            "• /removeasset BTC 1.5"
        )
        return

    symbol = args[0].upper()
    amount = None

    # Optional: Validate symbol format (optional)
    if not symbol.isalpha():
        await update.message.reply_text("❌ Invalid symbol.")
        return

    # Parse optional amount
    if len(args) >= 2:
        try:
            amount = float(args[1])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Use a number like 1.5", parse_mode="Markdown")
            return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT amount FROM portfolio WHERE user_id = ? AND symbol = ?", (user_id, symbol))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text(f"⚠️ You don't have any *{symbol}* in your portfolio.", parse_mode="Markdown")
        conn.close()
        return

    current_amount = row[0]

    if amount is None or amount >= current_amount:
        cursor.execute("DELETE FROM portfolio WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        msg = f"🗑 Removed *{symbol}* completely from your portfolio."
    else:
        new_amount = current_amount - amount
        cursor.execute(
            "UPDATE portfolio SET amount = ? WHERE user_id = ? AND symbol = ?",
            (new_amount, user_id, symbol)
        )
        msg = f"✅ Updated *{symbol}* to {new_amount} units."

    conn.commit()
    conn.close()

    await update.message.reply_text(msg, parse_mode="Markdown")
    
async def clear_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM portfolio WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]

    if count == 0:
        await update.message.reply_text("📭 Your portfolio is already empty.")
        conn.close()
        return

    cursor.execute("DELETE FROM portfolio WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text("🧹 All your portfolio assets have been removed.")
    

async def set_portfolio_loss_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return
    

    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Usage: `/portfoliolimit [amount]`\nExample: `/portfoliolimit 15000`",
            parse_mode="Markdown"
        )
        return

    try:
        amount = float(context.args[0].replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number greater than 0.")
        return

    # Set or update the limit
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO portfolio_limits (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE portfolio_limits SET loss_limit = ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Portfolio *loss alert* set!\nYou'll be notified if your portfolio drops below *${amount:,.2f}*.",
        parse_mode="Markdown"
    )

async def set_portfolio_profit_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Usage: `/portfoliotarget [amount]`\nExample: `/portfoliotarget 30000`",
            parse_mode="Markdown"
        )
        return

    try:
        amount = float(context.args[0].replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number greater than 0.")
        return

    # Save to database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO portfolio_limits (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE portfolio_limits SET profit_target = ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Portfolio *profit alert* set!\nYou'll be notified if your portfolio exceeds *${amount:,.2f}*.",
        parse_mode="Markdown"
    )