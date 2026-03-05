from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import os
from dotenv import load_dotenv
import requests
from datetime import datetime
from config import ADMIN_ID
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

load_dotenv()

from datetime import datetime, timedelta
from models.db import get_connection

# ============================================================================
# DYNAMIC URGENCY COUNTER
# ============================================================================

def get_pro_user_count() -> int:
    """
    Get current count of Pro users for urgency counter
    Returns total Pro users (all tiers)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM users
            WHERE plan LIKE 'pro%'
        """)
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    except Exception as e:
        print(f"❌ Error getting pro user count: {e}")
        return 0


def get_urgency_message() -> tuple[str, str]:
    """
    Generate dynamic urgency message based on real user count
    
    Returns:
        tuple: (urgency_text, emoji)
    """
    pro_count = get_pro_user_count()
    remaining = max(0, 100 - pro_count)
    
    # Dynamic urgency levels
    if remaining <= 10:
        emoji = "🔥"
        urgency = f"*LAST {remaining} SPOTS!* Price increases in {remaining} memberships!"
        intensity = "CRITICAL"
    elif remaining <= 25:
        emoji = "⚠️"
        urgency = f"*ONLY {remaining} SPOTS LEFT* at founder pricing!"
        intensity = "HIGH"
    elif remaining <= 50:
        emoji = "⏰"
        urgency = f"*{remaining} spots remaining* before price increase"
        intensity = "MEDIUM"
    else:
        emoji = "📊"
        urgency = f"{remaining}/100 founder spots available"
        intensity = "LOW"
    
    return urgency, emoji, intensity


