from telegram import Update
import httpx
import feedparser
import logging
from telegram.ext import ContextTypes
from services.coin_data import get_coin_data
from utils.formatting import format_large_number
from models.user import set_auto_delete_minutes
from utils.notification_service import send_auto_delete
from config import CRYPTO_PANIC_API_KEY, BOT_USERNAME, ADMIN_ID
from utils.indicators import get_crypto_indicators
from handlers.portfolio import add_asset
from models.user import get_user_plan
from services.price_service import get_crypto_price
import openai
import os
from models.db import get_connection
import openai
import os
from dotenv import load_dotenv
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY=os.getenv("OPENROUTER_API_KEY") 





from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


help_pages = {
    1: "*📖 Bot Guide: Alerts*\n\n"
       "• `/alert price BTC > 65000`\n"
       "• `/alert percent ETH +5`\n"
       "• `/alert volume XRP 5x 1h`\n"
       "• `/alert risk SOL SL:90 TP:130`\n"
       "• `/alert custom DOGE < 0.1 RSI < 30`\n"
       "• `/alert portfolio BTC 1 up 68000`\n"
       "• `/alerts` / `/remove TYPE ID`\n"
       "• `/removeall`\n",

    2: "*📊 Trend & Smart Tools*\n\n"
       "• `/trend BTC 4h` – RSI, EMA, MACD\n"
       "• `/predict ETH` – AI trend prediction\n"
       "• `/watch BTC 65000 10` – Watchlist alert\n"
       "• `/watchlist`, `/portfolio`\n",

    3: "*🎯 Tasks & Referrals*\n\n"
       "• `/tasks` – Complete 3 steps for Pro\n"
       "• Invite friends using your referral code\n\n"
       "*💎 Plans:*\n"
       "• Free: 3 alerts, no repeats\n"
       "• Pro: Unlimited, portfolio, custom, signals\n"
       "• `/upgrade` to see benefits\n",

    4: "*🌐 Community & Support*\n\n"
       "• [Join Group](https://t.me/YOURGROUPLINK)\n"
       "• Ask questions or share feedback\n\n"
       "Need help? DM the admin or use `/tasks`."
}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    name = user.first_name or "Trader"
    args = context.args

    # --- Handle referral code ---
    referred_by = None
    if args:
        try:
            referred_by = int(args[0])
        except ValueError:
            referred_by = None

    conn = get_connection()
    cursor = conn.cursor()

    # Check if user already referred
    cursor.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (user_id,))
    already_referred = cursor.fetchone()

    if referred_by and not already_referred and referred_by != user_id:
        cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id, timestamp)
            VALUES (?, ?, datetime('now'))
        """, (referred_by, user_id))
        conn.commit()

    # Register user if not exists
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, plan) VALUES (?, ?, 'free')", (user.id, user.username))
    # Check if user is new (INSERT happened)
    if cursor.rowcount > 0:
        print(f"🆕 New user joined: {user.id} (@{user.username})")

        # Send notification to admin
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"👤 *New User Joined!*\n"
                     f"ID: `{user.id}`\n"
                     f"Username: @{user.username or 'N/A'}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ Failed to notify admin: {e}")
    conn.commit()
    conn.close()

    # --- Welcome Message ---
    text = (
        f"👋 Welcome *{name}*!\n\n"
        f"📈 _You're now using one of Telegram's most powerful crypto trading assistants._\n\n"
        "💹 Thousands of traders use this bot daily to:\n"
        "• Set price, volume, and portfolio alerts\n"
        "• Track market trends & get AI predictions\n"
        "• Protect portfolios with SL/TP alerts\n"
        "• Monitor risk and volatility\n\n"
        "✨ Join the growing Pro community and level up your trading!"
    )

    # --- Inline Buttons ---
    keyboard = [
        [
            InlineKeyboardButton("🚀 Upgrade", callback_data="upgrade_menu"),
            InlineKeyboardButton("📈 How It Helps", callback_data="how_it_helps")
        ],
        [
            InlineKeyboardButton("📚 View Commands", callback_data="view_commands"),
            InlineKeyboardButton("👥 Join Community", callback_data="join_community")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 1
    keyboard = [
        [InlineKeyboardButton("⏭️ Next", callback_data=f"help_page|{page+1}")],
        [InlineKeyboardButton("❌ Close", callback_data="help_close")]
    ]
    await update.message.reply_text(
        help_pages[page],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )
    
async def handle_help_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "help_close":
        await query.edit_message_text("ℹ️ Closed help menu.")
        return

    if data.startswith("help_page|"):
        _, page_str = data.split("|")
        page = int(page_str)

        text = help_pages.get(page, "⚠️ Page not found.")
        buttons = []

        if page > 1:
            buttons.append(InlineKeyboardButton("⏮️ Back", callback_data=f"help_page|{page-1}"))
        if page < len(help_pages):
            buttons.append(InlineKeyboardButton("⏭️ Next", callback_data=f"help_page|{page+1}"))

        buttons_markup = [buttons] if buttons else []
        buttons_markup.append([InlineKeyboardButton("❌ Close", callback_data="help_close")])

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons_markup),
            disable_web_page_preview=True
        )
        
from models.db import get_connection

from models.db import get_connection

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user_id}"

    # Get referral count from referrals table
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()

    await update.message.reply_text(
        f"📣 *Invite friends & earn rewards!*\n\n"
        f"🔗 *Your referral link:*\n{link}\n\n"
        f"👥 *Referrals so far:* {count}\n\n"
        f"🎯 Use /tasks to complete tasks and unlock Pro access!\n"
        f"💎 You also get credit when your friends join via your link.",
        parse_mode="Markdown"
    )
    
from telegram import Update
from telegram.ext import ContextTypes

async def handle_upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    upgrade_text = (
        "💎 *Upgrade to Pro Plan*\n\n"
        "Unlock the full power of this bot:\n"
        "• Set unlimited alerts 🚨\n"
        "• Access advanced alert types 🔧\n"
        "• Get auto-refreshing alerts 🔁\n"
        "• Monitor your portfolio 📦\n"
        "• Use premium tools like predictions 📊\n\n"
        "To upgrade, type /upgrade or complete /tasks to earn 1-month free access!"
    )
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
async def handle_how_it_helps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    upgrade_text = (
        "📈 *How This Bot Helps You Trade Smarter:*\n\n"
        "✅ *Never miss key price movements* — Set alerts for price, volume, RSI, MACD & more.\n"
        "✅ *Plan your trades* — Add SL/TP and portfolio-based alerts.\n"
        "✅ *Automate your edge* — Get notified instantly without screen-watching.\n"
        "✅ *Stay disciplined* — Let the bot alert you instead of emotions driving decisions.\n\n"
        "_Trusted by 1000+ crypto traders worldwide._ 🌍"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
    
async def handle_view_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    upgrade_text = (
        "📘 *Available Bot Commands:*\n\n"
        "📊 *Alerts:*\n"
        "/alert — Set price alert\n"
        "/percent — % change alert\n"
        "/volume — Volume spike alert\n"
        "/risk — SL/TP alerts\n"
        "/custom — Price + RSI combo alert\n"
        "/portfolioalert — Portfolio-based alert\n"
        "/alerts — View active alerts\n"
        "/remove — Remove specific alert\n"
        "/removeall — Delete all alerts\n\n"

        "🧾 *Portfolio Tools:*\n"
        "/portfolio — View your holdings\n"
        "/add — Add a coin\n"
        "/remove — Remove a coin\n"
        "/portfoliolimit — Set max loss alert\n"
        "/portfoliotarget — Set profit target alert\n\n"

        "🛠 *Utilities:*\n"
        "/trend — Market trend analysis\n"
        "/prediction — AI-powered forecast *(Pro)*\n"
        "/watchlist — Manage watchlist\n"
        "/addwatch — Add to watchlist\n"
        "/removewatch — Remove from watchlist\n\n"

        "🎁 *Referral & Rewards:*\n"
        "/tasks — Earn 1 month Pro\n"
        "/invite — Refer & earn\n\n"

        "⚙️ *Account:*\n"
        "/upgrade — Upgrade to Pro\n"
        "/plan — Check current plan\n"
        "/start — Restart bot intro"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
    
    
async def handle_join_community(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    community_link = "https://t.me/+tSWwj5w7S8hkZmM0"  # Private invite link

    upgrade_text = (
        "🤝 *Join Our Trading Community!*\n\n"
        "Connect with hundreds of traders, share signals, ask questions, and learn from others using this bot.\n\n"
        f"🔗 Join here: {community_link}"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=upgrade_text, parse_mode="Markdown", reply_markup=reply_markup)
    
async def handle_back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    name = user.first_name or "Trader"

    keyboard = [
        [
            InlineKeyboardButton("🚀 Upgrade", callback_data="upgrade_menu"),
            InlineKeyboardButton("📈 How It Helps", callback_data="how_it_helps")
        ],
        [
            InlineKeyboardButton("📚 View Commands", callback_data="view_commands"),
            InlineKeyboardButton("👥 Join Community", callback_data="join_community")
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
  
        f"👋 Welcome *{name}*!\n\n"
        f"📈 _You're now using one of Telegram's most powerful crypto trading assistants._\n\n"
        "💹 Thousands of traders use this bot daily to:\n"
        "• Set price, volume, and portfolio alerts\n"
        "• Track market trends & get AI predictions\n"
        "• Protect portfolios with SL/TP alerts\n"
        "• Monitor risk and volatility\n\n"
        "✨ Join the growing Pro community and level up your trading!"
    )

    await query.edit_message_text(text=welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
    
async def set_auto_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if len(args) != 1 or not args[0].isdigit():
        await send_auto_delete(context, update.message.reply_text,"❌ Usage: /autodelete [minutes]\nExample: `/autodelete 3`", parse_mode="Markdown")
        return

    minutes = int(args[0])
    if minutes < 0 or minutes > 60:
        await send_auto_delete(context, update.message.reply_text,"⚠️ Please enter a value between 0 and 60.")
        return

    from models.user import set_auto_delete_minutes
    set_auto_delete_minutes(user_id, minutes)

    if minutes == 0:
        await send_auto_delete(context, update.message.reply_text,"🗑 Auto-delete has been *disabled*.", parse_mode="Markdown")
    else:
        await send_auto_delete(context, update.message.reply_text,f"🕒 Messages will now auto-delete after *{minutes} minutes*.", parse_mode="Markdown")
    
async def handle_chart_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    if len(parts) == 3 and parts[0] == "chart":
        symbol = parts[1]
        timeframe = parts[2]

        # Reuse chart handler logic
        from handlers.chart import show_chart
        context.args = [symbol, timeframe]
        await show_chart(update, context)
        
async def handle_add_alert_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    if len(parts) == 2 and parts[0] == "addalert":
        symbol = parts[1]
        await query.message.reply_text(
            f"🛎 To add an alert for *{symbol}*, use this format:\n"
            f"`/set price {symbol} > 67000`\n\n"
            "Or use `/help` to see full options.",
            parse_mode="Markdown"
        )
        

async def coin_alias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.strip().lstrip("/")
    coin_data = get_coin_data(cmd)

    if not coin_data:
        await send_auto_delete(context, update.message.reply_text,f"❌ Coin `{cmd}` not found.", parse_mode="Markdown")
        return

    m = coin_data["market_data"]
    pc_1h = m["price_change_percentage_1h_in_currency"].get("usd", 0)
    pc_24h = m["price_change_percentage_24h_in_currency"].get("usd", 0)
    pc_7d = m["price_change_percentage_7d_in_currency"].get("usd", 0)
    pc_30d = m["price_change_percentage_30d_in_currency"].get("usd", 0)
    price = m["current_price"]["usd"]
    ath = m["ath"]["usd"]
    vol = m["total_volume"]["usd"]
    cap = m["market_cap"]["usd"]
    high = m["high_24h"]["usd"]
    low = m["low_24h"]["usd"]
    
    ath_display = format_large_number(ath)
    vol_display = format_large_number(vol)
    cap_display = format_large_number(cap)

    msg = f"""📊 *{coin_data['name']}* (`{coin_data['symbol'].upper()}`)
    
    💰 Price: `${price:,.2f}`
    📈 24h High: `${high:,.2f}`
    📉 24h Low: `${low:,.2f}`
    🕐 1h: {pc_1h:.2f}%
    📅 24h: {pc_24h:.2f}%
    📆 7d: {pc_7d:.2f}%
    🗓 30d: {pc_30d:.2f}%
    📛 ATH: `${ath_display}`
    🔁 24h Volume: `${vol_display}`
    🌍 Market Cap: `${cap_display}`
    """
    # Add "View Chart" button
    symbol_upper = coin_data["symbol"].upper()
    keyboard = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📈 View Chart", callback_data=f"chart_{symbol_upper}_1h"),
        InlineKeyboardButton("➕ Add Alert", callback_data=f"addalert_{symbol_upper}")
    ]
])

    await send_auto_delete(context, update.message.reply_text,msg, parse_mode="Markdown", reply_markup=keyboard)


EXCLUDED_COMMANDS = {
    "start", "help", "tasks", "referral", "referrals", "alerts", "watch", "watchlist",
    "upgrade", "remove", "removeall", "best", "worst", "news", "trend", "addasset",
    "portfolio", "portfoliotarget", "portfoliolimit", "prediction", "edit", "stats", "setplan", "prolist"
}

async def coin_command_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text.strip().lstrip("/").lower()

    if command in EXCLUDED_COMMANDS:
        return  # Skip — handled by specific command handlers

    await coin_alias_handler(update, context)  # Treat as coin alias (e.g., /btc, /eth)

COINGECKO_API = "https://api.coingecko.com/api/v3"

async def best_gainers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Notify user it's working
        loading_msg = await update.message.reply_text("📈 Fetching top 24h gainers...")

        # Get top 100 coins by market cap
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{COINGECKO_API}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 100,
                    "page": 1,
                    "price_change_percentage": "24h",
                },
                timeout=10
            )
            data = response.json()

        # Sort by highest 24h % gain
        top_gainers = sorted(
            data,
            key=lambda x: x.get("price_change_percentage_24h", 0),
            reverse=True
        )[:3]

        message = "🏆 *Top 3 Gainers (24h)*:\n\n"
        for coin in top_gainers:
            name = coin["name"]
            symbol = coin["symbol"].upper()
            price = coin["current_price"]
            change = coin["price_change_percentage_24h"]
            message += f"• *{name}* ({symbol})\n  Price: ${price:.2f}\n  Gain: 📈 {change:.2f}%\n\n"

        await loading_msg.edit_text(message, parse_mode="Markdown")

    except Exception as e:
        print(f"Error in /best: {e}")
        await update.message.reply_text("❌ Could not fetch top gainers. Try again later.")   
     

async def worst_losers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        loading_msg = await update.message.reply_text("📉 Fetching top 24h losers...")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{COINGECKO_API}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 100,
                    "page": 1,
                    "price_change_percentage": "24h",
                },
                timeout=10
            )
            data = response.json()

        # Sort by lowest 24h % gain (i.e., biggest losses)
        top_losers = sorted(
            data,
            key=lambda x: x.get("price_change_percentage_24h", 0)
        )[:3]

        message = "🔻 *Top 3 Losers (24h)*:\n\n"
        for coin in top_losers:
            name = coin["name"]
            symbol = coin["symbol"].upper()
            price = coin["current_price"]
            change = coin["price_change_percentage_24h"]
            message += f"• *{name}* ({symbol})\n  Price: ${price:.2f}\n  Loss: 🔻 {change:.2f}%\n\n"

        await loading_msg.edit_text(message, parse_mode="Markdown")

    except Exception as e:
        print(f"Error in /worst: {e}")
        await update.message.reply_text("❌ Could not fetch losers. Try again later.") 
        

CRYPTO_NEWS_RSS = "https://cryptopanic.com/news/rss/"

async def crypto_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        loading = await update.message.reply_text("📰 Fetching latest crypto news...")

        feed = feedparser.parse(CRYPTO_NEWS_RSS)
        entries = feed.entries[:5]  # Get top 5

        if not entries:
            await loading.edit_text("❌ No news found at the moment.")
            return

        message = "*📰 Latest Crypto News:*\n\n"
        for entry in entries:
            title = entry.title
            link = entry.link
            message += f"• [{title}]({link})\n"

        await loading.edit_text(message, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        print(f"/news error: {e}")
        await update.message.reply_text("⚠️ Failed to fetch crypto news. Try again later.")
        

async def trend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("❌ Usage: /trend BTC [timeframe]\nExample: /trend ETH 4h")
        return

    symbol = args[0].upper()
    symbol = symbol.upper().replace("USDT", "") + "/USDT"
    timeframe = args[1] if len(args) > 1 else "1h"
    
   

    allowed_timeframes = ["1h", "4h", "1d", "30m", "15m"]
    if timeframe not in allowed_timeframes:
        await update.message.reply_text("❌ Invalid timeframe. Use one of: 1h, 4h, 1d, 30m, 15m")
        return

    # Check user plan
    plan = get_user_plan(user_id)
    if plan == "free" and timeframe != "1h":
        await update.message.reply_text("🔒 Only the *1h* timeframe is available on Free Plan.\nUse /upgrade to unlock more.", parse_mode="Markdown")
        return

    await update.message.reply_text("📡 Analyzing trend data... please wait.")

    try:
        indicators = await get_crypto_indicators(symbol, timeframe)
        if not indicators:
            await update.message.reply_text("⚠️ Could not fetch indicator data.")
            return

        msg = f"📊 *Trend Analysis for {symbol}* ({timeframe})\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"💰 *Price:* `${indicators['price']:.2f}`\n"
        
        # RSI interpretation
        rsi = indicators["rsi"]
        if rsi > 70:
            rsi_trend = "🔺 *Overbought*"
        elif rsi < 30:
            rsi_trend = "🔻 *Oversold*"
        else:
            rsi_trend = "🟡 *Neutral*"
        msg += f"📉 *RSI:* `{rsi:.2f}` → {rsi_trend}\n"

        # MACD with direction indication
        macd = indicators["macd"]
        signal = indicators["macdSignal"]
        hist = indicators["macdHist"]
        macd_trend = "🔼 Bullish" if float(macd) > float(signal) else "🔽 Bearish"
        msg += f"📈 *MACD:* `{macd}`\n"
        msg += f"📊 *Signal:* `{signal}`\n"
        msg += f"🧮 *Histogram:* `{hist}` → {macd_trend}\n"

        # EMA
        msg += f"📏 *EMA(20):* `${indicators['ema20']:.2f}`\n"
        

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        print("Trend command error:", e)
        await update.message.reply_text("❌ Error fetching trend data.")
        


import requests


def safe(val):
    return val if val is not None else "N/A"


async def predict_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    if plan != "pro":
        await update.message.reply_text(
            "🔒 This feature is for *Pro users only*.\nUse /upgrade to unlock.",
            parse_mode="Markdown"
        )
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /prediction BTC [timeframe]\nExample: /prediction ETH 4h")
        return

    symbol = args[0].upper()
#    timeframe = args[1] if len(args) > 1 else "1h"
#    # Map user-friendly to API-valid
#    timeframe_map = {
#    "1m": "1min",
#    "5m": "5min",
#    "15m": "15min",
#    "30m": "30min",
#    "1h": "1h",
#    "2h": "2h",
#    "4h": "4h",
#    "8h": "8h",
#    "1d": "1day",
#    "1w": "1week"
#    }

#    if timeframe not in timeframe_map:
#        await update.message.reply_text("❌ Invalid timeframe. Use one of: 1m, 15m, 30m, 1h, 2h, 4h, 8h, 1d, 1w")
#        return

    # Map user-friendly to API-valid
    timeframe_map = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "8h": "8h",
    "1d": "1day",
    "1w": "1week"
    }
    
    user_input_tf = args[1] if len(args) > 1 else "1h"
    if user_input_tf not in timeframe_map:
        await update.message.reply_text("❌ Invalid timeframe. Use one of: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d, 1w")
        return

    timeframe = timeframe_map[user_input_tf]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("🧠 Analyzing market conditions and predicting... Please wait...")

    # Fetch live price and indicators
    price = get_crypto_price(symbol)
    indicators = await get_crypto_indicators(symbol, timeframe)

    if price is None or indicators is None:
        await update.message.reply_text("⚠️ Could not fetch price or indicator data for this coin.")
        return

    prompt = f"""
    You're a crypto analyst. Based on the following data, give a brief, realistic short-term forecast for {symbol} in the next {timeframe}:

    • Price: ${price}
    • RSI: {safe(indicators.get('rsi'))}
    • MACD Histogram: {safe(indicators.get('macd'))}
    • EMA(20): {safe(indicators.get('ema20'))}
    • 24h High/Low: {safe(indicators.get('high_24h'))} / {safe(indicators.get('low_24h'))}
    • Volume: {safe(indicators.get('volume'))}

    Only include key insights and a directional prediction (up, down, or sideways). Be concise.
    """

    prediction = None

    # Try OpenAI first
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}]
        )
        prediction = response.choices[0].message.content.strip()

    except Exception as e:
        print("OpenAI failed:", e)
        prediction = None

    # Fallback to OpenRouter if OpenAI failed
    if not prediction:
        try:
            fallback_response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "mistralai/mixtral-8x7b-instruct",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=20
            )

            if fallback_response.status_code == 200:
                prediction = fallback_response.json()["choices"][0]["message"]["content"].strip()
            else:
                print("OpenRouter response error:", fallback_response.status_code, fallback_response.text)
                await update.message.reply_text("❌ Fallback model failed. Please try again later.")
                return

        except Exception as e:
            print("Fallback error:", e)
            await update.message.reply_text("❌ Fallback error occurred. Please try again later.")
            return

    await update.message.reply_text(
        f"📈 *AI Prediction for {symbol} ({timeframe}):*\n\n{prediction}\n\n"
        "⚠️ _Disclaimer: This prediction is generated by AI based on market data and does not constitute financial advice._",
        parse_mode="Markdown"
    )



    
    
from telegram.ext import CommandHandler

def register_general_handlers(app):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_help_pagination, pattern=r"^help_"))
    app.add_handler(CallbackQueryHandler(handle_upgrade_menu, pattern="^upgrade_menu$"))    
    app.add_handler(CallbackQueryHandler(handle_how_it_helps, pattern="^how_it_helps$"))
    app.add_handler(CallbackQueryHandler(handle_view_commands, pattern="^view_commands$"))
    app.add_handler(CallbackQueryHandler(handle_join_community, pattern="^join_community$"))
    app.add_handler(CallbackQueryHandler(handle_back_to_start, pattern="^back_to_start$"))
    app.add_handler(CommandHandler("autodelete", set_auto_delete))
    app.add_handler(CallbackQueryHandler(handle_chart_button, pattern="^chart_"))
    app.add_handler(CallbackQueryHandler(handle_add_alert_button, pattern="^addalert_"))
    app.add_handler(CommandHandler("best", best_gainers))
    app.add_handler(CommandHandler("worst", worst_losers))
    app.add_handler(CommandHandler("news", crypto_news))
    app.add_handler(CommandHandler("trend", trend_command))
    app.add_handler(CommandHandler("addasset", add_asset))
    app.add_handler(CommandHandler("prediction", predict_price))
    app.add_handler(MessageHandler(
    filters.TEXT & filters.Regex(r"^/[a-zA-Z]{2,10}$"),  # increase to 10 to allow commands like /referral
    coin_command_router
)) 

   
    