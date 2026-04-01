from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
import os
from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta
from config import ADMIN_ID
from tasks.handlers import handle_streak
from models.user_activity import update_last_active
from models.db import get_connection

load_dotenv()

# ============================================================================
# DYNAMIC URGENCY COUNTER
# ============================================================================

def get_pro_user_count() -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE plan LIKE 'pro%'")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"❌ Error getting pro user count: {e}")
        return 0


def get_urgency_message() -> tuple:
    pro_count = get_pro_user_count()
    remaining = max(0, 100 - pro_count)

    if remaining <= 10:
        return f"*LAST {remaining} SPOTS!* Price increases soon!", "🔥", "CRITICAL"
    elif remaining <= 25:
        return f"*ONLY {remaining} SPOTS LEFT* at founder pricing!", "⚠️", "HIGH"
    elif remaining <= 50:
        return f"*{remaining} spots remaining* before price increase", "⏰", "MEDIUM"
    else:
        return f"{remaining}/100 founder spots available", "📊", "LOW"


def calculate_new_expiry(user_id: int, new_plan: str, stack: bool = True):
    """Returns new expiry datetime, or None for lifetime."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan, expiry_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    current_plan   = row[0].lower() if row and row[0] else "free"
    current_expiry = row[1] if row and row[1] else None

    current_expiry_dt = None
    if current_expiry:
        try:
            current_expiry_dt = (
                datetime.fromisoformat(current_expiry)
                if isinstance(current_expiry, str)
                else current_expiry
            )
        except Exception as e:
            print(f"⚠️ Error parsing expiry: {e}")

    now = datetime.utcnow()
    if stack and current_plan.startswith("pro_") and current_expiry_dt and current_expiry_dt > now:
        start_date = current_expiry_dt
    else:
        start_date = now

    if new_plan == "monthly":
        return start_date + timedelta(days=30)
    elif new_plan == "yearly":
        return start_date + timedelta(days=365)
    elif new_plan == "lifetime":
        return None
    else:
        raise ValueError(f"Invalid plan type: {new_plan}")


def _get_current_plan_info(user_id: int) -> tuple:
    """Returns (current_plan, current_expiry_dt, remaining_days)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan, expiry_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    current_plan   = row[0].lower() if row and row[0] else "free"
    current_expiry = row[1] if row and row[1] else None

    current_expiry_dt = None
    remaining_days    = 0
    if current_expiry:
        try:
            current_expiry_dt = (
                datetime.fromisoformat(current_expiry)
                if isinstance(current_expiry, str)
                else current_expiry
            )
            if current_expiry_dt > datetime.utcnow():
                remaining_days = (current_expiry_dt - datetime.utcnow()).days
        except Exception as e:
            print(f"⚠️ Error parsing expiry: {e}")

    return current_plan, current_expiry_dt, remaining_days


# ============================================================================
# PRICING
# ============================================================================

USD_PRICES     = {"monthly": 7.99,  "yearly": 59,   "lifetime": 149}
FUTURE_PRICES  = {"monthly": 14.99, "yearly": 99,   "lifetime": 299}
STARS_PRICES   = {"monthly": 600,   "yearly": 4500, "lifetime": 11500}

CRYPTO_DETAILS = {
    "usdt": {"name": "USDT (TRC20)", "wallet": "TCvaGAp7UrMHwwzMH9jLukL9BbAGq39iLX",              "id": "tether"},
    "ton":  {"name": "TON",          "wallet": "UQDgqP7E0jzxoLFrSHVJiq6E4o4RZu3tdtHLPOEfyq0XMEyE", "id": "the-open-network"},
    "btc":  {"name": "Bitcoin (BTC)","wallet": "14i5aBLB8yWh5gnApYUTaMAvPKukR6BqCM",              "id": "bitcoin"},
}

PLAN_LABELS = {
    "monthly":  "Monthly Pro",
    "yearly":   "Yearly Pro",
    "lifetime": "Lifetime Pro",
}

