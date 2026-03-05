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



def build_start_message(name: str) -> str:
    """
    Return the welcome message for new (and returning) users.
    Synchronous — no fetches, no await needed.
    Caller just does:  text = build_start_message(first_name)
    """
    first = name.split()[0] if name else "there"

    return (
        f"👋 Hey {first} — welcome to *PricePulseBot*.\n\n"
        f"Most traders lose money not because they pick bad coins,\n"
        f"but because they enter too early, set bad stops, or miss\n"
        f"the moment price hits their level.\n\n"
        f"*This bot fixes all three.*\n\n"
        f"👇 Pick something to try right now:"
    )
# ============================================================================
# KEYBOARDS
# ============================================================================

def main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [   
            InlineKeyboardButton("⚡ Find Setups", callback_data="start_movers"),
            InlineKeyboardButton("📊 Market Strategy", callback_data="start_strategy"),
        ],
        [
            InlineKeyboardButton("📍 Key Levels", callback_data="start_levels"),
            InlineKeyboardButton("🔔 Set an Alert", callback_data="start_alerts"),
        ],
        [
            InlineKeyboardButton("🛡️ Hold or Exit?", callback_data="start_hold"),
            InlineKeyboardButton("🧠 Risk Calculator", callback_data="start_analysis"),
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
        # Check if this user was already referred before
        cursor.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (user_id,))
        already_referred = cursor.fetchone()

        if referred_by and not already_referred and referred_by != user_id:
            cursor.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            """, (referred_by, user_id))

            init_task_progress_with_conn(user_id, conn)
            init_task_progress_with_conn(referred_by, conn)

            cursor.execute("""
                UPDATE task_progress
                SET referral_count = referral_count + 1
                WHERE user_id = ?
            """, (referred_by,))

        # Register user if not exists
        cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, username, plan)
            VALUES (?, ?, 'free')
        """, (user_id, username))

        is_new_user = cursor.rowcount > 0
        if is_new_user:
            print(f"🆕 New user joined: {user_id} (@{username})")

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"❌ Database error in start_command: {e}")

    finally:
        conn.close()

    # ── Activate trial for new users ──────────────────────────────────
    trial_started = False
    if is_new_user:
        try:
            from models.user import start_trial
            trial_started = start_trial(user_id)
        except Exception as e:
            print(f"❌ Failed to start trial for {user_id}: {e}")

    # 🔔 Notify admin about new user
    if is_new_user:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "👤 *New User Joined!*\n"
                    f"ID: `{user_id}`\n"
                    f"Username: @{username or 'N/A'}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ Failed to notify admin: {e}")

    # Build live start message
    try:
        text = build_start_message(name)
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

    # ── Trial welcome message ─────────────────────────────────────────
    if trial_started:
        from datetime import datetime, timedelta, timezone
        expiry_date = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%B %d")
        await update.message.reply_text(
            "🎁 *You have 5 days of free Pro access.*\n\n"
            "Every feature. No restrictions. No card needed.\n\n"
            "Try /setup, /risk, /screen — everything is unlocked.\n\n"
            "After 5 days you keep free tier access.\n"
            f"Your trial expires: *{expiry_date}*\n\n"
            "Upgrade anytime with /upgrade.",
            parse_mode="Markdown",
        )
# ============================================================================
# CALLBACK HANDLERS
# All callbacks use the "start_" prefix to prevent collisions with other
# handlers registered elsewhere in the project.
# ============================================================================

"""
Replaces the duplicated fetch/calculate logic in handle_start_hold
with direct imports from handlers/hold.py.

What was removed:
  - fetch_hold_btc_data()         → replaced by hold.py's fetchers
  - _hold_calculate_sma()         → replaced by hold.py's calculate_sma()
  - _hold_calculate_rsi()         → replaced by hold.py's calculate_rsi()
  - _hold_detect_rsi_divergence() → replaced by hold.py's detect_rsi_divergence()
  - _hold_detect_regime()         → replaced by hold.py's detect_market_regime()
  - _hold_volume_capitulation()   → replaced by hold.py's detect_volume_capitulation()
  - run_btc_hold_analysis()       → replaced by hold.py's analyze_hold_decision()

What was kept:
  - format_hold_preview()  — compact preview format for the start screen
  - handle_start_hold()    — the callback handler (now much simpler)
"""