def calculate_new_expiry(user_id: int, new_plan: str, stack: bool = True) -> datetime:
    """
    Calculate expiry date for new plan with smart stacking
    
    Args:
        user_id: Telegram user ID
        new_plan: New plan type (monthly, yearly, lifetime)
        stack: If True, add time to existing plan. If False, replace plan (start fresh)
    
    Returns:
        datetime object for new expiry date
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT plan, expiry_date 
        FROM users 
        WHERE user_id = ?
    """, (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    # Get current plan info
    current_plan = row[0].lower() if row and row[0] else "free"
    current_expiry = row[1] if row and row[1] else None
    
    # Parse current expiry if it exists
    current_expiry_dt = None
    if current_expiry:
        try:
            if isinstance(current_expiry, str):
                current_expiry_dt = datetime.fromisoformat(current_expiry)
            elif isinstance(current_expiry, datetime):
                current_expiry_dt = current_expiry
        except Exception as e:
            print(f"⚠️ Error parsing expiry: {e}")
    
    # Determine starting point for new plan
    now = datetime.utcnow()
    
    # ═══════════════════════════════════════════════════════════════════════
    # SMART STACKING LOGIC
    # ═══════════════════════════════════════════════════════════════════════
    
    if stack and current_plan.startswith("pro_") and current_expiry_dt and current_expiry_dt > now:
        # User has active Pro plan - ADD to existing time
        remaining_days = (current_expiry_dt - now).days
        start_date = current_expiry_dt
        print(f"✅ User {user_id} has {remaining_days} days left. Adding new plan time to existing.")
    else:
        # No active plan OR stack=False - start fresh
        start_date = now
        print(f"✅ User {user_id} plan starting immediately (replacing existing).")
    
    # Calculate new expiry based on plan type
    if new_plan == "monthly":
        new_expiry = start_date + timedelta(days=30)
    elif new_plan == "yearly":
        new_expiry = start_date + timedelta(days=365)
    elif new_plan == "lifetime":
        new_expiry = None  # Lifetime has no expiry
    else:
        raise ValueError(f"Invalid plan type: {new_plan}")
    
    return new_expiry
    
# --- USD Plan Prices ---
USD_PRICES = {
    "monthly": 7.99,
    "yearly": 59,
    "lifetime": 149
}

# Future pricing (shown for urgency)
FUTURE_PRICES = {
    "monthly": 14.99,
    "yearly": 99,
    "lifetime": 299
}

# --- Crypto Meta ---
CRYPTO_DETAILS = {
    "usdt": {"name": "USDT (TRC20)", "wallet": "TCvaGAp7UrMHwwzMH9jLukL9BbAGq39iLX", "id": "tether"},
    "ton": {"name": "TON", "wallet": "UQDgqP7E0jzxoLFrSHVJiq6E4o4RZu3tdtHLPOEfyq0XMEyE", "id": "the-open-network"},
    "btc": {"name": "Bitcoin (BTC)", "wallet": "14i5aBLB8yWh5gnApYUTaMAvPKukR6BqCM", "id": "bitcoin"}
}

# --- Step 1: Show Upgrade Plans with Dynamic Counter ---
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

async def upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/upgrade")
    await handle_streak(update, context)
    
    # ═══════════════════════════════════════════════════════════════════════
    # GET DYNAMIC URGENCY DATA
    # ═══════════════════════════════════════════════════════════════════════
    urgency_text, urgency_emoji, intensity = get_urgency_message()
    pro_count = get_pro_user_count()
    remaining = max(0, 100 - pro_count)
    
    # Calculate savings
    monthly_savings = FUTURE_PRICES["monthly"] - USD_PRICES["monthly"]
    yearly_savings = FUTURE_PRICES["yearly"] - USD_PRICES["yearly"]
    lifetime_savings = FUTURE_PRICES["lifetime"] - USD_PRICES["lifetime"]
    
    # Dynamic urgency bar (visual representation)
    filled = min(pro_count, 100)
    bar_length = 20
    filled_bars = int((filled / 100) * bar_length)
    empty_bars = bar_length - filled_bars
    progress_bar = "█" * filled_bars + "░" * empty_bars
    
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
        f"• Early adopter pricing applies to your *current plan only*\n"
        f"• If your plan expires, renewal will be at the *standard rate*\n"
        f"• Lock in the longest plan now to maximise your savings\n\n"
        
        f"💰 *Current Pricing (Save ${monthly_savings}-${lifetime_savings}):*\n"
        f"• Monthly: ~~${FUTURE_PRICES['monthly']}~~ → *${USD_PRICES['monthly']}* (Save ${monthly_savings:.2f}/mo)\n"
        f"• Yearly: ~~${FUTURE_PRICES['yearly']}~~ → *${USD_PRICES['yearly']}* (Save ${yearly_savings}/yr)\n"
        f"• Lifetime: ~~${FUTURE_PRICES['lifetime']}~~ → *${USD_PRICES['lifetime']}* (Save ${lifetime_savings})\n\n"
        
        f"⚡ *Join now, pay less. Let it expire, pay full price.*\n\n"
        
        f"*Choose your plan 👇*"
    )

    # Dynamic button text based on urgency
    if remaining <= 10:
        monthly_btn = f"🔥 Monthly - ${USD_PRICES['monthly']} (LAST {remaining}!)"
        yearly_btn = f"🔥 Yearly - ${USD_PRICES['yearly']} (LAST {remaining}!)"
        lifetime_btn = f"🔥 Lifetime - ${USD_PRICES['lifetime']} (LAST {remaining}!)"
    elif remaining <= 25:
        monthly_btn = f"⚠️ Monthly - ${USD_PRICES['monthly']} ({remaining} left)"
        yearly_btn = f"⚠️ Yearly - ${USD_PRICES['yearly']} ({remaining} left)"
        lifetime_btn = f"⚠️ Lifetime - ${USD_PRICES['lifetime']} ({remaining} left)"
    else:
        monthly_btn = f"📆 Monthly - ${USD_PRICES['monthly']}"
        yearly_btn = f"📅 Yearly - ${USD_PRICES['yearly']}"
        lifetime_btn = f"♾️ Lifetime - ${USD_PRICES['lifetime']}"

    keyboard = [
        [InlineKeyboardButton(monthly_btn, callback_data="plan_monthly")],
        [InlineKeyboardButton(yearly_btn, callback_data="plan_yearly")],
        [InlineKeyboardButton(lifetime_btn, callback_data="plan_lifetime")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=markup, parse_mode="Markdown")

    
# --- Step 2: Handle Plan Selection ---
async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan = query.data.replace("plan_", "")
    context.user_data["selected_plan"] = plan
    
    # Get urgency for payment page
    urgency_text, urgency_emoji, intensity = get_urgency_message()

    keyboard = [
        [InlineKeyboardButton("💵 USDT (TRC20)", callback_data=f"pay_{plan}_usdt")],
        [InlineKeyboardButton("🪙 TON", callback_data=f"pay_{plan}_ton")],
        [InlineKeyboardButton("₿ Bitcoin", callback_data=f"pay_{plan}_btc")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_plans")]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=(
            f"💳 *{plan.capitalize()} Plan selected*\n\n"
            f"{urgency_emoji} {urgency_text}\n\n"
            f"Choose a crypto to pay with:"
        ),
        reply_markup=markup,
        parse_mode="Markdown"
    )


# --- Handle Back to Plans ---
async def back_to_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await upgrade_menu(update, context)


import requests
import os
from dotenv import load_dotenv

# Load env variable
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

def get_live_price_usd(coin_id: str):
    """
    Fetch live USD price using CoinGecko API key.
    """
    try:
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin_id}&vs_currencies=usd&x_cg_demo_api_key={COINGECKO_API_KEY}"
        )

        response = requests.get(url, timeout=20)
        data = response.json()

        return data[coin_id]["usd"]

    except Exception as e:
        print("❌ Error fetching live price:", e)
        return None
        


