import os
import requests
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# === CoinMarketCap & FearGreed API Info ===
CMC_GLOBAL_API = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"
CMC_LISTINGS_API = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
CMC_API_KEY = os.getenv("CMC_API_KEY")
FEAR_GREED_API = "https://api.alternative.me/fng/"

def format_number(num):
    """Helper to format big numbers cleanly."""
    if num >= 1_000_000_000_000:
        return f"{num / 1_000_000_000_000:.2f}T"
    elif num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"{num / 1_000_000:.2f}M"
    else:
        return f"{num:,.0f}"

# --- NEW: Reusable function for notifications ---
def get_global_market_message() -> str:
    """Fetch global market data and return the formatted message string."""
    try:
        headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}

        # === Global Market Data ===
        response = requests.get(CMC_GLOBAL_API, headers=headers)
        response.raise_for_status()
        data = response.json().get("data", {})
        quote = data.get("quote", {}).get("USD", {})

        total_market_cap = quote.get("total_market_cap", 0)
        total_volume = quote.get("total_volume_24h", 0)
        btc_dominance = data.get("btc_dominance", 0)
        eth_dominance = data.get("eth_dominance", 0)
        defi_market_cap = data.get("defi_market_cap", 0)
        defi_dominance = data.get("defi_market_cap_dominance", 0)
        stablecoin_market_cap = data.get("stablecoin_market_cap", 0)
        stablecoin_volume = data.get("stablecoin_volume_24h", 0)
        derivatives_volume = data.get("derivatives_volume_24h", 0)
        market_cap_change = quote.get("total_market_cap_yesterday_percentage_change", 0)
        altcoin_market_cap = total_market_cap * ((100 - btc_dominance - eth_dominance) / 100)

        # === Top Gainer / Loser ===
        listings_response = requests.get(CMC_LISTINGS_API, headers=headers, params={"limit": 100})
        listings_data = listings_response.json().get("data", [])
        top_gainer = max(listings_data, key=lambda x: x["quote"]["USD"]["percent_change_24h"])
        top_loser = min(listings_data, key=lambda x: x["quote"]["USD"]["percent_change_24h"])

        # === Fear & Greed Index ===
        fng_response = requests.get(FEAR_GREED_API)
        fng_data = fng_response.json().get("data", [{}])[0]
        fear_greed_value = fng_data.get("value", "N/A")
        fear_greed_text = fng_data.get("value_classification", "N/A")

        # Build message
        message = (
            f"🌍 *Global Crypto Market Overview*\n\n"
            f"💰 *Total Market Cap:* ${format_number(total_market_cap)}\n"
            f"📊 *24h Volume:* ${format_number(total_volume)}\n"
            f"📈 *Market Cap Change (24h):* {market_cap_change:+.2f}%\n\n"
            f"🏆 *BTC Dominance:* {btc_dominance:.2f}%\n"
            f"💎 *ETH Dominance:* {eth_dominance:.2f}%\n"
            f"🪙 *Altcoin Market Cap:* ${format_number(altcoin_market_cap)}\n\n"
            f"💵 *Stablecoin Cap:* ${format_number(stablecoin_market_cap)}\n"
            f"🔄 *Stablecoin Volume (24h):* ${format_number(stablecoin_volume)}\n"
            f"⚙️ *DeFi Market Cap:* ${format_number(defi_market_cap)} ({defi_dominance:.2f}% dominance)\n"
            f"📉 *Derivatives Volume (24h):* ${format_number(derivatives_volume)}\n\n"
            f"🚀 *Top Gainer (24h):* {top_gainer['name']} ({top_gainer['symbol']}) +{top_gainer['quote']['USD']['percent_change_24h']:.2f}%\n"
            f"📉 *Top Loser (24h):* {top_loser['name']} ({top_loser['symbol']}) {top_loser['quote']['USD']['percent_change_24h']:.2f}%\n\n"
            f"😨 *Fear & Greed Index:* {fear_greed_value} ({fear_greed_text})"
        )

        return message

    except Exception as e:
        print(f"[Global] Error fetching global market data: {e}")
        return "⚠️ Could not fetch global market data."


# --- Keep original command working ---
async def global_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/global")
    await handle_streak(update, context)
    message = get_global_market_message()
    await update.message.reply_text(message, parse_mode="Markdown")


def register_global_handler(app):
    app.add_handler(CommandHandler("global", global_command))