import asyncio
from telegram import Update
from telegram.ext import ContextTypes

# ── Import everything we need from the canonical hold.py ─────────────────────
from handlers.hold import (
    fetch_coin_price_data,
    fetch_coin_details,
    fetch_fear_greed_index,
    fetch_btc_data,
    analyze_hold_decision,
    TOP_100_COINS,
)


# ── back_keyboard assumed to be defined/imported elsewhere in your start file ─
# from handlers.start import back_keyboard   (keep your existing import)


# ============================================================================
# COMPACT PREVIEW FORMATTER  (start-screen only — not the full /hold output)
# ============================================================================

def format_hold_preview(a: dict) -> str:
    """
    Compact BTC hold preview for the start screen.
    Shows verdict, key signals, and a CTA to run /hold for the full report.
    """
    price   = a["current_price"]
    verdict = a["verdict"]
    fg      = a.get("fear_greed")
    fg_str  = f"{fg[0]}/100 ({fg[1]})" if fg else "N/A"

    regime_emoji = "🟢" if a["regime"] == "Bull" else "🔴" if a["regime"] == "Bear" else "🟡"

    # RSI line
    rsi_val = a.get("rsi")
    if rsi_val:
        if a.get("bullish_divergence"):
            rsi_line = f"RSI {rsi_val:.0f} — Bullish divergence 📈"
        elif rsi_val < 30:
            rsi_line = f"RSI {rsi_val:.0f} — Oversold ⚠️"
        elif rsi_val > 70:
            rsi_line = f"RSI {rsi_val:.0f} — Overbought ⚠️"
        else:
            rsi_line = f"RSI {rsi_val:.0f} — Neutral"
    else:
        rsi_line = "RSI — N/A"

    # Top 2 signals each side  (hold.py stores them under "signals" key)
    signals     = a.get("signals", {})
    bull_list   = signals.get("bullish", [])
    bear_list   = signals.get("bearish", [])
    bull_lines  = "\n".join(f"  ✅ {s}" for s in bull_list[:2]) or "  —"
    bear_lines  = "\n".join(f"  ❌ {s}" for s in bear_list[:2]) or "  —"

    sma50 = a.get("sma_50")
    if sma50:
        if "EXIT" in verdict:
            inv_line = f"  • Price closes above ${sma50 * 1.05:,.0f} with volume"
        else:
            inv_line = f"  • Price breaks below ${sma50 * 0.95:,.0f}"
    else:
        inv_line = "  • Market regime shifts"

    price_vs_50   = a.get("price_vs_50", 0)
    confirmations = a.get("confirmations", 0)

    return (
        f"🛡️ *BTC Hold Analysis — Live*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 BTC Price: *${price:,.0f}*\n"
        f"🎯 Verdict: *{verdict}*\n"
        f"📊 Confidence: *{a['confidence']:.0f}%*"
        f"  |  Confirmations: *{confirmations}/3*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📉 *30-Day Outlook:*\n"
        f"  Decline probability: *{a['prob_decline']:.0f}%*\n"
        f"  Downside target: *${a['expected_low']:,.0f}*\n"
        f"  ATH drawdown: *{a['drawdown_ath']}%*\n\n"
        f"📊 *Signal Snapshot:*\n"
        f"  {regime_emoji} Regime: *{a['regime']}*\n"
        f"  {'✅' if price_vs_50 > 0 else '❌'} "
        f"50MA: *{'Above' if price_vs_50 > 0 else 'Below'} "
        f"by {abs(price_vs_50)}%*\n"
        f"  📈 {rsi_line}\n"
        f"  😱 Fear & Greed: *{fg_str}*\n\n"
        f"✅ *For:*\n{bull_lines}\n\n"
        f"❌ *Against:*\n{bear_lines}\n\n"
        f"🔄 *Analysis flips if:*\n{inv_line}\n\n"
        f"💎 Preservation Score: *{a['preservation_score']}/10*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Preview only. Run `/hold btc` for the full\n"
        f"multi-confirmation analysis with re-entry\n"
        f"zones, timeframe selection, and all signals._\n\n"
        f"_Analysis only — not financial advice._"
    )


