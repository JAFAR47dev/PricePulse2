# notifications/handlers/test_handler.py
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from notifications.models import get_user_notification_settings
from notifications.services.notification_data import get_notification_data
from notifications.scheduler import send_notification


async def test_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered when user taps 'Send Test Notification'.
    Sends a clean, well-formatted live preview of user notifications.
    """
    query = update.callback_query
    user_id = query.from_user.id

    # --- Fetch user settings ---
    settings = get_user_notification_settings(user_id)

    # --- Fetch notification data (cached for speed) ---
    try:
        notif_data = await get_notification_data(ttl=60)
    except Exception as e:
        print(f"[TestNotification] Failed to fetch data: {e}")
        await query.answer("⚠️ Failed to fetch data. Try again later.", show_alert=True)
        return

    parts = ["📢 *Test Notification Preview*\n"]

    # --- 🌍 Global Market Section ---
    if settings.get("include_global") and notif_data.get("global"):
        g = notif_data["global"]
        if isinstance(g, dict):
            parts.append(
                "\n🌍 *Global Market Overview*\n"
                f"💰 *Market Cap:* {g.get('market_cap', 'N/A')}\n"
                f"📊 *24h Volume:* {g.get('volume', 'N/A')}\n"
                f"📈 *Change:* {g.get('change', 'N/A')}\n"
                f"🏆 *BTC Dom:* {g.get('btc_dominance', 'N/A')} | "
                f"💎 *ETH Dom:* {g.get('eth_dominance', 'N/A')}"
            )
        else:
            parts.append(f"🌍 {g}")

    # --- 🚀 Top Gainers ---
    if settings.get("include_gainers") and notif_data.get("gainers"):
        gainers_data = notif_data["gainers"]
        if isinstance(gainers_data, list) and len(gainers_data) > 0:
            formatted = "\n".join(
                [f"• {c[0]} — 📈 *{c[1]}*" for c in gainers_data[:3]]
            )
            parts.append(f"\n🚀 *Top Gainers (24h)*\n{formatted}")
        else:
            parts.append(f"🚀 *Top Gainers:* {gainers_data}")

    # --- 📉 Top Losers ---
    if settings.get("include_losers") and notif_data.get("losers"):
        losers_data = notif_data["losers"]
        if isinstance(losers_data, list) and len(losers_data) > 0:
            formatted = "\n".join(
                [f"• {c[0]} — 🔻 *{c[1]}*" for c in losers_data[:3]]
            )
            parts.append(f"\n📉 *Top Losers (24h)*\n{formatted}")
        else:
            parts.append(f"📉 *Top Losers:* {losers_data}")

    # --- 📰 News Section ---
    if settings.get("include_news") and notif_data.get("news"):
        news_data = notif_data["news"]
        if isinstance(news_data, list) and len(news_data) > 0:
            formatted = "\n".join(
                [f"• [{n.split('](')[0].replace('[', '').strip()}]({n.split('](')[1][:-1]})"
                 if '](' in n else f"• {n}" for n in news_data[:3]]
            )
            parts.append(f"\n📰 *Latest News*\n{formatted}")
        else:
            parts.append(f"📰 *Crypto:* {news_data}")

    # --- ⛽ Gas Fees ---
    if settings.get("include_gas") and notif_data.get("gas"):
        gas_data = notif_data["gas"]
        if isinstance(gas_data, str):
            parts.append(f"\n⛽ *Gas Fees*\n{gas_data}")
        elif isinstance(gas_data, dict):
            parts.append(
                "\n⛽ *Gas Fees (ETH)*\n"
                f"• Low: {gas_data.get('low', 'N/A')}\n"
                f"• Standard: {gas_data.get('standard', 'N/A')}\n"
                f"• High: {gas_data.get('high', 'N/A')}"
            )

    # --- 💡 Coin of the Day ---
    if settings.get("include_cod") and notif_data.get("cod"):
        cod_data = notif_data["cod"]
        if isinstance(cod_data, dict):
            parts.append(
                f"\n💡 *Coin of the Day*\n"
                f"• *{cod_data.get('coin', 'N/A')}* — {cod_data.get('reason', 'No reason provided.')}"
            )
        else:
            parts.append(f"\n💡 *Coin:* {cod_data}")

    # --- Combine all sections ---
    message = "\n".join(parts)

    # --- Send the message using the user's preferred method ---
    await send_notification(context.bot, settings, message)

    # --- Confirm to user ---
    await query.answer("✅ Test notification sent!")