from models.db import get_connection
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from models.user_activity import update_last_active
from config import ADMIN_ID
import sqlite3
import time
import aiohttp
import asyncio
import os
from datetime import datetime
from services.movers_service import MoversService
from handlers.movers import format_movers_message

_movers_service = MoversService()
# ============================================================================
# ENV KEYS
# ============================================================================
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ============================================================================
# DB UTILS
# ============================================================================

def get_connection_with_retry(max_retries=3):
    for attempt in range(max_retries):
        try:
            conn = get_connection()
            conn.execute("PRAGMA busy_timeout = 30000")
            return conn
        except sqlite3.OperationalError:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
    return get_connection()


def init_task_progress_with_conn(user_id: int, conn):
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(task_progress)")
        columns = [col[1] for col in cursor.fetchall()]

        column_defaults = {
            "user_id": user_id,
            "daily_streak": 0,
            "last_active_date": None,
            "streak_reward_claimed": 0,
            "pro_expiry_date": None,
            "referral_count": 0,
            "claimed_referral_rewards": "[]",
            "referral_rewards_claimed": "",
            "social_tg": 0,
            "social_tw": 0,
            "social_story": 0,
        }

        insert_columns = [col for col in column_defaults if col in columns]
        insert_values = [column_defaults[col] for col in insert_columns]
        columns_str = ", ".join(insert_columns)
        placeholders = ", ".join(["?" for _ in insert_columns])

        cursor.execute(
            f"INSERT OR IGNORE INTO task_progress ({columns_str}) VALUES ({placeholders})",
            insert_values,
        )
        print(f"✅ Task progress initialized for user {user_id}")
    except Exception as e:
        print(f"❌ Error initializing task progress for user {user_id}: {e}")
        raise


# ============================================================================
# MARKET DATA FETCHERS
# ============================================================================