PLAN_HIERARCHY = {"free": 0, "pro_monthly": 1, "pro_yearly": 2, "pro_lifetime": 3}

VALID_PLANS  = set(USD_PRICES.keys())
VALID_CRYPTO = set(CRYPTO_DETAILS.keys())


# ============================================================================
# STEP 1 — UPGRADE MENU
# ============================================================================

async def upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/upgrade")
    await handle_streak(update, context)

    urgency_text, urgency_emoji, intensity = get_urgency_message()
    pro_count = get_pro_user_count()
    remaining = max(0, 100 - pro_count)

    monthly_savings  = FUTURE_PRICES["monthly"]  - USD_PRICES["monthly"]
    yearly_savings   = FUTURE_PRICES["yearly"]   - USD_PRICES["yearly"]
    lifetime_savings = FUTURE_PRICES["lifetime"] - USD_PRICES["lifetime"]

    filled_bars  = int((min(pro_count, 100) / 100) * 20)
    progress_bar = "█" * filled_bars + "░" * (20 - filled_bars)

    # FIX: Removed ~~strikethrough~~ — not supported in Markdown mode,
    # renders as literal tildes. Using [was $X] notation instead.
    text = (
        f"💎 *Pro Plan — Advanced Tools for Serious Traders*\n\n"
        f"Upgrade to unlock:\n"
        f"🔔 Unlimited alerts (price, %, volume, indicators)\n"
        f"📊 Multi-timeframe AI analysis\n"
        f"🧠 Strategy backtesting & trade setup analysis\n"
        f"💼 Advanced risk tools & portfolio controls\n"
        f"👁️ Large watchlists & market scanning\n\n"
        f"Everything in one chat. No switching tools.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{urgency_emoji} *EARLY ADOPTER PRICING*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{urgency_emoji} *{urgency_text}*\n\n"
        f"📊 *Founder Member Progress:*\n"
        f"`{progress_bar}` {pro_count}/100\n\n"
        f"⏰ *What happens after spot #100:*\n"
        f"• Prices increase 50-100%\n"
        f"• Lock in the longest plan now to maximise savings\n\n"
        f"💰 *Current Pricing:*\n"
        f"• Monthly: *${USD_PRICES['monthly']}* [was ${FUTURE_PRICES['monthly']}] "
        f"/ *{STARS_PRICES['monthly']} ⭐*\n"
        f"• Yearly:  *${USD_PRICES['yearly']}* [was ${FUTURE_PRICES['yearly']}] "
        f"/ *{STARS_PRICES['yearly']} ⭐*\n"
        f"• Lifetime: *${USD_PRICES['lifetime']}* [was ${FUTURE_PRICES['lifetime']}] "
        f"/ *{STARS_PRICES['lifetime']} ⭐*\n\n"
        f"⚡ *Join now, pay less. Let it expire, pay full price.*\n\n"
        f"*Choose your plan 👇*"
    )

    if remaining <= 10:
        monthly_btn  = f"🔥 Monthly — ${USD_PRICES['monthly']} (LAST {remaining}!)"
        yearly_btn   = f"🔥 Yearly — ${USD_PRICES['yearly']} (LAST {remaining}!)"
        lifetime_btn = f"🔥 Lifetime — ${USD_PRICES['lifetime']} (LAST {remaining}!)"
    elif remaining <= 25:
        monthly_btn  = f"⚠️ Monthly — ${USD_PRICES['monthly']} ({remaining} left)"
        yearly_btn   = f"⚠️ Yearly — ${USD_PRICES['yearly']} ({remaining} left)"
        lifetime_btn = f"⚠️ Lifetime — ${USD_PRICES['lifetime']} ({remaining} left)"
    else:
        monthly_btn  = f"📆 Monthly — ${USD_PRICES['monthly']}"
        yearly_btn   = f"📅 Yearly — ${USD_PRICES['yearly']}"
        lifetime_btn = f"♾️ Lifetime — ${USD_PRICES['lifetime']}"

    keyboard = [
        [InlineKeyboardButton(monthly_btn,  callback_data="plan_monthly")],
        [InlineKeyboardButton(yearly_btn,   callback_data="plan_yearly")],
        [InlineKeyboardButton(lifetime_btn, callback_data="plan_lifetime")],
    ]

    if update.message:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )


