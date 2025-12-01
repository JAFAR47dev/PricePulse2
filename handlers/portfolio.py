from telegram import Update
from telegram.ext import ContextTypes
from models.db import get_connection
from utils.auth import is_pro_plan
from models.user import get_user_plan
from utils.prices import get_crypto_prices, get_portfolio_crypto_prices
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
    await update_last_active(user_id, command_name="/addasset")
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
    await update_last_active(user_id, command_name="/portfolio")
    plan = get_user_plan(user_id)

    # --- PRO CHECK ---
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return

    # --- LOAD PORTFOLIO SAFELY ---
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, amount FROM portfolio WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        print("❌ DB ERROR in view_portfolio:", e)
        try:
            await update.message.reply_text("⚠️ Error loading your portfolio. Please try again.")
        except Exception:
            pass
        return

    if not rows:
        await update.message.reply_text("📭 Your portfolio is empty. Add assets using /addasset")
        return

    # Build list of crypto symbols that need API fetching
    crypto_symbols = []
    for symbol, _ in rows:
        s = (symbol or "").upper().strip()
        if s and s not in STABLECOINS and s not in FIAT_CURRENCIES and s != "USD":
            crypto_symbols.append(s)

    # --- FETCH CRYPTO PRICES SAFELY ---
    crypto_data = {}
    if crypto_symbols:
        try:
            crypto_data = await get_portfolio_crypto_prices(crypto_symbols)
            if not isinstance(crypto_data, dict):
                crypto_data = {}
        except Exception as e:
            print("❌ Price fetch error in view_portfolio:", e)
            crypto_data = {}

    # --- BUILD PORTFOLIO MESSAGE WITH CHUNKED SENDING ---
    total_value = 0.0
    total_change_usd = 0.0

    header = "*📊 Your Portfolio (24h Performance):*\n\n"
    buf = header
    MAX_LENGTH = 3500  # safe buffer for Telegram message size

    async def flush_buffer(force=False):
        nonlocal buf
        if not buf:
            return
        try:
            # if buffer is small and not forced, keep accumulating
            if not force and len(buf) < MAX_LENGTH:
                return
            # send current buffer
            await update.message.reply_text(buf, parse_mode="Markdown")
        except Exception as e:
            print("❌ Failed to send portfolio chunk:", e)
            # swallow send errors (we don't want to crash)
        finally:
            buf = ""  # reset buffer after sending

    for symbol, amount in rows:
        symbol = (symbol or "").upper().strip()

        # --- Determine source: stablecoin / fiat / crypto ---
        price = None
        pct_change_24h = None

        if symbol in STABLECOINS or symbol == "USD":
            price = 1.0
            pct_change_24h = 0.0
        elif symbol in FIAT_CURRENCIES:
            try:
                price = get_fiat_to_usd(symbol)
            except Exception as e:
                print(f"❌ Fiat conversion error for {symbol}:", e)
                price = None
            pct_change_24h = 0.0
        else:
            data = crypto_data.get(symbol) or {}
            # expect structure {"price": float|None, "change_pct": float|None}
            price = data.get("price")
            pct_change_24h = data.get("change_pct")

        # Formatting for missing price
        if price is None:
            buf += f"• *{symbol}*: {amount} (⚠️ Price unavailable)\n\n"
            # flush if too long
            if len(buf) >= MAX_LENGTH:
                await flush_buffer(force=True)
            continue

        # --- Current USD value ---
        try:
            value = float(amount) * float(price)
        except Exception:
            value = 0.0

        total_value += value

        # --- Compute USD change for this asset ---
        asset_change_usd = None
        if pct_change_24h is None:
            asset_change_usd = None
        else:
            try:
                asset_change_usd = value * (float(pct_change_24h) / 100.0)
                total_change_usd += asset_change_usd
            except Exception:
                asset_change_usd = None

        # --- Text formatting with emojis ---
        if pct_change_24h is None:
            pct_text = "⚠️ N/A"
        else:
            try:
                pct_val = float(pct_change_24h)
                if pct_val > 0:
                    pct_text = f"🟢 +{pct_val:.2f}%"
                elif pct_val < 0:
                    pct_text = f"🔴 {pct_val:.2f}%"
                else:
                    pct_text = "➖ 0%"
            except Exception:
                pct_text = "⚠️ N/A"

        if asset_change_usd is None:
            change_usd_text = "⚠️ N/A"
        else:
            if asset_change_usd > 0:
                change_usd_text = f"🟢 +${asset_change_usd:,.2f}"
            elif asset_change_usd < 0:
                change_usd_text = f"🔴 -${abs(asset_change_usd):,.2f}"
            else:
                change_usd_text = "➖ $0"

        # Per-asset line
        # Price formatting: show 4 decimals for small coins, 2 for big ones
        try:
            price_display = f"${price:,.4f}" if price < 1 else f"${price:,.2f}"
        except Exception:
            price_display = f"${price}"

        buf += (
            f"• *{symbol}*: {amount}\n"
            f"  ↳ {price_display} each → *${value:,.2f}*\n"
            f"  ↳ 24h: {pct_text} | {change_usd_text}\n\n"
        )

        # send chunk if buffer too large
        if len(buf) >= MAX_LENGTH:
            await flush_buffer(force=True)

