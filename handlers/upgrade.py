from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import os
from dotenv import load_dotenv
import requests
from datetime import datetime


load_dotenv()

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_ID", "").split(",") if x.strip().isdigit()]

# --- USD Plan Prices ---
USD_PRICES = {
    "monthly": 10,
    "yearly": 99,
    "lifetime": 249
}

# --- Crypto Meta ---
CRYPTO_DETAILS = {
    "usdt": {"name": "USDT (TRC20)", "wallet": "TVex1n73MazbhC4C55P1449KsiEi9H5v1p", "id": "tether"},
    "ton": {"name": "TON", "wallet": "UQB6scBD94g_P3yoRkkC1ti5meFLfz4lpmNt7eoQhpLjD-lP", "id": "the-open-network"},
    "btc": {"name": "Bitcoin (BTC)", "wallet": "bc1qxhaqvxlnzvhw66savhkq5c7y6cyglmwtda77xe", "id": "bitcoin"}
}

# --- Step 1: Show Upgrade Plans ---
async def upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Upgrade menu received")
    text = (
    "*🚀 Upgrade to Pro*\n\n"
    "Unlock the full power of your crypto toolkit and gain an edge in the market with advanced tools and automation:\n\n"
    
    "🔔 *Unlimited Smart Alerts*\n"
    "• Set unlimited alerts (price, percent change, volume, risk, custom)\n"
    "• Alerts refresh every 30 seconds\n"
    "• Edit or remove alerts anytime\n\n"

    "📊 *Advanced Portfolio Tracking*\n"
    "• Add crypto, stablecoins, and fiat assets\n"
    "• Auto-track value with live market prices\n"
    "• Set profit targets and loss limits\n"
    "• Get alerts when portfolio hits your thresholds\n\n"

    "📈 *Watchlist & Market Insights*\n"
    "• Track your favorite coins easily\n"
    "• View top gainers, losers, trends\n"
    "• Stay updated on what’s moving\n\n"

    "🧠 *AI Market Predictions*\n"
    "• Get short-term forecasts based on RSI, MACD, EMA, and more\n"
    "• Sentiment-aware and always improving\n\n"

    "🎯 *Referral & Task Rewards*\n"
    "• Complete simple tasks to earn Pro trial\n"
    "• Invite friends and earn bonus days\n\n"

    "⚡ *Priority Access & Fast Performance*\n"
    "• Pro users get faster data refresh\n"
    "• Early access to new features and updates\n\n"
    
    "*Choose a plan to upgrade and unlock everything:*"
)
    keyboard = [
        [InlineKeyboardButton("📆 Monthly - $10", callback_data="plan_monthly")],
        [InlineKeyboardButton("📅 Yearly - $99", callback_data="plan_yearly")],
        [InlineKeyboardButton("♾️ Lifetime - $249", callback_data="plan_lifetime")],
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


# --- Helper: Get live price ---
def get_live_price_usd(coin_id: str):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        return response.json()[coin_id]["usd"]
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

        # Notify admins
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🛎 *Payment Confirmation Submitted*\n\n"
                        f"👤 User: [{user_name}](tg://user?id={user.id}) (`{user.id}`)\n"
                        f"📦 Plan: *{plan.capitalize()}* (${usd_value})\n"
                        f"💱 Crypto: *{crypto_name}*\n"
                        f"🕒 Time: {timestamp}\n\n"
                        f"Use `/setplan {user.id} {plan}` to upgrade manually."
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
        