# ============================================================================
# STEP 2 — PLAN SELECTED → SHOW PAYMENT METHODS
# FIX: Added guard so unexpected callback_data never causes a KeyError
# ============================================================================

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # FIX: Validate plan before touching STARS_PRICES
    plan = query.data.replace("plan_", "")
    if plan not in VALID_PLANS:
        await query.answer("⚠️ Invalid selection.", show_alert=True)
        return

    context.user_data["selected_plan"] = plan
    urgency_text, urgency_emoji, _      = get_urgency_message()
    stars = STARS_PRICES[plan]
    usd   = USD_PRICES[plan]

    keyboard = [
        [InlineKeyboardButton(
            f"⭐ Pay with Stars ({stars} ⭐) — Instant",
            callback_data=f"stars_{plan}"        # FIX: dedicated prefix, not pay_
        )],
        [InlineKeyboardButton("💵 USDT (TRC20)", callback_data=f"crypto_{plan}_usdt")],
        [InlineKeyboardButton("🪙 TON",           callback_data=f"crypto_{plan}_ton")],
        [InlineKeyboardButton("₿ Bitcoin",        callback_data=f"crypto_{plan}_btc")],
        [InlineKeyboardButton("🔙 Back",           callback_data="back_to_plans")],
    ]

    await query.edit_message_text(
        text=(
            f"💳 *{PLAN_LABELS[plan]} — ${usd} / {stars} ⭐*\n\n"
            f"{urgency_emoji} {urgency_text}\n\n"
            f"⭐ *Stars* — instant activation, no wallet needed\n"
            f"🔐 *Crypto* — manual verification (up to 24h)\n\n"
            f"Choose how you'd like to pay:"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ============================================================================
# STEP 3a — STARS INVOICE
# FIX: Uses dedicated "stars_{plan}" prefix to avoid routing collision
# FIX: Edits the original message so dead buttons can't be pressed again
# ============================================================================

async def show_stars_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan = query.data.replace("stars_", "")
    if plan not in VALID_PLANS:
        await query.answer("⚠️ Invalid plan.", show_alert=True)
        return

    context.user_data["selected_plan"] = plan
    stars = STARS_PRICES[plan]
    label = PLAN_LABELS[plan]

    # FIX: Edit message FIRST so the payment method buttons become inactive
    # while the invoice is open. Prevents double-tapping.
    await query.edit_message_text(
        f"⭐ *{label} — {stars} Stars*\n\n"
        f"An invoice has been sent below \n"
        f"Complete the payment there to activate Pro instantly.\n\n"
        f"_Changed your mind? Use /upgrade to start over._",
        parse_mode="Markdown"
    )

    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title=f"PricePulseBot — {label}",
        description=(
            "Unlock full Pro access: unlimited alerts, AI analysis, "
            "multi-coin screener, risk tools & more."
        ),
        payload=f"stars_{plan}_{query.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=stars)],
    )


# ============================================================================
# PRE-CHECKOUT — Telegram calls this before charging
# Must respond within 10 seconds
# ============================================================================

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    parts = query.invoice_payload.split("_")

    # payload format: stars_{plan}_{user_id}
    if len(parts) != 3 or parts[0] != "stars":
        await query.answer(ok=False, error_message="Invalid payment payload.")
        return

    plan    = parts[1]
    user_id = int(parts[2])

    if user_id != query.from_user.id:
        await query.answer(ok=False, error_message="Payment user mismatch.")
        return

    if plan not in STARS_PRICES:
        await query.answer(ok=False, error_message="Invalid plan.")
        return

    await query.answer(ok=True)


# ============================================================================
# SUCCESSFUL PAYMENT — auto-activates Pro immediately
# FIX: Calculate expiry once, reuse for both DB write and display
# FIX: Uses INSERT OR REPLACE so new users without a DB row get activated too
# ============================================================================

async def handle_stars_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    user    = update.effective_user

    parts = payment.invoice_payload.split("_")
    plan  = parts[1]

    # FIX: Calculate expiry ONCE and pass to both _activate_pro and display
    new_expiry = calculate_new_expiry(user_id, plan, stack=False)
    _activate_pro(user_id, plan, new_expiry)

    stars_charged = payment.total_amount

    if new_expiry:
        expiry_str = new_expiry.strftime("%Y-%m-%d")
        days_str   = str((new_expiry - datetime.utcnow()).days)
    else:
        expiry_str = "Never (Lifetime)"
        days_str   = "∞"

    await update.message.reply_text(
        f"🎉 <b>Payment Confirmed — You're now Pro!</b>\n\n"
        f"⭐ Stars charged : <b>{stars_charged}</b>\n"
        f"📦 Plan          : <b>{PLAN_LABELS[plan]}</b>\n"
        f"📅 Active until  : <code>{expiry_str}</code>\n"
        f"⏳ Duration      : <b>{days_str} days</b>\n\n"
        f"✅ Full access is live right now. Enjoy!\n\n"
        f"Use /menu to explore all Pro features.",
        parse_mode="HTML"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"⭐ <b>Stars Payment Received</b>\n\n"
                f"👤 User  : <a href='tg://user?id={user_id}'>{user.full_name}</a> "
                f"(<code>{user_id}</code>)\n"
                f"📦 Plan  : {PLAN_LABELS[plan]}\n"
                f"⭐ Stars : {stars_charged}\n"
                f"📅 Until : {expiry_str}\n\n"
                f"✅ Auto-activated — no action needed."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ Failed to notify admin of Stars payment: {e}")


def _activate_pro(user_id: int, plan: str, new_expiry) -> None:
    """
    FIX: Uses INSERT OR REPLACE (upsert) so brand-new users with no row
    in the users table still get activated. Previously UPDATE silently
    affected 0 rows for new users and they never got Pro access.
    """
    expiry_str = new_expiry.isoformat() if new_expiry else None

    conn   = get_connection()
    cursor = conn.cursor()

    # Check if user row exists
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()

    if exists:
        cursor.execute(
            "UPDATE users SET plan = ?, expiry_date = ? WHERE user_id = ?",
            (f"pro_{plan}", expiry_str, user_id)
        )
    else:
        # New user — insert minimal row with Pro plan
        cursor.execute(
            "INSERT INTO users (user_id, plan, expiry_date) VALUES (?, ?, ?)",
            (user_id, f"pro_{plan}", expiry_str)
        )

    conn.commit()
    conn.close()
    print(f"[upgrade] ✅ Activated pro_{plan} for user {user_id} until {expiry_str}")


# ============================================================================
# STEP 3b — CRYPTO PAYMENT
# FIX: Uses "crypto_{plan}_{coin}" prefix instead of "pay_{plan}_{coin}"
#      to avoid any routing ambiguity
# ============================================================================

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")


def get_live_price_usd(coin_id: str):
    try:
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin_id}&vs_currencies=usd&x_cg_demo_api_key={COINGECKO_API_KEY}"
        )
        response = requests.get(url, timeout=20)
        return response.json()[coin_id]["usd"]
    except Exception as e:
        print("❌ Error fetching live price:", e)
        return None