# ============================================================================
# CALLBACK HANDLER
# ============================================================================

async def handle_start_hold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback for the 'BTC Hold Analysis' button on the start screen.
    Fetches BTC data using hold.py's own fetchers, runs hold.py's own
    analysis engine, then renders a compact preview.
    """
    query = update.callback_query
    await query.answer("Loading live BTC analysis…")

    await query.edit_message_text(
        text=(
            "⏳ *Fetching live BTC hold analysis…*\n\n"
            "_Running conservative multi-confirmation analysis_"
        ),
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    try:
        coingecko_id = TOP_100_COINS.get("BTC", "bitcoin")
        days         = 180   # same depth used by /hold btc 30d

        # Reuse hold.py's fetchers — no duplicate network code
        price_data, coin_details, btc_prices, fear_greed = await asyncio.gather(
            fetch_coin_price_data(coingecko_id, days),
            fetch_coin_details(coingecko_id),
            fetch_btc_data(days),
            fetch_fear_greed_index(),
        )

        if not price_data or not coin_details:
            raise ValueError("CoinGecko returned no data for BTC")

        prices  = [p[1] for p in price_data.get("prices", [])]
        volumes = [v[1] for v in price_data.get("total_volumes", [])]

        if len(prices) < 50:
            raise ValueError(f"Only {len(prices)} price points returned — need 50+")

        market_data   = coin_details.get("market_data", {})
        current_price = market_data.get("current_price", {}).get("usd") or prices[-1]
        market_cap_rank = coin_details.get("market_cap_rank", 1)

        # Reuse hold.py's analysis engine directly
        analysis = analyze_hold_decision(
            symbol          = "BTC",
            current_price   = current_price,
            prices          = prices,
            volumes         = volumes,
            btc_prices      = btc_prices,
            market_data     = market_data,
            market_cap_rank = market_cap_rank,
            fear_greed      = fear_greed,
            timeframe_days  = 30,
        )

        # Add current_price to analysis dict so format_hold_preview can read it
        analysis["current_price"] = current_price

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
        text=text,
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

# ============================================================================
# SETUP PREVIEW — fetches live BTC 1h data for the Market Strategy button
# ============================================================================

async def handle_start_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Loading live BTC setup…")

    await query.edit_message_text(
        text="⏳ <b>Fetching live BTC 1h setup analysis…</b>\n\n<i>Calculating indicators and key levels</i>",
        parse_mode="HTML",
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
            "📊 <b>BTC Setup Analysis</b>\n\n"
            "Live data is temporarily unavailable.\n\n"
            "<b>Run the full command directly:</b>\n"
            "<code>/setup btc 1h</code> — BTC 1-hour setup\n"
            "<code>/setup btc 4h</code> — BTC 4-hour setup\n"
            "<code>/setup eth 1h</code> — ETH 1-hour setup\n\n"
            "<i>Not financial advice.</i>"
        )

    await query.edit_message_text(
        text=text, parse_mode="HTML", reply_markup=back_keyboard()
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

"""
Replaces handle_start_movers / handle_start_movers_refresh / handle_start_movers_24h
with a single entry point that opens the /screen strategy selector directly.

All the real work (timeframe selection, scanning, results, back button) is
already handled by the existing callbacks in handlers/screener.py — we just
need to show the strategy list and let screener_callback take over from there.
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from models.user import get_user_plan
from utils.auth import is_pro_plan