# --- Helper: Calculate live amount ---
def calculate_live_crypto_amount(crypto: str, plan: str):
    usd = USD_PRICES[plan]
    coin_id = CRYPTO_DETAILS[crypto]["id"]
    price = get_live_price_usd(coin_id)
    if price:
        return round(usd / price, 6)
    return None


# --- Step 3: Show Payment Instructions ---
async def show_payment_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.replace("pay_", "")  # e.g. "monthly_usdt"
    plan, crypto = data.split("_")
    context.user_data["selected_plan"] = plan
    context.user_data["selected_crypto"] = crypto

    live_amount = calculate_live_crypto_amount(crypto, plan)
    if not live_amount:
        await query.message.reply_text("⚠️ Failed to fetch live price. Please try again later.")
        return

    crypto_info = CRYPTO_DETAILS[crypto]
    crypto_name = crypto_info["name"]
    wallet = crypto_info["wallet"]
    usd_price = USD_PRICES[plan]
    
    # Get urgency
    urgency_text, urgency_emoji, intensity = get_urgency_message()

    text = (
        f"💼 *Upgrade to {plan.capitalize()} Plan*\n"
        f"💲 Price: ${usd_price} USD\n"
        f"🪙 Pay with: *{crypto_name}*\n\n"
        f"{urgency_emoji} {urgency_text}\n\n"
        f"📥 *Amount to Pay:* `{live_amount} {crypto.upper()}` _(Live Rate)_\n"
        f"🏦 *Wallet Address:* `{wallet}`\n\n"
        "🔄 After payment, press the ✅ button below to notify us."
    )

    keyboard = [
        [InlineKeyboardButton("✅ I've Paid", callback_data=f"confirm_{plan}_{crypto}")],
        [
            InlineKeyboardButton("⬅ Back", callback_data=f"back_to_crypto_{plan}")
        ]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
from models.db import get_connection

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        user = query.from_user
        user_id = user.id
        data = query.data.replace("confirm_", "")  # e.g. confirm_monthly_usdt
        plan, crypto = data.split("_")

        # ═══════════════════════════════════════════════════════════════════════
        # CHECK FOR DUPLICATE SUBSCRIPTION ATTEMPT
        # ═══════════════════════════════════════════════════════════════════════
        
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT plan, expiry_date 
            FROM users 
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        current_plan = row[0].lower() if row and row[0] else "free"
        current_expiry = row[1] if row and row[1] else None
        conn.close()
        
        # Parse current expiry
        current_expiry_dt = None
        remaining_days = 0
        if current_expiry:
            try:
                if isinstance(current_expiry, str):
                    current_expiry_dt = datetime.fromisoformat(current_expiry)
                elif isinstance(current_expiry, datetime):
                    current_expiry_dt = current_expiry
                
                if current_expiry_dt and current_expiry_dt > datetime.utcnow():
                    remaining_days = (current_expiry_dt - datetime.utcnow()).days
            except Exception as e:
                print(f"⚠️ Error parsing expiry: {e}")
        
        # ═══════════════════════════════════════════════════════════════════════
        # DUPLICATE PLAN DETECTION
        # ═══════════════════════════════════════════════════════════════════════
        
        requested_plan = f"pro_{plan}"
        
        # Case 1: Already have the EXACT same plan with time remaining
        if current_plan == requested_plan and remaining_days > 0:
            await query.edit_message_text(
                f"⚠️ <b>You Already Have This Plan!</b>\n\n"
                f"📦 Current plan: <b>{current_plan.replace('pro_', '').capitalize()}</b>\n"
                f"📅 Expires: <code>{current_expiry_dt.strftime('%Y-%m-%d')}</code>\n"
                f"⏳ Days remaining: <b>{remaining_days} days</b>\n\n"
                f"❌ <b>Payment not needed right now</b>\n\n"
                f"💡 <b>What you can do:</b>\n"
                f"• Wait until your plan expires, then renew\n"
                f"• Upgrade to a longer plan (yearly/lifetime)\n"
                f"• Contact support if you have questions: /support\n\n"
                f"<i>Your current subscription is already active!</i>",
                parse_mode="HTML"
            )
            return
        
        # Case 2: Already have Lifetime (trying to buy anything)
        if current_plan == "pro_lifetime":
            await query.edit_message_text(
                f"👑 <b>You Have Lifetime Access!</b>\n\n"
                f"♾️ Your account has <b>Lifetime Pro</b> status\n"
                f"✅ You already have full access forever\n\n"
                f"❌ <b>No payment needed</b>\n\n"
                f"💡 Enjoy all Pro features - they never expire!",
                parse_mode="HTML"
            )
            return
        
        # Case 3: Downgrade attempt (yearly → monthly with time left)
        plan_hierarchy = {
            "free": 0,
            "pro_monthly": 1,
            "pro_yearly": 2,
            "pro_lifetime": 3
        }
        
        current_tier = plan_hierarchy.get(current_plan, 0)
        requested_tier = plan_hierarchy.get(requested_plan, 0)
        
        if requested_tier < current_tier and remaining_days > 0:
            # They're trying to downgrade while still subscribed
            await query.edit_message_text(
                f"⚠️ <b>Downgrade Detected</b>\n\n"
                f"📦 Current plan: <b>{current_plan.replace('pro_', '').capitalize()}</b> ({remaining_days} days left)\n"
                f"📦 Requested plan: <b>{plan.capitalize()}</b>\n\n"
                f"❌ <b>You can't downgrade while your current plan is active</b>\n\n"
                f"💡 <b>Options:</b>\n"
                f"• Wait until {current_expiry_dt.strftime('%Y-%m-%d')} (when current plan expires)\n"
                f"• Keep your current plan and enjoy the benefits\n"
                f"• Contact support: /support\n\n"
                f"<i>Your {current_plan.replace('pro_', '')} plan is still active!</i>",
                parse_mode="HTML"
            )
            return
        
        # ═══════════════════════════════════════════════════════════════════════
        # VALID PAYMENT - PROCEED
        # ═══════════════════════════════════════════════════════════════════════
        
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        user_name = user.full_name or user.username or "Unknown"
        crypto_info = CRYPTO_DETAILS.get(crypto.lower(), {})
        crypto_name = crypto_info.get("name", crypto.upper())
        usd_value = USD_PRICES.get(plan, "N/A")
        
        # ✅ CALCULATE NEW EXPIRY (STACKING LOGIC)
        new_expiry = calculate_new_expiry(user_id, plan, stack=True)
        
        # Format expiry for display
        if new_expiry:
            expiry_display = new_expiry.strftime("%Y-%m-%d")
            days_until = (new_expiry - datetime.utcnow()).days
        else:
            expiry_display = "Never (Lifetime)"
            days_until = "∞"

        # Get urgency for admin notification
        urgency_text, urgency_emoji, intensity = get_urgency_message()

        # ═══════════════════════════════════════════════════════════════════════
        # NOTIFY ADMIN
        # ═══════════════════════════════════════════════════════════════════════
        
        admin_id = ADMIN_ID
        
        # Build upgrade context message
        if current_plan != "free" and remaining_days > 0:
            upgrade_context = (
                f"🔄 *Upgrade Context:*\n"
                f"• Previous: {current_plan} ({remaining_days} days left)\n"
                f"• New: pro_{plan}\n"
                f"• Time added: {days_until} days total\n"
                f"• Remaining days preserved: ✅\n"
            )
        else:
            upgrade_context = f"🆕 *New subscription* (no previous plan)\n"
        
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🛎 *Payment Confirmation Submitted*\n\n"
                    f"{urgency_emoji} *{urgency_text}*\n\n"
                    f"👤 User: [{user_name}](tg://user?id={user.id}) (`{user.id}`)\n"
                    f"📦 Plan: *{plan.capitalize()}* (${usd_value})\n"
                    f"💱 Crypto: *{crypto_name}*\n"
                    f"🕒 Time: {timestamp}\n\n"
                    f"{upgrade_context}\n"
                    f"📅 *New Expiry:* `{expiry_display}`\n"
                    f"⏳ *Total Days:* {days_until}\n\n"
                    f"✅ Use `/setplan {user.id} pro_{plan}` to activate."
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ Failed to notify admin {admin_id}:", e)
    
        # ═══════════════════════════════════════════════════════════════════════
        # NOTIFY USER
        # ═══════════════════════════════════════════════════════════════════════
        
        if plan == "lifetime":
            user_message = (
                "✅ <b>Payment Confirmation Submitted</b>\n\n"
                "⏳ Please wait while we verify your payment.\n\n"
                "🎉 Your account will be upgraded to <b>Lifetime Pro</b>\n"
                "♾️ Never expires - full access forever!\n\n"
                "📧 You'll receive confirmation within 24 hours."
            )
        else:
            # Show upgrade details
            if current_plan != "free" and remaining_days > 0:
                user_message = (
                    "✅ <b>Payment Confirmation Submitted</b>\n\n"
                    "⏳ Please wait while we verify your payment.\n\n"
                    f"🔄 <b>Upgrade Details:</b>\n"
                    f"• Current plan: {current_plan.replace('pro_', '').capitalize()} ({remaining_days} days left)\n"
                    f"• New plan: {plan.capitalize()}\n"
                    f"• Total time: <b>{days_until} days</b>\n\n"
                    f"📅 New expiry date: <code>{expiry_display}</code>\n\n"
                    f"✨ <b>Your {remaining_days} remaining days will be preserved!</b>\n\n"
                    f"📧 You'll receive confirmation within 24 hours."
                )
            else:
                user_message = (
                    "✅ <b>Payment Confirmation Submitted</b>\n\n"
                    "⏳ Please wait while we verify your payment.\n\n"
                    f"📅 Your new plan will be active until: <code>{expiry_display}</code>\n"
                    f"🔔 That's <b>{days_until} days</b> of Pro access!\n\n"
                    f"📧 You'll receive confirmation within 24 hours."
                )
        
        await query.edit_message_text(user_message, parse_mode="HTML")

    except Exception as e:
        print("❌ Payment confirmation error:", e)
        await query.edit_message_text(
            "❌ <b>Something went wrong</b>\n\n"
            "Please try again or contact support: /support",
            parse_mode="HTML"
        )


# ============================================================================
# ADMIN COMMAND - Pro User List (for reference)
# ============================================================================

async def pro_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admins only.")
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, username, plan, expiry_date 
        FROM users
        WHERE plan LIKE 'pro%'
        ORDER BY expiry_date IS NULL DESC, expiry_date ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    # Show count and urgency
    pro_count = len(rows)
    remaining = max(0, 100 - pro_count)
    urgency_text, urgency_emoji, intensity = get_urgency_message()
    
    message = (
        f"👥 **Pro User List**\n\n"
        f"{urgency_emoji} {urgency_text}\n\n"
        f"Total Pro Users: {pro_count}/100\n"
        f"Remaining Founder Spots: {remaining}\n\n"
    )
    
    for row in rows:
        user_id, username, plan, expiry = row
        username_display = f"@{username}" if username else f"ID: {user_id}"
        expiry_display = expiry if expiry else "Lifetime"
        message += f"• {username_display} - {plan} (expires: {expiry_display})\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")