def calculate_live_crypto_amount(crypto: str, plan: str):
    usd     = USD_PRICES[plan]
    coin_id = CRYPTO_DETAILS[crypto]["id"]
    price   = get_live_price_usd(coin_id)
    return round(usd / price, 6) if price else None


async def show_payment_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # FIX: Updated to match new "crypto_{plan}_{coin}" prefix
    data  = query.data.replace("crypto_", "")

    # data is now "monthly_usdt", "yearly_btc" etc.
    # rsplit from right in case plan name ever changes
    parts = data.split("_")
    if len(parts) != 2 or parts[0] not in VALID_PLANS or parts[1] not in VALID_CRYPTO:
        await query.answer("⚠️ Invalid selection.", show_alert=True)
        return

    plan, crypto = parts
    context.user_data["selected_plan"]   = plan
    context.user_data["selected_crypto"] = crypto

    live_amount = calculate_live_crypto_amount(crypto, plan)
    if not live_amount:
        await query.edit_message_text(
            "⚠️ Failed to fetch live price. Please try again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Retry", callback_data=f"crypto_{plan}_{crypto}"),
                InlineKeyboardButton("⬅ Back",  callback_data=f"plan_{plan}"),
            ]])
        )
        return

    crypto_info                      = CRYPTO_DETAILS[crypto]
    urgency_text, urgency_emoji, _   = get_urgency_message()

    text = (
        f"💼 *Upgrade to {PLAN_LABELS[plan]}*\n"
        f"💲 Price: ${USD_PRICES[plan]} USD\n"
        f"🪙 Pay with: *{crypto_info['name']}*\n\n"
        f"{urgency_emoji} {urgency_text}\n\n"
        f"📥 *Amount to Pay:* `{live_amount} {crypto.upper()}` _(Live Rate)_\n"
        f"🏦 *Wallet Address:*\n`{crypto_info['wallet']}`\n\n"
        f"🔄 After payment press ✅ below to notify us.\n"
        f"⏳ Activation within 24 hours after verification."
    )

    keyboard = [
        [InlineKeyboardButton("✅ I've Paid", callback_data=f"confirm_{plan}_{crypto}")],
        # FIX: Back button now routes to plan_{plan} which hits handle_plan_selection
        # Previously routed to back_to_crypto_{plan} which had no handler → dead button
        [InlineKeyboardButton("⬅ Back",       callback_data=f"plan_{plan}")],
    ]
    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================================