async def fetch_market_data() -> dict:
    """Fetch BTC/ETH prices, global data, and fear & greed index."""
    result = {
        "btc_price": None,
        "btc_change": None,
        "eth_price": None,
        "eth_change": None,
        "fear_greed": None,
        "fear_greed_label": None,
        "btc_dominance": None,
        "total_market_cap": None,
        "market_cap_change": None,
        "total_volume": None,
    }

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    async with aiohttp.ClientSession() as session:
        # BTC + ETH prices
        try:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin,ethereum",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    btc = data.get("bitcoin", {})
                    eth = data.get("ethereum", {})
                    result["btc_price"] = btc.get("usd")
                    result["btc_change"] = btc.get("usd_24h_change")
                    result["eth_price"] = eth.get("usd")
                    result["eth_change"] = eth.get("usd_24h_change")
        except Exception as e:
            print(f"⚠️ Price fetch error: {e}")

        # Global market data
        try:
            async with session.get(
                "https://api.coingecko.com/api/v3/global",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    gdata = data.get("data", {})
                    result["btc_dominance"] = gdata.get(
                        "market_cap_percentage", {}
                    ).get("btc")
                    result["market_cap_change"] = gdata.get(
                        "market_cap_change_percentage_24h_usd"
                    )
                    result["total_market_cap"] = gdata.get(
                        "total_market_cap", {}
                    ).get("usd")
                    result["total_volume"] = gdata.get("total_volume", {}).get("usd")
        except Exception as e:
            print(f"⚠️ Global data fetch error: {e}")

        # Fear & Greed (alternative.me — free, no key needed)
        try:
            async with session.get(
                "https://api.alternative.me/fng/?limit=1",
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    fng_list = data.get("data", [])
                    if fng_list:
                        result["fear_greed"] = int(fng_list[0].get("value", 50))
                        result["fear_greed_label"] = fng_list[0].get(
                            "value_classification", ""
                        )
        except Exception as e:
            print(f"⚠️ Fear & Greed fetch error: {e}")

    return result


async def fetch_btc_levels() -> dict:
    """Derive support/resistance from last 14 days of daily OHLC."""
    levels = {"resistance": None, "support1": None, "support2": None}

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin/ohlc",
                params={"vs_currency": "usd", "days": "14"},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    candles = await resp.json()
                    if candles and len(candles) >= 3:
                        highs = sorted([c[2] for c in candles], reverse=True)
                        lows = sorted([c[3] for c in candles])
                        levels["resistance"] = round(highs[0], 0)
                        levels["support1"] = round(lows[0], 0)
                        levels["support2"] = (
                            round(lows[1], 0)
                            if len(lows) > 1
                            else round(lows[0] * 0.97, 0)
                        )
    except Exception as e:
        print(f"⚠️ BTC levels fetch error: {e}")

    return levels


async def fetch_top_mover() -> dict:
    """Fetch biggest 24h gainer from CoinGecko top 100."""
    result = {"name": None, "symbol": None, "change": None}

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 100,
                    "page": 1,
                    "price_change_percentage": "24h",
                },
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    coins = await resp.json()
                    if coins:
                        best = max(
                            coins,
                            key=lambda c: c.get("price_change_percentage_24h") or -999,
                        )
                        result["name"] = best.get("name")
                        result["symbol"] = (best.get("symbol") or "").upper()
                        result["change"] = best.get("price_change_percentage_24h")
    except Exception as e:
        print(f"⚠️ Top mover fetch error: {e}")

    return result


# ============================================================================
# SCORE + REGIME HELPERS
# ============================================================================

def calculate_market_score(market_data: dict) -> int:
    score = 50

    fg = market_data.get("fear_greed")
    if fg is not None:
        if fg <= 15:
            score -= 25
        elif fg <= 25:
            score -= 18
        elif fg <= 35:
            score -= 10
        elif fg >= 80:
            score += 18
        elif fg >= 65:
            score += 10
        elif fg >= 55:
            score += 5

    change = market_data.get("market_cap_change")
    if change is not None:
        if change < -4:
            score -= 18
        elif change < -2:
            score -= 10
        elif change < -0.5:
            score -= 5
        elif change > 4:
            score += 15
        elif change > 2:
            score += 8
        elif change > 0.5:
            score += 4

    btc_change = market_data.get("btc_change")
    if btc_change is not None:
        if btc_change < -5:
            score -= 12
        elif btc_change < -2:
            score -= 6
        elif btc_change > 4:
            score += 10
        elif btc_change > 2:
            score += 5

    return max(0, min(100, score))


def get_regime(score: int) -> str:
    if score >= 65:
        return "Bull"
    elif score >= 48:
        return "Neutral"
    elif score >= 30:
        return "Bear"
    else:
        return "Extreme Bear"


def get_score_emoji(score: int) -> str:
    if score >= 65:
        return "🟢"
    elif score >= 48:
        return "🟡"
    elif score >= 30:
        return "🔴"
    else:
        return "🔴🔴"


def get_trade_rule(score: int) -> str:
    if score <= 20:
        return "Cash is your best position right now.\nWait for score > 40 before any new entries."
    elif score <= 35:
        return "Reduce exposure. Tighten stops.\nOnly the cleanest setups with minimal size."
    elif score <= 50:
        return "Selective entries only. Confirm momentum first.\nTake profits faster than usual."
    elif score <= 65:
        return "Conditions are improving — stay disciplined.\nSize positions correctly and keep stops tight."
    else:
        return "Momentum is on your side today.\nStay disciplined — markets can shift fast."


def get_hold_probability(score: int) -> int:
    if score <= 20:
        return 80
    elif score <= 30:
        return 72
    elif score <= 40:
        return 62
    elif score <= 50:
        return 50
    else:
        return 28


def format_large_number(n) -> str:
    if n is None:
        return "N/A"
    if n >= 1_000_000_000_000:
        return f"${n / 1_000_000_000_000:.2f}T"
    if n >= 1_000_000_000:
        return f"${n / 1_000_000_000:.1f}B"
    return f"${n:,.0f}"


# ============================================================================
# AI VERDICT VIA OPENROUTER
# ============================================================================

async def fetch_ai_verdict(
    market_data: dict, score: int, regime: str, levels: dict, top_mover: dict
) -> str:
    if not OPENROUTER_API_KEY:
        return _fallback_verdict(score, regime)

    btc_price = market_data.get("btc_price", "N/A")
    btc_change = market_data.get("btc_change")
    eth_change = market_data.get("eth_change")
    fg = market_data.get("fear_greed", "N/A")
    fg_label = market_data.get("fear_greed_label", "")
    change_str = f"{btc_change:+.1f}%" if btc_change is not None else "N/A"
    eth_str = f"{eth_change:+.1f}%" if eth_change is not None else "N/A"
    mover_str = (
        f"{top_mover['name']} ({top_mover['symbol']}) +{top_mover['change']:.1f}%"
        if top_mover.get("change")
        else "N/A"
    )

    prompt = (
        "You are a professional crypto risk analyst writing a 3-sentence daily market verdict "
        "for traders opening a Telegram trading bot. Be direct, specific, and risk-first. "
        "No fluff. No bullet points. No emojis. Plain sentences only. "
        "Sound like a senior trader who has seen hundreds of market cycles.\n\n"
        f"Market data right now:\n"
        f"- Market Score: {score}/100\n"
        f"- Regime: {regime}\n"
        f"- BTC: ${btc_price:,} ({change_str})\n"
        f"- ETH: {eth_str}\n"
        f"- Fear & Greed: {fg}/100 ({fg_label})\n"
        f"- BTC Resistance: ${levels.get('resistance', 'N/A'):,}\n"
        f"- BTC Support: ${levels.get('support1', 'N/A'):,}\n"
        f"- Top mover today: {mover_str}\n\n"
        "Write exactly 3 sentences. "
        "Sentence 1: what the market is doing and why it matters to a trader opening the app right now. "
        "Sentence 2: what the biggest risk is today specifically. "
        "Sentence 3: what disciplined traders are doing right now — be concrete, not generic."
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistralai/mistral-7b-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 140,
                    "temperature": 0.55,
                },
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    verdict = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if verdict:
                        return verdict
    except Exception as e:
        print(f"⚠️ OpenRouter verdict error: {e}")

    return _fallback_verdict(score, regime)


def _fallback_verdict(score: int, regime: str) -> str:
    if score <= 20:
        return (
            "The market is in active capitulation — most assets are bleeding with no confirmed floor. "
            "Entering any position right now means absorbing maximum volatility with minimum edge. "
            "Smart traders are sitting in stablecoins and waiting for a score above 40 before deploying capital."
        )
    elif score <= 35:
        return (
            "Market structure is bearish with elevated fear across most sectors. "
            "The risk of further downside outweighs the potential upside at current levels. "
            "Reduce exposure, tighten stops, and wait for regime confirmation before new entries."
        )
    elif score <= 55:
        return (
            "The market is in a neutral range with no strong directional bias confirmed. "
            "Selective setups exist but conviction is low — avoid oversizing any position today. "
            "Trade only the cleanest setups with tight risk and take profits faster than usual."
        )
    else:
        return (
            "Market conditions are improving with momentum building across key sectors. "
            "The trend is supportive but always confirm entries with your own levels before risking capital. "
            "Size positions appropriately and keep stops tight — conditions can shift fast."
        )


# ============================================================================
# BUILD START MESSAGE
# ============================================================================

async def build_start_message(name: str) -> str:
    today = datetime.utcnow().strftime("%a, %b %d %Y · %H:%M UTC")

    # Fetch all data concurrently
    market_data, levels, top_mover = await asyncio.gather(
        fetch_market_data(),
        fetch_btc_levels(),
        fetch_top_mover(),
    )

    score = calculate_market_score(market_data)
    fg = market_data.get("fear_greed")
    fg_label = market_data.get("fear_greed_label", "")
    regime = get_regime(score)
    score_emoji = get_score_emoji(score)
    trade_rule = get_trade_rule(score)

    # AI verdict
    verdict = await fetch_ai_verdict(market_data, score, regime, levels, top_mover)

    # BTC line
    btc_price = market_data.get("btc_price")
    btc_change = market_data.get("btc_change")
    if btc_price and btc_change is not None:
        btc_arrow = "📈" if btc_change >= 0 else "📉"
        btc_line = f"BTC  ${btc_price:>10,.0f}  {btc_change:+.1f}%  {btc_arrow}"
    elif btc_price:
        btc_line = f"BTC  ${btc_price:,.0f}"
    else:
        btc_line = "BTC  — unavailable"

    # ETH line
    eth_price = market_data.get("eth_price")
    eth_change = market_data.get("eth_change")
    if eth_price and eth_change is not None:
        eth_arrow = "📈" if eth_change >= 0 else "📉"
        eth_line = f"ETH  ${eth_price:>10,.0f}  {eth_change:+.1f}%  {eth_arrow}"
    else:
        eth_line = None

    # Fear & Greed
    if fg is not None:
        if fg <= 20:
            fg_emoji = "😱"
        elif fg <= 35:
            fg_emoji = "😨"
        elif fg <= 50:
            fg_emoji = "😐"
        elif fg <= 65:
            fg_emoji = "🙂"
        else:
            fg_emoji = "🤑"
        fg_line = f"Fear & Greed: {fg_emoji} {fg}/100  ({fg_label})"
    else:
        fg_line = None

    # Market cap
    mcap = market_data.get("total_market_cap")
    mcap_change = market_data.get("market_cap_change")
    if mcap and mcap_change is not None:
        mcap_arrow = "▲" if mcap_change >= 0 else "▼"
        mcap_line = (
            f"Market Cap:  {format_large_number(mcap)}  "
            f"({mcap_arrow}{abs(mcap_change):.1f}%)"
        )
    else:
        mcap_line = None

    # BTC dominance
    dom = market_data.get("btc_dominance")
    dom_line = f"BTC Dominance:  {dom:.1f}%" if dom else None

    # Top mover
    if top_mover.get("name") and top_mover.get("change"):
        mover_line = (
            f"🚀 Top mover:  {top_mover['name']} "
            f"({top_mover['symbol']})  +{top_mover['change']:.1f}%"
        )
    else:
        mover_line = None

    # BTC key levels
    resistance = levels.get("resistance")
    support1 = levels.get("support1")
    support2 = levels.get("support2")

    if resistance and support1 and support2 and btc_price:
        res_pct = ((resistance - btc_price) / btc_price) * 100
        s1_pct = ((btc_price - support1) / btc_price) * 100
        s2_pct = ((btc_price - support2) / btc_price) * 100
        levels_block = (
            f"📍 *BTC Key Levels:*\n"
            f"🔴 Resistance: ${resistance:,.0f}  (+{res_pct:.1f}%)\n"
            f"🟢 Support 1:   ${support1:,.0f}  (-{s1_pct:.1f}%)\n"
            f"🟢 Support 2:   ${support2:,.0f}  (-{s2_pct:.1f}%)"
        )
    elif resistance and support1:
        levels_block = (
            f"📍 *BTC Key Levels:*\n"
            f"🔴 Resistance: ${resistance:,.0f}\n"
            f"🟢 Support:     ${support1:,.0f}"
        )
    else:
        levels_block = "📍 Key levels → `/levels btc 4h`"

    # Hold warning (only shown in bear conditions)
    hold_prob = get_hold_probability(score)
    hold_block = ""
    if btc_price and hold_prob >= 58:
        downside_target = round(btc_price * (1 - (hold_prob / 100) * 0.28), 0)
        capital_at_risk = round(btc_price - downside_target, 0)
        hold_block = (
            f"⚠️ *Holding BTC right now?*\n"
            f"{hold_prob}% probability of further decline.\n"
            f"Downside target: ${downside_target:,.0f}  |  "
            f"At risk per BTC: ${capital_at_risk:,.0f}\n"
            f"→ Run `/hold btc` for the full exit analysis."
        )

    # Snapshot block
    snapshot_lines = [btc_line]
    if eth_line:
        snapshot_lines.append(eth_line)
    if fg_line:
        snapshot_lines.append(fg_line)
    if mcap_line:
        snapshot_lines.append(mcap_line)
    if dom_line:
        snapshot_lines.append(dom_line)
    if mover_line:
        snapshot_lines.append(mover_line)

    snapshot = "\n".join(snapshot_lines)

    # Assemble full message
    text = (
        f"🛡️ *PricePulse — {today}*\n\n"
        f"Welcome, *{name}*. Before you place a single trade,\n"
        f"here's what the market looks like right now:\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Score: *{score}/100* {score_emoji}  |  Regime: *{regime}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{snapshot}\n\n"
        f"🧠 *Today's Verdict:*\n"
        f"_{verdict}_\n\n"
        f"{levels_block}\n\n"
    )

    if hold_block:
        text += f"{hold_block}\n\n"

    text += (
        f"📌 *Today's rule:*\n"
        f"{trade_rule}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 *What this bot does for you:*\n"
        f"• Shows you when NOT to trade — before you lose\n"
        f"• Gives you live key levels on any coin\n"
        f"• Alerts you the moment price hits your zone\n"
        f"• AI analysis on any coin in seconds\n"
        f"• Tracks your portfolio with auto SL/TP alerts\n\n"
        f"👇 *Where do you want to start?*"
    )

    return text


# ============================================================================
# KEYBOARDS
# ============================================================================

def main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🛡️ Hold or Exit?", callback_data="start_hold"),
            InlineKeyboardButton("📊 Market Strategy", callback_data="start_strategy"),
        ],
        [
            InlineKeyboardButton("📍 Key Levels", callback_data="start_levels"),
            InlineKeyboardButton("🔔 Set an Alert", callback_data="start_alerts"),
        ],
        [
            InlineKeyboardButton("⚡ Top Movers", callback_data="start_movers"),
            InlineKeyboardButton("🧠 AI Analysis", callback_data="start_analysis"),
        ],
        [
            InlineKeyboardButton("🚀 Pro Features", callback_data="start_pro"),
            InlineKeyboardButton("📋 All Commands", callback_data="start_commands"),
        ],
        [
            InlineKeyboardButton("👤 My Account", callback_data="start_account"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back to Home", callback_data="start_back")]]
    )


# ============================================================================
# START COMMAND
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    await update_last_active(user_id, command_name="/start")
    username = user.username
    name = user.first_name or "Trader"
    args = context.args

    referred_by = None
    if args:
        try:
            referred_by = int(args[0])
        except ValueError:
            referred_by = None

    conn = get_connection_with_retry()
    cursor = conn.cursor()
    is_new_user = False

    try:
        cursor.execute(
            "SELECT 1 FROM referrals WHERE referred_id = ?", (user_id,)
        )
        already_referred = cursor.fetchone()

        if referred_by and not already_referred and referred_by != user_id:
            cursor.execute(
                "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referred_by, user_id),
            )
            init_task_progress_with_conn(user_id, conn)
            init_task_progress_with_conn(referred_by, conn)
            cursor.execute(
                "UPDATE task_progress SET referral_count = referral_count + 1 WHERE user_id = ?",
                (referred_by,),
            )

        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, plan) VALUES (?, ?, 'free')",
            (user_id, username),
        )
        if cursor.rowcount > 0:
            is_new_user = True
            print(f"🆕 New user joined: {user_id} (@{username})")

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Database error in start_command: {e}")
    finally:
        conn.close()

    # Notify admin only for new users
    if is_new_user:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "👤 *New User Joined!*\n"
                    f"ID: `{user_id}`\n"
                    f"Name: {name}\n"
                    f"Username: @{username or 'N/A'}"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"❌ Failed to notify admin: {e}")

    # Build live start message
    try:
        text = await build_start_message(name)
    except Exception as e:
        print(f"❌ build_start_message failed: {e}")
        text = (
            f"🛡️ *PricePulse*\n\n"
            f"Welcome, *{name}*.\n\n"
            f"Trade less. Preserve more.\n"
            f"This bot filters weak setups so you don't fund the market's liquidity.\n\n"
            f"Use the buttons below to get started."
        )

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard(),
        parse_mode="Markdown",
    )