# FIX: Import _get_overall_cache_status instead of is_cache_fresh.
# is_cache_fresh() with no args only checked 1h, showing 🟢 even when
# 4h/1d caches were empty. _get_overall_cache_status checks all 3 priority
# timeframes and returns an accurate status string.
from handlers.screener import STRATEGIES, _get_overall_cache_status


async def handle_start_movers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Replaces the old top-movers panel on the start screen.
    Now opens the Multi-Coin Screener strategy selector directly.

    From here the user clicks a strategy → timeframe → results,
    all handled by the existing screener_callback in screener.py.
    The ⬅️ Back button inside the screener returns to strategy list,
    which is fine UX from the start screen too.
    """
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    plan    = get_user_plan(user_id)
    is_pro  = is_pro_plan(plan)

    if not is_pro:
        await query.edit_message_text(
            "🔒 *Multi-Coin Screener — Pro Only*\n\n"
            "Scan 100 coins in real-time against 5 technical strategies:\n\n"
            "• Strong Bounce Setup\n"
            "• Breakout with Momentum\n"
            "• Reversal After Sell-Off\n"
            "• Trend Turning Bullish\n"
            "• Deep Pullback Opportunity\n\n"
            "👉 /upgrade to unlock",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 Upgrade to Pro", callback_data="upgrade_menu"),
                InlineKeyboardButton("⬅️ Back", callback_data="start_back"),
            ]]),
        )
        return

    # FIX: Replaced is_cache_fresh() with _get_overall_cache_status()
    cache_status = _get_overall_cache_status()

    keyboard = [
        [InlineKeyboardButton(strategy["name"], callback_data=f"screener_{key}")]
        for key, strategy in STRATEGIES.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="start_back")])

    await query.edit_message_text(
        f"📊 *Multi-Coin Screener* {cache_status}\n\n"
        "Pick a strategy to scan 100 coins right now:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
"""
Replaces handle_start_analysis with handle_start_risk.

The old handler fetched live BTC indicators, called the AI, and showed
a trimmed analysis preview — all async work that could fail.

The new handler just launches the /risk conversation flow immediately.
No fetches, no AI call, instant response.

The only subtlety: risk_command() expects update.message, but a callback
query doesn't have one. We initialise the flow state directly here and
send the first step message ourselves, exactly as risk_command() would.
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from models.user import get_user_plan
from utils.auth import is_pro_plan

# Import the private step helpers so we don't duplicate the flow logic
from handlers.risk import _fmt, _leverage_label


async def handle_start_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Renamed entry point — kept as handle_start_analysis so you don't need
    to change your callback registration. Opens the /risk calculator.
    """
    query   = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    plan   = get_user_plan(user_id)
    is_pro = is_pro_plan(plan)

    # Initialise the risk flow — same state shape as risk_command()
    context.user_data["risk_flow"] = {
        "active": True,
        "step":   "account_size",
        "is_pro": is_pro,
        "data":   {},
    }

    # edit_message_text closes the inline keyboard cleanly, then we send
    # the first step as a new message so risk_message_handler can reply to it.
    await query.edit_message_text(
        text="💰 *Starting Risk Calculator…*",
        parse_mode=ParseMode.MARKDOWN,
    )

    await query.message.reply_text(
        "🤖 *AI Risk Calculator*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "I'll calculate optimal position sizing and\n"
        "show you liquidation prices, real exposure,\n"
        "and an AI risk assessment.\n\n"
        "*Step 1 of 5:* Account Size\n\n"
        "💵 What's your total trading account balance?\n\n"
        "*Examples:*\n"
        "`500` → $500\n"
        "`5000` → $5,000\n"
        "`25000` → $25,000\n\n"
        "_Type /cancel to exit_",
        parse_mode=ParseMode.MARKDOWN,
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
        text = build_start_message(name)
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