async def remove_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/removeasset")
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
    await update_last_active(user_id, command_name="/clearportfolio")
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
    await update_last_active(user_id, command_name="/portfoliolimit")
    plan = get_user_plan(user_id)

    # --- PRO CHECK ---
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return

    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Usage: `/portfoliolimit [amount] [repeat]`\n"
            "Example: `/portfoliolimit 15000 repeat`",
            parse_mode="Markdown"
        )
        return

    # --- EXTRACT AMOUNT ---
    raw_amount = context.args[0].replace(",", "")
    try:
        amount = float(raw_amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number greater than 0.")
        return

    # --- CHECK FOR 'repeat' KEYWORD ---
    repeat_flag = 1 if (len(context.args) > 1 and context.args[1].lower() == "repeat") else 0

    # --- SAVE TO DATABASE ---
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT OR IGNORE INTO portfolio_limits (user_id) VALUES (?)", (user_id,))

    cursor.execute("""
        UPDATE portfolio_limits
        SET loss_limit = ?, repeat_limit_loss = ?
        WHERE user_id = ?
    """, (amount, repeat_flag, user_id))

    conn.commit()
    conn.close()

    # --- RESPONSE ---
    if repeat_flag:
        repeat_text = "🔁 *Repeating alert enabled* — you'll get alerted every time it drops below this level."
    else:
        repeat_text = "🔔 (One-time alert — it will not repeat.)"

    await update.message.reply_text(
        f"✅ Portfolio *loss alert* set!\n"
        f"📉 Trigger at: *${amount:,.2f}*\n\n"
        f"{repeat_text}",
        parse_mode="Markdown"
    )
    

async def set_portfolio_profit_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/portfoliotarget")
    plan = get_user_plan(user_id)

    # --- PRO CHECK ---
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*. Use /upgrade to unlock full portfolio tools.",
            parse_mode="Markdown"
        )
        return

    # --- ARG CHECK ---
    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Usage: `/portfoliotarget [amount] [repeat]`\n"
            "Example: `/portfoliotarget 30000 repeat`",
            parse_mode="Markdown"
        )
        return

    # --- PARSE AMOUNT ---
    raw_amount = context.args[0].replace(",", "")
    try:
        amount = float(raw_amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number greater than 0.")
        return

    # --- REPEAT FLAG ---
    repeat_flag = 1 if (len(context.args) > 1 and context.args[1].lower() == "repeat") else 0

    # --- SAVE TO DATABASE ---
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT OR IGNORE INTO portfolio_limits (user_id) VALUES (?)", (user_id,))

    cursor.execute("""
        UPDATE portfolio_limits
        SET profit_target = ?, repeat_limit_profit = ?
        WHERE user_id = ?
    """, (amount, repeat_flag, user_id))

    conn.commit()
    conn.close()

    # --- USER FEEDBACK ---
    if repeat_flag:
        repeat_text = "🔁 *Repeating alert enabled* — you'll be alerted every time your portfolio exceeds this value."
    else:
        repeat_text = "🔔 (One-time alert — it will not repeat.)"

    await update.message.reply_text(
        f"✅ Portfolio *profit alert* set!\n"
        f"📈 Trigger at: *${amount:,.2f}*\n\n"
        f"{repeat_text}",
        parse_mode="Markdown"
    )