# ============================================================================
# CALLBACK HANDLERS
# All callbacks use the "start_" prefix to prevent collisions with other
# handlers registered elsewhere in the project.
# ============================================================================

async def fetch_hold_btc_data() -> dict:
    """
    Fetch everything needed to run a live BTC hold analysis.
    Returns a dict with prices, volumes, current_price, fear_greed, and ath.
    Gracefully returns empty dict on any failure.
    """
    result = {}
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    async with aiohttp.ClientSession() as session:
        # Historical prices + volumes (180 days for indicator depth)
        try:
            async with session.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                params={"vs_currency": "usd", "days": 180, "interval": "daily"},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["prices"] = [p[1] for p in data.get("prices", [])]
                    result["volumes"] = [v[1] for v in data.get("total_volumes", [])]
        except Exception as e:
            print(f"⚠️ hold BTC chart fetch error: {e}")

        # Current price + ATH
        try:
            async with session.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    mdata = data.get("market_data", {})
                    result["current_price"] = mdata.get("current_price", {}).get("usd")
                    result["ath"] = mdata.get("ath", {}).get("usd")
                    result["market_cap_rank"] = data.get("market_cap_rank", 1)
        except Exception as e:
            print(f"⚠️ hold BTC details fetch error: {e}")

        # Fear & Greed
        try:
            async with session.get(
                "https://api.alternative.me/fng/?limit=1",
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    fng = data.get("data", [{}])[0]
                    result["fear_greed"] = (
                        int(fng.get("value", 50)),
                        fng.get("value_classification", "Neutral"),
                    )
        except Exception as e:
            print(f"⚠️ hold fear & greed fetch error: {e}")

    return result


def _hold_calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def _hold_calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _hold_detect_rsi_divergence(prices, lookback=14):
    """Returns (bullish_div, bearish_div)"""
    if len(prices) < lookback * 2:
        return False, False
    rsi_vals = []
    for i in range(lookback, len(prices)):
        r = _hold_calculate_rsi(prices[:i + 1])
        if r is not None:
            rsi_vals.append(r)
    if len(rsi_vals) < lookback:
        return False, False
    rp = prices[-lookback:]
    rr = rsi_vals[-lookback:]
    bullish = rp[-1] < rp[0] and rr[-1] > rr[0]
    bearish = rp[-1] > rp[0] and rr[-1] < rr[0]
    return bullish, bearish


def _hold_detect_regime(prices):
    sma20 = _hold_calculate_sma(prices, 20)
    sma50 = _hold_calculate_sma(prices, 50)
    sma200 = _hold_calculate_sma(prices, 200) if len(prices) >= 200 else None
    if not sma20 or not sma50:
        return "Unknown"
    if sma200:
        if sma20 > sma50 > sma200:
            return "Bull"
        if sma20 < sma50 < sma200:
            return "Bear"
    else:
        if sma20 > sma50 * 1.02:
            return "Bull"
        if sma20 < sma50 * 0.98:
            return "Bear"
    return "Sideways"


def _hold_volume_capitulation(prices, volumes):
    if len(prices) < 14 or len(volumes) < 14:
        return False
    change = (prices[-1] - prices[-7]) / prices[-7]
    recent_vol = sum(volumes[-7:]) / 7
    prev_vol = sum(volumes[-14:-7]) / 7
    return change < -0.05 and recent_vol > prev_vol * 1.4


def run_btc_hold_analysis(data: dict) -> dict:
    """
    Runs the same conservative scoring logic from hold.py on BTC data.
    Returns a clean result dict ready for display.
    """
    prices = data.get("prices", [])
    volumes = data.get("volumes", [])
    current_price = data.get("current_price") or (prices[-1] if prices else None)
    ath = data.get("ath", 0) or 0
    fear_greed = data.get("fear_greed")

    if not prices or not current_price or len(prices) < 50:
        return {}

    regime = _hold_detect_regime(prices)
    sma50 = _hold_calculate_sma(prices, 50)
    sma200 = _hold_calculate_sma(prices, 200) if len(prices) >= 200 else None
    rsi = _hold_calculate_rsi(prices)
    bullish_div, bearish_div = _hold_detect_rsi_divergence(prices)
    capitulation = _hold_volume_capitulation(prices, volumes)

    price_vs_50 = ((current_price - sma50) / sma50 * 100) if sma50 else 0
    drawdown_ath = ((current_price - ath) / ath * 100) if ath > 0 else 0
    local_high = max(prices[-30:]) if len(prices) >= 30 else current_price
    drawdown_local = ((current_price - local_high) / local_high * 100)

    # Conservative scoring — same as hold.py
    score = -20
    confirmations = 0
    signals_bull = []
    signals_bear = []

    if regime == "Bull":
        score += 35
        confirmations += 1
        signals_bull.append("Confirmed bull market")
    elif regime == "Bear":
        score -= 35
        signals_bear.append("Confirmed bear market")
    else:
        score -= 10

    if sma50 and sma200:
        if sma50 > sma200:
            score += 15
            confirmations += 1
            signals_bull.append("Golden cross active")
        elif sma50 < sma200 * 0.98:
            score -= 15
            signals_bear.append("Death cross active")

    if price_vs_50 > 5:
        score += 10
        confirmations += 1
        signals_bull.append(f"Above 50MA (+{price_vs_50:.1f}%)")
    elif price_vs_50 < -5:
        score -= 10
        signals_bear.append(f"Below 50MA ({price_vs_50:.1f}%)")

    if rsi:
        if rsi < 30:
            if bullish_div:
                score += 20
                confirmations += 1
                signals_bull.append(f"Bullish divergence (RSI {rsi:.0f})")
            else:
                score -= 15
                signals_bear.append(f"RSI oversold, no divergence ({rsi:.0f})")
        elif rsi > 70:
            score -= 10
            signals_bear.append(f"RSI overbought ({rsi:.0f})")
        elif 45 < rsi < 65:
            score += 5
            signals_bull.append(f"RSI healthy ({rsi:.0f})")

    if capitulation:
        score += 15
        confirmations += 1
        signals_bull.append("Volume capitulation signal")

    if fear_greed:
        fg_val, fg_label = fear_greed
        if fg_val < 15:
            score += 5
            signals_bull.append(f"Extreme fear ({fg_val}) — contrarian")
        elif fg_val > 85:
            score -= 5
            signals_bear.append(f"Extreme greed ({fg_val})")

    # Clamp score
    score = max(-100, min(100, score))

    # Verdict
    if score >= 50 and confirmations >= 4:
        verdict = "🟢 ACCUMULATE"
        confidence = min(90, 60 + (score - 50) * 0.5)
    elif score >= 25 and confirmations >= 3:
        verdict = "🟢 HOLD"
        confidence = min(80, 50 + (score - 25) * 1.0)
    elif score >= -10:
        verdict = "🟡 PARTIAL EXIT"
        confidence = min(75, 55 + abs(score) * 1.5)
    else:
        verdict = "🔴 EXIT NOW"
        confidence = min(90, 60 + abs(score + 10) * 0.6)

    prob_decline = max(20, min(85, 50 - score * 0.4)) if score > 0 else min(85, 55 + abs(score) * 0.4)
    downside_target = round(current_price * (1 - (prob_decline / 100) * 0.25), 0)
    capital_at_risk = round(current_price - downside_target, 0)
    preservation_score = round(max(1, min(10, (score + 50) / 10)), 1)

    # Invalidation level
    invalidation = round(sma50 * 1.05, 0) if sma50 and "EXIT" in verdict else (round(sma50 * 0.95, 0) if sma50 else None)

    return {
        "verdict": verdict,
        "confidence": round(confidence),
        "score": score,
        "confirmations": confirmations,
        "prob_decline": round(prob_decline),
        "current_price": current_price,
        "downside_target": downside_target,
        "capital_at_risk": capital_at_risk,
        "drawdown_ath": round(drawdown_ath, 1),
        "drawdown_local": round(drawdown_local, 1),
        "regime": regime,
        "rsi": round(rsi, 0) if rsi else None,
        "bullish_div": bullish_div,
        "price_vs_50": round(price_vs_50, 1),
        "capitulation": capitulation,
        "fear_greed": fear_greed,
        "signals_bull": signals_bull,
        "signals_bear": signals_bear,
        "preservation_score": preservation_score,
        "invalidation": invalidation,
        "sma50": round(sma50, 0) if sma50 else None,
        "sma200": round(sma200, 0) if sma200 else None,
    }


def format_hold_preview(a: dict) -> str:
    """
    Format a compact but data-rich BTC hold preview for the start screen.
    Shows the verdict, key signals, and a clear CTA to run the full command.
    """
    price = a["current_price"]
    verdict = a["verdict"]
    fg = a.get("fear_greed")
    fg_str = f"{fg[0]}/100 ({fg[1]})" if fg else "N/A"

    # Regime emoji
    regime_emoji = "🟢" if a["regime"] == "Bull" else "🔴" if a["regime"] == "Bear" else "🟡"

    # RSI line
    rsi_val = a.get("rsi")
    if rsi_val:
        if a.get("bullish_div"):
            rsi_line = f"RSI {rsi_val:.0f} — Bullish divergence 📈"
        elif rsi_val < 30:
            rsi_line = f"RSI {rsi_val:.0f} — Oversold ⚠️"
        elif rsi_val > 70:
            rsi_line = f"RSI {rsi_val:.0f} — Overbought ⚠️"
        else:
            rsi_line = f"RSI {rsi_val:.0f} — Neutral"
    else:
        rsi_line = "RSI — N/A"

    # Top 2 signals each side
    bull_lines = "\n".join(f"  ✅ {s}" for s in a["signals_bull"][:2]) or "  —"
    bear_lines = "\n".join(f"  ❌ {s}" for s in a["signals_bear"][:2]) or "  —"

    # Invalidation
    inv_line = (
        f"  • Price closes above ${a['invalidation']:,.0f} with volume"
        if a.get("invalidation") and "EXIT" in verdict
        else f"  • Price breaks below ${a['invalidation']:,.0f}"
        if a.get("invalidation")
        else "  • Market regime shifts to Bull"
    )

    text = (
        f"🛡️ *BTC Hold Analysis — Live*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 BTC Price: *${price:,.0f}*\n"
        f"🎯 Verdict: *{verdict}*\n"
        f"📊 Confidence: *{a['confidence']}%* "
        f"| Confirmations: *{a['confirmations']}/3*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📉 *30-Day Outlook:*\n"
        f"  Decline probability: *{a['prob_decline']}%*\n"
        f"  Downside target: *${a['downside_target']:,.0f}*\n"
        f"  Capital at risk/BTC: *${a['capital_at_risk']:,.0f}*\n"
        f"  ATH drawdown: *{a['drawdown_ath']}%*\n\n"
        f"📊 *Signal Snapshot:*\n"
        f"  {regime_emoji} Regime: *{a['regime']}*\n"
        f"  {'✅' if a['price_vs_50'] > 0 else '❌'} "
        f"50MA: *{'Above' if a['price_vs_50'] > 0 else 'Below'} "
        f"by {abs(a['price_vs_50'])}%*\n"
        f"  📈 {rsi_line}\n"
        f"  😱 Fear & Greed: *{fg_str}*\n\n"
        f"✅ *For:*\n{bull_lines}\n\n"
        f"❌ *Against:*\n{bear_lines}\n\n"
        f"🔄 *Analysis flips if:*\n{inv_line}\n\n"
        f"💎 Preservation Score: *{a['preservation_score']}/10*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_This is a preview. Run `/hold btc` for the\n"
        f"full multi-confirmation analysis with re-entry\n"
        f"zones, timeframe selection, and all signals._\n\n"
        f"_Analysis only — not financial advice._"
    )
    return text


async def handle_start_hold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Loading live BTC analysis…")

    # Show loading state immediately
    await query.edit_message_text(
        text="⏳ *Fetching live BTC hold analysis…*\n\n_Running conservative multi-confirmation analysis_",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        data = await fetch_hold_btc_data()
        analysis = run_btc_hold_analysis(data)

        if not analysis:
            raise ValueError("Insufficient data returned")

        text = format_hold_preview(analysis)

    except Exception as e:
        print(f"⚠️ handle_start_hold error: {e}")
        text = (
            "🛡️ *Hold or Exit Analysis*\n\n"
            "Live data is temporarily unavailable.\n\n"
            "*Run the full command directly:*\n"
            "`/hold btc` — Full BTC hold analysis\n"
            "`/hold eth 30d` — 30-day ETH outlook\n"
            "`/hold sol` — Any coin\n\n"
            "_Analysis only — not financial advice._"
        )

    await query.edit_message_text(
        text=text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


# ============================================================================
# SETUP PREVIEW — fetches live BTC 1h data for the Market Strategy button
# ============================================================================

async def handle_start_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Loading live BTC setup…")

    await query.edit_message_text(
        text="⏳ *Fetching live BTC 1h setup analysis…*\n\n_Calculating indicators and key levels_",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        from handlers.setup import setup_analyzer, format_setup_message

        setup_data = await setup_analyzer.analyze_setup("BTC", "1h")

        if not setup_data:
            raise ValueError("Insufficient data")

        text = await format_setup_message(setup_data, "BTC", "1h")

    except Exception as e:
        print(f"⚠️ handle_start_strategy error: {e}")
        text = (
            "📊 *BTC Setup Analysis*\n\n"
            "Live data is temporarily unavailable.\n\n"
            "*Run the full command directly:*\n"
            "`/setup btc 1h` — BTC 1-hour setup\n"
            "`/setup btc 4h` — BTC 4-hour setup\n"
            "`/setup eth 1h` — ETH 1-hour setup\n\n"
            "_Not financial advice._"
        )

    await query.edit_message_text(
        text=text, parse_mode="Markdown", reply_markup=back_keyboard()
    )

# ============================================================================
# LEVELS PREVIEW — imports and uses LevelsEngine directly
# ============================================================================

from services.levels_engine import LevelsEngine

_levels_engine = LevelsEngine()


def format_levels_preview(result: dict) -> str:
    """
    Format a compact but data-rich BTC 1h levels preview for the start screen.
    Uses the same data structure returned by LevelsEngine.calculate_levels().
    """
    current_price = result["current_price"]
    resistance_levels = result.get("resistance_levels", [])
    support_levels = result.get("support_levels", [])
    atr_pct = result.get("atr_pct", 0)

    def fp(v):
        if v is None: return "N/A"
        if v >= 1000: return f"${v:,.0f}"
        if v >= 1:    return f"${v:,.3f}"
        return f"${v:.6f}"

    def strength_emoji(s):
        return "🔥" if s == "Strong" else "⚡" if s == "Medium" else "💫"

    # Determine if price is inside a critical zone
    zone_warning = ""
    if resistance_levels:
        nearest_res = resistance_levels[0]
        res_dist = ((nearest_res["price"] - current_price) / current_price) * 100
        if res_dist < 0.5:
            zone_warning = "⚠️ *Price is at resistance — rejection risk is high*\n\n"
    if support_levels:
        nearest_sup = support_levels[0]
        sup_dist = ((current_price - nearest_sup["price"]) / current_price) * 100
        if sup_dist < 0.5:
            zone_warning = "⚠️ *Price is at support — watch for bounce or breakdown*\n\n"

    # Volatility context
    if atr_pct > 5:
        vol_line = f"Volatility: 🔴 High ({atr_pct:.1f}% ATR) — levels may be tested fast"
    elif atr_pct > 2:
        vol_line = f"Volatility: 🟡 Moderate ({atr_pct:.1f}% ATR)"
    else:
        vol_line = f"Volatility: 🟢 Low ({atr_pct:.1f}% ATR) — levels should hold well"

    text = (
        f"📍 *BTC Key Levels — 1h (Live)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Current Price: *{fp(current_price)}*\n"
        f"{vol_line}\n\n"
        f"{zone_warning}"
    )

    # Resistance levels
    if resistance_levels:
        text += "🔴 *Resistance Zones:*\n"
        for lvl in resistance_levels[:3]:
            dist = ((lvl["price"] - current_price) / current_price) * 100
            se = strength_emoji(lvl["strength"])
            text += (
                f"{se} *{fp(lvl['price'])}*  (+{dist:.1f}%)\n"
                f"   {lvl['touches']} touches · {lvl['strength']}\n"
            )
        text += "\n"
    else:
        text += "🔴 *Resistance:* No clear zones detected above\n\n"

    # Support levels
    if support_levels:
        text += "🟢 *Support Zones:*\n"
        for lvl in support_levels[:3]:
            dist = ((current_price - lvl["price"]) / current_price) * 100
            se = strength_emoji(lvl["strength"])
            text += (
                f"{se} *{fp(lvl['price'])}*  (-{dist:.1f}%)\n"
                f"   {lvl['touches']} touches · {lvl['strength']}\n"
            )
        text += "\n"
    else:
        text += "🟢 *Support:* No clear zones detected below\n\n"

    text += (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Preview only. Run `/levels btc 1h` for the full\n"
        f"breakdown including price ranges and zone scores._\n\n"
        f"_Works on any coin: `/levels eth 4h` `/levels sol 1d`_"
    )

    return text
    
async def handle_start_levels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Loading live BTC levels…")

    await query.edit_message_text(
        text="⏳ *Fetching live BTC 1h key levels…*\n\n_Detecting support and resistance zones_",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        result = await _levels_engine.calculate_levels("BTC", "1h", max_levels=3)
        text = format_levels_preview(result)

    except Exception as e:
        print(f"⚠️ handle_start_levels error: {e}")
        text = (
            "📍 *Key Support & Resistance Levels*\n\n"
            "Live data is temporarily unavailable.\n\n"
            "*Run the command directly:*\n"
            "`/levels btc 1h` — BTC 1-hour levels\n"
            "`/levels eth 4h` — ETH 4-hour levels\n"
            "`/levels sol 1d` — SOL daily levels\n\n"
            "💡 Never enter a trade without knowing your\n"
            "nearest support and resistance first."
        )

    await query.edit_message_text(
        text=text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


async def handle_start_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    from handlers.set_alert.flow_manager import start_set_alert

    context.user_data['alert_symbol'] = None  # No pre-filled symbol, user picks
    await start_set_alert(update, context)

async def handle_start_movers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Loading live movers…")

    await query.edit_message_text(
        text="⏳ *Scanning top 100 coins right now…*",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        movers_data = await _movers_service.get_top_movers(timeframe="1h")

        if not movers_data:
            raise ValueError("No data returned")

        # Reuse the exact formatter from movers.py — no duplication
        message = format_movers_message(movers_data, "1h")

        # Add a CTA footer before the back button
        message += "_Tap /movers for 24h view and refresh controls._"

        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="start_movers_refresh"),
                InlineKeyboardButton("📊 Switch to 24h", callback_data="start_movers_24h"),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="start_back")],
        ]

        await query.edit_message_text(
            text=message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception as e:
        print(f"⚠️ handle_start_movers error: {e}")
        await query.edit_message_text(
            text=(
                "⚡ *Top Movers*\n\n"
                "Live data is temporarily unavailable.\n\n"
                "Run `/movers` directly for live results."
            ),
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        
async def handle_start_movers_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh button inside the start movers view."""
    query = update.callback_query
    await query.answer("Refreshing…")

    await query.edit_message_text(
        text="⏳ *Refreshing movers…*",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        movers_data = await _movers_service.get_top_movers(timeframe="1h")
        if not movers_data:
            raise ValueError("No data")
        message = format_movers_message(movers_data, "1h")
        message += "_Tap /movers for 24h view and refresh controls._"
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="start_movers_refresh"),
                InlineKeyboardButton("📊 Switch to 24h", callback_data="start_movers_24h"),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="start_back")],
        ]
        await query.edit_message_text(
            text=message, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        print(f"⚠️ handle_start_movers_refresh error: {e}")
        await query.edit_message_text(
            text="❌ Refresh failed. Run `/movers` directly.",
            parse_mode="Markdown", reply_markup=back_keyboard(),
        )


async def handle_start_movers_24h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to 24h view inside the start movers panel."""
    query = update.callback_query
    await query.answer("Loading 24h view…")

    await query.edit_message_text(
        text="⏳ *Loading 24h movers…*",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        movers_data = await _movers_service.get_top_movers(timeframe="24h")
        if not movers_data:
            raise ValueError("No data")
        message = format_movers_message(movers_data, "24h")
        message += "_Tap /movers for full controls._"
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="start_movers_refresh"),
                InlineKeyboardButton("📊 Switch to 1h", callback_data="start_movers"),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="start_back")],
        ]
        await query.edit_message_text(
            text=message, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        print(f"⚠️ handle_start_movers_24h error: {e}")
        await query.edit_message_text(
            text="❌ Failed to load. Run `/movers` directly.",
            parse_mode="Markdown", reply_markup=back_keyboard(),
        )

from utils.indicators import get_crypto_indicators
from handlers.analysis import (
    get_coingecko_24h,
    build_analysis_prompt,
    get_ai_analysis,
    format_analysis_response,
    COINGECKO_ID_MAP,
)

def format_analysis_preview(full_response: str) -> str:
    """
    Trim the full analysis response for the start screen preview.
    Keeps the header, AI narrative, and quick indicators.
    Strips the disclaimer and adds a CTA.
    """
    # Remove the disclaimer line — we add our own shorter one
    lines = full_response.split("\n")
    trimmed = [
        line for line in lines
        if "Disclaimer" not in line and "NOT financial advice" not in line
    ]
    text = "\n".join(trimmed).rstrip()

    text += (
        "\n\n━━━━━━━━━━━━━━━━━━━━\n"
        "_Preview. Run `/analysis btc 1h` for the full\n"
        "multi-scenario breakdown and risk factors._\n\n"
        "_Interpretation only — not financial advice._"
    )
    return text
    
async def handle_start_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Loading live BTC analysis…")

    await query.edit_message_text(
        text=(
            "⏳ *Fetching live BTC 1h AI analysis…*\n\n"
            "_Running indicators and generating interpretation_"
        ),
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        coin_id = COINGECKO_ID_MAP.get("BTC")
        if not coin_id:
            raise ValueError("BTC not found in coin map")

        # Fetch indicators and 24h stats concurrently
        indicators, stats_24h = await asyncio.gather(
            get_crypto_indicators("BTC", "1h"),
            get_coingecko_24h(coin_id),
        )

        if not indicators:
            raise ValueError("Indicators unavailable")

        # Fallback if CoinGecko 24h fails
        if not stats_24h:
            stats_24h = {
                "current_price": indicators.get("price"),
                "high_24h": "N/A",
                "low_24h": "N/A",
                "volume_24h": "N/A",
                "market_cap": "N/A",
                "price_change_24h": "N/A",
                "price_change_24h_pct": "N/A",
            }

        prompt = build_analysis_prompt(
            symbol="BTC",
            timeframe="1h",
            timeframe_display="1 Hour",
            indicators=indicators,
            stats_24h=stats_24h,
        )

        analysis_text = await get_ai_analysis(prompt)

        if not analysis_text:
            raise ValueError("AI analysis returned empty")

        full_response = format_analysis_response(
            symbol="BTC",
            timeframe="1h",
            timeframe_display="1 Hour",
            indicators=indicators,
            stats_24h=stats_24h,
            analysis_text=analysis_text,
        )

        text = format_analysis_preview(full_response)

    except Exception as e:
        print(f"⚠️ handle_start_analysis error: {e}")
        text = (
            "🧠 *AI Analysis Tools*\n\n"
            "Live data is temporarily unavailable.\n\n"
            "*Run the command directly:*\n"
            "`/analysis btc 1h` — BTC 1-hour AI analysis\n"
            "`/analysis eth 4h` — ETH 4-hour analysis\n"
            "`/analysis sol 1d` — SOL daily analysis\n\n"
            "_Interpretation only — not financial advice._"
        )

    await query.edit_message_text(
        text=text, parse_mode="Markdown", reply_markup=back_keyboard()
    )

async def handle_start_pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🚀 *Pro Plan — Advanced Tools for Serious Traders*\n\n"
        "Upgrade to unlock:\n\n"
        "🔔 *Alerts & Risk*\n"
        "• Unlimited alerts — price, %, volume, indicators\n"
        "• Watch alerts — track coin moves over time\n"
        "• `/levels` — Key support & resistance zones\n\n"
        "🧠 *AI & Market Intelligence*\n"
        "• `/setup` — Professional trade setup analyzer\n"
        "• `/analysis` — AI-powered technical analysis\n"
        "• `/aiscan` — Chart pattern detection\n"
        "• `/regime` — Market regime & risk level\n"
        "• `/hold` — Capital preservation analysis\n"
        "• `/today` — Full daily market strategy\n\n"
        "📊 *Research & Strategy*\n"
        "• `/bt` — Strategy backtesting\n"
        "• `/screen` — Scan top coins for setups\n\n"
        "💼 *Portfolio & Smart Risk*\n"
        "• Portfolio stop-loss & take-profit automation\n"
        "• Advanced portfolio risk controls\n\n"
        "Everything in one chat. No switching tools.\n\n"
        "✨ *Get Pro FREE* → `/tasks`\n"
        "💎 *Upgrade now* → `/upgrade`"
    )
    await query.edit_message_text(
        text=text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


async def handle_start_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📋 *All Commands*\n\n"
        "🔍 *Prices & Charts*\n"
        "`/btc` `/eth` `/sol` — Any coin price & stats\n"
        "`/c btc 1h` — TradingView chart\n"
        "`/trend btc 4h` — Indicators & momentum\n"
        "`/comp btc eth` — Compare two coins\n\n"
        "📊 *Market Overview*\n"
        "`/movers` `/best` `/worst` — Top movers\n"
        "`/global` — Global market overview\n"
        "`/hmap` — Top 100 heatmap\n"
        "`/news` — Latest 5 crypto news\n"
        "`/cod` — Coin of the day\n\n"
        "🔔 *Alerts*\n"
        "`/set` `/alerts` `/remove` `/removeall`\n"
        "`/watch` `/watchlist` `/removewatch`\n\n"
        "📁 *Portfolio*\n"
        "`/portfolio` `/add` `/removeasset`\n"
        "`/pflimit` `/pftarget` `/clearpf`\n\n"
        "🛠️ *Utilities*\n"
        "`/risk` — Position size calculator\n"
        "`/calc` — Crypto calculator\n"
        "`/conv` — Currency converter\n"
        "`/gas` — ETH gas fees\n"
        "`/fx` `/fxchart` — Forex rates\n\n"
        "🚀 *Pro Commands*\n"
        "`/setup` `/analysis` `/aiscan` `/hold`\n"
        "`/today` `/regime` `/levels` `/bt` `/screen`\n\n"
        "👤 *Account*\n"
        "`/upgrade` `/tasks` `/referral` `/myplan`\n"
        "`/notifications` `/support` `/privacy`"
    )
    await query.edit_message_text(
        text=text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


async def handle_start_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "👤 *My Account*\n\n"
        "`/myplan` — Check your plan & expiry date\n"
        "`/upgrade` — See Pro benefits & upgrade\n"
        "`/tasks` — Complete tasks to earn FREE Pro\n"
        "`/referral` — Get your referral link\n"
        "`/notifications` — Enable or disable alerts\n"
        "`/feedback` — Leave a review\n"
        "`/privacy` — Privacy policy & terms\n"
        "`/support` — Contact support\n\n"
        "💡 Not on Pro yet? Run `/tasks` — you can\n"
        "unlock Pro for free by completing simple tasks."
    )
    await query.edit_message_text(
        text=text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


async def handle_start_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rebuild the full live start message when user taps Back to Home."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    name = user.first_name or "Trader"

    try:
        text = await build_start_message(name)
    except Exception as e:
        print(f"❌ build_start_message failed on back: {e}")
        text = (
            "🛡️ *PricePulse*\n\n"
            "Trade less. Preserve more.\n"
            "Use the buttons below to explore."
        )

    await query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