# STEP 4 — CRYPTO CONFIRMATION (manual verification)
# ============================================================================

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        user    = query.from_user
        user_id = user.id
        data    = query.data.replace("confirm_", "")
        parts   = data.split("_")

        if len(parts) != 2 or parts[0] not in VALID_PLANS or parts[1] not in VALID_CRYPTO:
            await query.edit_message_text("⚠️ Invalid confirmation data. Please try again.")
            return

        plan, crypto = parts

        current_plan, current_expiry_dt, remaining_days = _get_current_plan_info(user_id)
        requested_plan = f"pro_{plan}"

        # Duplicate plan check
        if current_plan == requested_plan and remaining_days > 0:
            await query.edit_message_text(
                f"⚠️ <b>You Already Have This Plan!</b>\n\n"
                f"📦 Current: <b>{current_plan.replace('pro_', '').capitalize()}</b>\n"
                f"📅 Expires: <code>{current_expiry_dt.strftime('%Y-%m-%d')}</code>\n"
                f"⏳ Remaining: <b>{remaining_days} days</b>\n\n"
                f"Wait until expiry or upgrade to a longer plan.",
                parse_mode="HTML"
            )
            return

        # Lifetime check
        if current_plan == "pro_lifetime":
            await query.edit_message_text(
                "👑 <b>You Have Lifetime Access!</b>\n\n"
                "♾️ You already have full access forever — no payment needed.",
                parse_mode="HTML"
            )
            return

        # Downgrade check
        if (PLAN_HIERARCHY.get(requested_plan, 0) < PLAN_HIERARCHY.get(current_plan, 0)
                and remaining_days > 0):
            await query.edit_message_text(
                f"⚠️ <b>Downgrade Detected</b>\n\n"
                f"You can't downgrade while your {current_plan.replace('pro_', '')} "
                f"plan is active ({remaining_days} days left).",
                parse_mode="HTML"
            )
            return

        # Valid — notify admin and user
        timestamp   = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        user_name   = user.full_name or user.username or "Unknown"
        crypto_name = CRYPTO_DETAILS[crypto]["name"]
        usd_value   = USD_PRICES[plan]

        new_expiry = calculate_new_expiry(user_id, plan, stack=True)
        if new_expiry:
            expiry_display = new_expiry.strftime("%Y-%m-%d")
            days_until     = (new_expiry - datetime.utcnow()).days
        else:
            expiry_display = "Never (Lifetime)"
            days_until     = "∞"

        urgency_text, urgency_emoji, _ = get_urgency_message()

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🛎 <b>Crypto Payment Submitted</b>\n\n"
                    f"👤 User   : <a href='tg://user?id={user_id}'>{user_name}</a> "
                    f"(<code>{user_id}</code>)\n"
                    f"📦 Plan   : {PLAN_LABELS[plan]} (${usd_value})\n"
                    f"💱 Crypto : {crypto_name}\n"
                    f"🕒 Time   : {timestamp}\n\n"
                    f"📅 Expiry : <code>{expiry_display}</code>\n"
                    f"⏳ Days   : {days_until}\n\n"
                    f"✅ Activate: <code>/setplan {user_id} pro_{plan}</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"❌ Failed to notify admin: {e}")

        if plan == "lifetime":
            user_message = (
                "✅ <b>Payment Confirmation Submitted</b>\n\n"
                "🎉 Your account will be upgraded to <b>Lifetime Pro</b> within 24 hours.\n"
                "♾️ Full access forever once verified."
            )
        elif current_plan != "free" and remaining_days > 0:
            user_message = (
                f"✅ <b>Payment Confirmation Submitted</b>\n\n"
                f"🔄 <b>Upgrade Details:</b>\n"
                f"• Previous: {current_plan.replace('pro_', '').capitalize()} "
                f"({remaining_days} days left)\n"
                f"• New plan: {PLAN_LABELS[plan]}\n"
                f"• Total time: <b>{days_until} days</b>\n\n"
                f"📅 New expiry: <code>{expiry_display}</code>\n"
                f"✨ Your remaining days will be preserved!\n\n"
                f"⏳ Activation within 24 hours."
            )
        else:
            user_message = (
                f"✅ <b>Payment Confirmation Submitted</b>\n\n"
                f"📅 Active until: <code>{expiry_display}</code>\n"
                f"🔔 That's <b>{days_until} days</b> of Pro access!\n\n"
                f"⏳ Activation within 24 hours."
            )

        await query.edit_message_text(user_message, parse_mode="HTML")

    except Exception as e:
        print(f"❌ Payment confirmation error: {e}")
        await query.edit_message_text(
            "❌ <b>Something went wrong</b>\n\nPlease try again or contact /support",
            parse_mode="HTML"
        )


# ============================================================================
# NAVIGATION
# ============================================================================

async def back_to_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await upgrade_menu(update, context)


# ============================================================================
# ADMIN
# ============================================================================

async def pro_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admins only.")
        return

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, username, plan, expiry_date
        FROM users WHERE plan LIKE 'pro%'
        ORDER BY expiry_date IS NULL DESC, expiry_date ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    pro_count                       = len(rows)
    remaining                       = max(0, 100 - pro_count)
    urgency_text, urgency_emoji, _  = get_urgency_message()

    message = (
        f"👥 <b>Pro User List</b>\n\n"
        f"{urgency_emoji} {urgency_text}\n\n"
        f"Total Pro Users: {pro_count}/100\n"
        f"Remaining Founder Spots: {remaining}\n\n"
    )

    for row in rows:
        uid, username, plan, expiry = row
        uname   = f"@{username}" if username else f"ID: {uid}"
        exp_str = expiry if expiry else "Lifetime"
        message += f"• {uname} — {plan} (expires: {exp_str})\n"

    await update.message.reply_text(message, parse_mode="HTML")
