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



# --- USD Plan Prices ---
USD_PRICES = {
    "monthly": 7.99,
    "yearly": 59,
    "lifetime": 149
}

# --- Crypto Meta ---
CRYPTO_DETAILS = {
    "usdt": {"name": "USDT (TRC20)", "wallet": "TD1XFtspTGeQUjPJ4B4ki7pcTCsXLGAcva", "id": "tether"},
    "ton": {"name": "TON", "wallet": "UQDgqP7E0jzxoLFrSHVJiq6E4o4RZu3tdtHLPOEfyq0XMEyE", "id": "the-open-network"},
    "btc": {"name": "Bitcoin (BTC)", "wallet": "bc1q6898mactfdqqfut87wxckpjvd2nwdj22r8svh8", "id": "bitcoin"}
}

# --- Step 1: Show Upgrade Plans ---
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

async def upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/upgrade")
    await handle_streak(update, context)
    text = (
    "💎 *Upgrade to Pro — Stop Losing Money to Slow Decisions*\n\n"
    
    "You're already paying for this.\n"
    "Most traders spend *$30-60/month* on TradingView, alert apps, news feeds, and portfolio trackers.\n"
    "Then *waste hours* switching between them — and still miss the move.\n\n"
    
    "❌ *What that costs you:*\n"
    "• Late entries because you didn't see the breakout\n"
    "• Missed exits because alerts didn't fire\n"
    "• Bad trades because you couldn't confirm the setup fast enough\n\n"
    
    "✅ *Pro fixes this — everything you need, one chat, instant answers:*\n\n"
    
    "🔔 *Never Miss a Move*\n"
    "   Unlimited alerts: price, %, volume, risk, indicators — set once, forget it\n\n"
    
    "📊 *Confirm Setups in Seconds*\n"
    "   Charts, trends, regime analysis — no timeframe limits, instant access\n\n"
    
    "🤖 *Trade Like You Have a Research Team*\n"
    "   AI predictions, pattern scanner, strategy backtests — see what's working NOW\n\n"
    
    "💼 *Protect Your Portfolio Automatically*\n"
    "   Smart stop-loss & take-profit alerts — discipline, even when you're not watching\n\n"
    
    "🐋 *Follow the Smart Money*\n"
    "   Whale wallet tracking — know when institutions are moving before price reacts\n\n"
    
    "👁️ *Monitor Everything at Once*\n"
    "   Advanced watchlists — real-time tracking across 100+ coins\n\n"
    
    "⚡ *One bot. One subscription. Zero switching.*\n"
    "Pro users don't trade harder — they trade *smarter* and *faster*.\n\n"
    
    "🎁 *Founding Member Pricing — Lock It In Now*\n"
    "Early users get Pro at launch pricing. Price increases as we add features.\n\n"
    
    "*Choose your plan below 👇*"
)



    keyboard = [
        [InlineKeyboardButton("📆 Monthly - $7.99", callback_data="plan_monthly")],
        [InlineKeyboardButton("📅 Yearly - $59", callback_data="plan_yearly")],
        [InlineKeyboardButton("♾️ Lifetime - $149", callback_data="plan_lifetime")],
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

    keyboard = [
        [InlineKeyboardButton("💵 USDT (TRC20)", callback_data=f"pay_{plan}_usdt")],
        [InlineKeyboardButton("🪙 TON", callback_data=f"pay_{plan}_ton")],
        [InlineKeyboardButton("₿ Bitcoin", callback_data=f"pay_{plan}_btc")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_plans")]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=f"💳 *{plan.capitalize()} Plan selected*\n\nChoose a crypto to pay with:",
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

    text = (
        f"💼 *Upgrade to {plan.capitalize()} Plan*\n"
        f"💲 Price: ${usd_price} USD\n"
        f"🪙 Pay with: *{crypto_name}*\n\n"
        f"📥 *Amount to Pay:* `{live_amount} {crypto.upper()}` _(Live Rate)_\n"
        f"🏦 *Wallet Address:* `{wallet}`\n\n"
        "🔄 After payment, press the ✅ button below to notify us."
    )

    keyboard = [
        [InlineKeyboardButton("✅ I’ve Paid", callback_data=f"confirm_{plan}_{crypto}")],
        [
            InlineKeyboardButton("⬅ Back", callback_data=f"back_to_crypto_{plan}")
        ]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        user = query.from_user
        data = query.data.replace("confirm_", "")  # e.g. confirm_monthly_usdt
        plan, crypto = data.split("_")

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        user_name = user.full_name or user.username or "Unknown"
        crypto_info = CRYPTO_DETAILS.get(crypto.lower(), {})
        crypto_name = crypto_info.get("name", crypto.upper())
        usd_value = USD_PRICES.get(plan, "N/A")

        # Notify admin  
        admin_id = ADMIN_ID
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🛎 *Payment Confirmation Submitted*\n\n"
                    f"👤 User: [{user_name}](tg://user?id={user.id}) (`{user.id}`)\n"
                    f"📦 Plan: *{plan.capitalize()}* (${usd_value})\n"
                    f"💱 Crypto: *{crypto_name}*\n"
                    f"🕒 Time: {timestamp}\n\n"
                    f"Use `/setplan {user.id} pro_{plan}` to upgrade manually."
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ Failed to notify admin {admin_id}:", e)
    
        # Notify user
        await query.edit_message_text(
            "✅ Payment confirmation submitted successfully.\n\n"
            "⏳ Please wait while we verify your payment and upgrade your account shortly."
        )

    except Exception as e:
        print("❌ Payment confirmation error:", e)
        await query.edit_message_text("❌ Something went wrong. Please try again or contact support.")
        
