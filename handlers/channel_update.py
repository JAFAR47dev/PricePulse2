"""
handlers/channel_update.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Admin-only command that composes and sends a rich market update
to a Telegram channel.

/sendupdate — shows a control panel with 4 buttons:
  [☀️ Preview Morning]   [🌙 Preview Evening]
  [⏰ Schedule Morning]  [⏰ Schedule Evening]

Preview buttons send the post to the admin's DM immediately.
Schedule buttons ask for a time (HH:MM UTC), then register a
daily JobQueue job that fires at that time every day.

Environment variables required:
  CHANNEL_ID           — e.g. "@pricepulse_updates" or numeric "-1001234567890"
  ADMIN_IDS            — comma-separated Telegram user IDs allowed to run this
  COINGECKO_API_KEY    — optional, raises rate limits
  OPENROUTER_API_KEY   — for AI narrative generation

Architecture:
  1. fetch_all_channel_data()   — all API calls run concurrently
  2. enrich_data()              — derive scores, EMAs, RSI, level breaks
  3. build_ai_prompt()          — structured prompt from enriched data
  4. get_ai_narrative()         — OpenRouter call → 3-sentence take
  5. format_channel_post()      — assemble final Telegram message + single button
  6. channel_update_command()   — shows control panel, admin-gated
  7. Callback handlers          — preview and schedule flows
"""

import os
import asyncio
import logging
import json
import math
from datetime import datetime, timezone
from typing import Optional

import httpx
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CHANNEL_ID         = os.getenv("CHANNEL_ID", "")
COINGECKO_API_KEY  = os.getenv("COINGECKO_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BOT_USERNAME       = os.getenv("BOT_USERNAME", "your_bot")  # without @

_raw_admin_ids     = os.getenv("ADMIN_ID", "")
ADMIN_IDS: set[int] = {
    int(x.strip()) for x in _raw_admin_ids.split(",") if x.strip().isdigit()
}

# Score persistence — keeps previous score in memory for direction comparison.
# Survives for the process lifetime; good enough for twice-daily posts.
_score_history: list[int] = []

# Tracks pending schedule inputs: {user_id: "morning" | "evening"}
_pending_schedule: dict[int, str] = {}

# ── CoinGecko helpers ─────────────────────────────────────────────────────────

def _cg_headers() -> dict:
    h = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        h["x-cg-demo-api-key"] = COINGECKO_API_KEY
    return h


# ============================================================================
# SECTION 1 — DATA FETCHERS  (all async, run concurrently)
# ============================================================================

async def _fetch_prices(client: httpx.AsyncClient) -> dict:
    """BTC + ETH spot price and 24h change."""
    out = {}
    try:
        r = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            headers=_cg_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            d = r.json()
            out["btc_price"]  = d.get("bitcoin", {}).get("usd")
            out["btc_change"] = d.get("bitcoin", {}).get("usd_24h_change")
            out["eth_price"]  = d.get("ethereum", {}).get("usd")
            out["eth_change"] = d.get("ethereum", {}).get("usd_24h_change")
    except Exception as e:
        logger.warning(f"[channel] price fetch: {e}")
    return out


async def _fetch_global(client: httpx.AsyncClient) -> dict:
    """Market cap, volume, BTC dominance, 24h change."""
    out = {}
    try:
        r = await client.get(
            "https://api.coingecko.com/api/v3/global",
            headers=_cg_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            g = r.json().get("data", {})
            out["total_market_cap"]    = g.get("total_market_cap", {}).get("usd")
            out["market_cap_change"]   = g.get("market_cap_change_percentage_24h_usd")
            out["btc_dominance"]       = g.get("market_cap_percentage", {}).get("btc")
            out["total_volume"]        = g.get("total_volume", {}).get("usd")
    except Exception as e:
        logger.warning(f"[channel] global fetch: {e}")
    return out


async def _fetch_fear_greed(client: httpx.AsyncClient) -> dict:
    """Fear & Greed index."""
    out = {}
    try:
        r = await client.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=8,
        )
        if r.status_code == 200:
            item = r.json().get("data", [{}])[0]
            out["fear_greed"]       = int(item.get("value", 50))
            out["fear_greed_label"] = item.get("value_classification", "Neutral")
    except Exception as e:
        logger.warning(f"[channel] fear/greed fetch: {e}")
    return out


async def _fetch_movers(client: httpx.AsyncClient) -> dict:
    """Top gainer and top loser from CoinGecko top-100."""
    out = {}
    try:
        r = await client.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "24h",
            },
            headers=_cg_headers(),
            timeout=12,
        )
        if r.status_code == 200:
            coins = r.json()
            if coins:
                best = max(coins, key=lambda c: c.get("price_change_percentage_24h") or -999)
                worst = min(coins, key=lambda c: c.get("price_change_percentage_24h") or 999)
                out["top_gainer_name"]   = best.get("name")
                out["top_gainer_symbol"] = (best.get("symbol") or "").upper()
                out["top_gainer_change"] = best.get("price_change_percentage_24h")
                out["top_loser_name"]    = worst.get("name")
                out["top_loser_symbol"]  = (worst.get("symbol") or "").upper()
                out["top_loser_change"]  = worst.get("price_change_percentage_24h")
    except Exception as e:
        logger.warning(f"[channel] movers fetch: {e}")
    return out


async def _fetch_btc_ohlcv(client: httpx.AsyncClient) -> dict:
    """
    BTC 4h candles (last 60) for EMA20/50, RSI-14, and level-break detection.
    CoinGecko /market_chart with days=14 gives ~4h granularity on the free tier.
    """
    out = {}
    try:
        r = await client.get(
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
            params={"vs_currency": "usd", "days": 90, "interval": "daily"},
            headers=_cg_headers(),
            timeout=12,
        )
        if r.status_code == 200:
            prices  = [p[1] for p in r.json().get("prices", [])]
            volumes = [v[1] for v in r.json().get("total_volumes", [])]
            out["btc_prices_4h"]  = prices
            out["btc_volumes_4h"] = volumes
    except Exception as e:
        logger.warning(f"[channel] BTC OHLCV fetch: {e}")
    return out


async def fetch_all_channel_data() -> dict:
    """
    Run all network fetches concurrently.
    Returns a single merged dict with all raw data.
    """
    async with httpx.AsyncClient() as client:
        (
            prices,
            global_data,
            fg,
            movers,
            ohlcv,
        ) = await asyncio.gather(
            _fetch_prices(client),
            _fetch_global(client),
            _fetch_fear_greed(client),
            _fetch_movers(client),
            _fetch_btc_ohlcv(client),
        )

    return {
        **prices,
        **global_data,
        **fg,
        **movers,
        **ohlcv,
    }


# ============================================================================
# SECTION 2 — INDICATOR CALCULATIONS
# ============================================================================

def _ema(prices: list[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    k   = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val


def _rsi(prices: list[float], period: int = 14) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100.0 if al == 0 else 100 - (100 / (1 + ag / al))


def _market_score(raw: dict) -> int:
    """Same conservative scoring logic used in the start message."""
    score = 50
    fg = raw.get("fear_greed")
    if fg is not None:
        if fg <= 15:   score -= 25
        elif fg <= 25: score -= 18
        elif fg <= 35: score -= 10
        elif fg >= 80: score += 18
        elif fg >= 65: score += 10
        elif fg >= 55: score += 5

    change = raw.get("market_cap_change")
    if change is not None:
        if change < -4:    score -= 18
        elif change < -2:  score -= 10
        elif change < -0.5: score -= 5
        elif change > 4:   score += 15
        elif change > 2:   score += 8
        elif change > 0.5: score += 4

    btc_change = raw.get("btc_change")
    if btc_change is not None:
        if btc_change < -5:  score -= 12
        elif btc_change < -2: score -= 6
        elif btc_change > 4:  score += 10
        elif btc_change > 2:  score += 5

    return max(0, min(100, score))


def _regime(score: int) -> str:
    if score >= 65: return "Bull"
    if score >= 48: return "Neutral"
    if score >= 30: return "Bear"
    return "Extreme Bear"


def _ema_position(price: float, ema20: Optional[float], ema50: Optional[float]) -> str:
    """
    Returns a plain-English string describing price vs EMAs.
    e.g. "above EMA20 and EMA50" / "above EMA20, below EMA50"
    """
    if ema20 is None and ema50 is None:
        return "EMA data unavailable"
    parts = []
    if ema20 is not None:
        parts.append(f"{'above' if price > ema20 else 'below'} EMA20")
    if ema50 is not None:
        parts.append(f"{'above' if price > ema50 else 'below'} EMA50")
    return " and ".join(parts)


def _detect_level_break(prices: list[float]) -> Optional[str]:
    """
    Simplified level-break detector.
    Looks at the last 14 candles — if price has crossed a recent
    swing high or swing low in the last 2 candles, flags it.
    Returns a string like "broke above $97,400 resistance" or None.
    """
    if len(prices) < 10:
        return None

    lookback = prices[-14:]
    current  = prices[-1]
    prev     = prices[-2]

    recent_high = max(lookback[:-2])
    recent_low  = min(lookback[:-2])

    if prev < recent_high and current > recent_high:
        return f"broke above ${recent_high:,.0f} resistance"
    if prev > recent_low and current < recent_low:
        return f"broke below ${recent_low:,.0f} support"
    return None


def _fmt_mcap(n) -> str:
    if n is None: return "N/A"
    if n >= 1e12: return f"${n/1e12:.2f}T"
    if n >= 1e9:  return f"${n/1e9:.1f}B"
    return f"${n:,.0f}"


# ============================================================================
# SECTION 3 — DATA ENRICHMENT
# ============================================================================

def enrich_data(raw: dict) -> dict:
    """
    Derive all calculated fields from raw API data.
    Returns enriched dict ready for prompt + formatter.
    """
    prices_4h = raw.get("btc_prices_4h", [])
    btc_price = raw.get("btc_price") or (prices_4h[-1] if prices_4h else None)

    ema20 = _ema(prices_4h, 20) if len(prices_4h) >= 20 else None
    ema50 = _ema(prices_4h, 50) if len(prices_4h) >= 50 else None
    rsi   = _rsi(prices_4h, 14) if len(prices_4h) >= 15 else None

    score  = _market_score(raw)
    regime = _regime(score)

    # Score direction vs last recorded score
    score_direction = None
    score_prev      = None
    if _score_history:
        score_prev      = _score_history[-1]
        diff            = score - score_prev
        if diff >= 5:
            score_direction = f"up from {score_prev} → {score}"
        elif diff <= -5:
            score_direction = f"down from {score_prev} → {score}"
        else:
            score_direction = f"steady at {score}"
    _score_history.append(score)
    if len(_score_history) > 10:
        _score_history.pop(0)

    # EMA position string
    ema_pos = _ema_position(btc_price, ema20, ema50) if btc_price else "unavailable"

    # Level break
    level_break = _detect_level_break(prices_4h) if prices_4h else None

    # Screener summary
    screener_counts = raw.get("screener_counts", {})
    total_hits      = sum(screener_counts.values())
    top_strategy    = max(screener_counts, key=screener_counts.get) if screener_counts else None
    top_strategy_name = SCREENER_STRATEGIES.get(top_strategy, "") if top_strategy else ""
    top_strategy_hits = screener_counts.get(top_strategy, 0) if top_strategy else 0

    return {
        # Raw pass-through
        "btc_price":           btc_price,
        "btc_change":          raw.get("btc_change"),
        "eth_price":           raw.get("eth_price"),
        "eth_change":          raw.get("eth_change"),
        "fear_greed":          raw.get("fear_greed"),
        "fear_greed_label":    raw.get("fear_greed_label", "Neutral"),
        "btc_dominance":       raw.get("btc_dominance"),
        "total_market_cap":    raw.get("total_market_cap"),
        "market_cap_change":   raw.get("market_cap_change"),
        "top_gainer_name":     raw.get("top_gainer_name"),
        "top_gainer_symbol":   raw.get("top_gainer_symbol"),
        "top_gainer_change":   raw.get("top_gainer_change"),
        "top_loser_name":      raw.get("top_loser_name"),
        "top_loser_symbol":    raw.get("top_loser_symbol"),
        "top_loser_change":    raw.get("top_loser_change"),
        # Derived
        "score":               score,
        "regime":              regime,
        "score_direction":     score_direction,
        "score_prev":          score_prev,
        "ema20":               ema20,
        "ema50":               ema50,
        "rsi_4h":              round(rsi, 1) if rsi else None,
        "ema_position":        ema_pos,
        "level_break":         level_break,
    }


# ============================================================================
# SECTION 4 — AI NARRATIVE
# ============================================================================

def build_ai_prompt(data: dict, tone: str = "morning") -> str:
    btc_price  = data.get("btc_price")
    btc_change = data.get("btc_change")
    eth_change = data.get("eth_change")
    fg         = data.get("fear_greed")
    fg_label   = data.get("fear_greed_label", "")
    score      = data.get("score")
    regime     = data.get("regime")
    score_dir  = data.get("score_direction") or f"at {score}"
    dom        = data.get("btc_dominance")
    rsi        = data.get("rsi_4h")
    ema_pos    = data.get("ema_position", "")
    level_break = data.get("level_break")
    total_hits  = data.get("screener_total_hits", 0)
    top_strat   = data.get("top_strategy_name", "")
    top_hits    = data.get("top_strategy_hits", 0)
    gainer      = data.get("top_gainer_name")
    gainer_pct  = data.get("top_gainer_change")
    loser       = data.get("top_loser_name")
    loser_pct   = data.get("top_loser_change")
    mcap_change = data.get("market_cap_change")

    tone_instruction = (
        "Morning post: tell traders exactly what they're walking into today and what price to watch."
        if tone == "morning" else
        "Evening post: tell traders what actually mattered today and what to hold overnight."
    )

    level_line = f"- BTC level break: {level_break}" if level_break else "- No major BTC level break in last 24h"

    return f"""You are a crypto trader writing a 3-sentence Telegram channel update. You talk like a desk trader texting a colleague — short, specific, numbers-first. No fluff.

MARKET DATA:
- BTC: ${btc_price:,.0f} ({btc_change:+.1f}%)
- ETH: {eth_change:+.1f}%
- Market cap 24h: {mcap_change:+.1f}%
- Fear & Greed: {fg}/100 ({fg_label})
- Market score: {score_dir}
- Regime: {regime}
- BTC dominance: {dom:.1f}%
- BTC RSI (daily): {rsi}
- BTC vs EMAs: {ema_pos}
{level_line}
- Top gainer: {gainer} +{gainer_pct:.1f}%
- Top loser: {loser} {loser_pct:.1f}%

Task: {tone_instruction}

Write exactly 3 sentences. Start sentence 1 with a price or number. Sentence 2 names a specific level or signal. Sentence 3 is one clear thing to do or watch — do NOT end with "dive into your platform", "consider strategies", or any generic CTA.

BANNED phrases: "keep a close eye", "dive into", "consider potential", "trading platform", "market is experiencing", "it's important to", "exercise caution".

Max 75 words. No emojis. No bullet points."""


async def get_ai_narrative(prompt: str) -> Optional[str]:
    if not OPENROUTER_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistralai/mixtral-8x7b-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 180,
                    "temperature": 0.45,
                },
            )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        logger.warning(f"[channel AI] {r.status_code}")
    except Exception as e:
        logger.warning(f"[channel AI] {e}")
    return None


def fallback_narrative(data: dict) -> str:
    """Rule-based narrative when AI is unavailable."""
    score  = data.get("score", 50)
    regime = data.get("regime", "Neutral")
    fg     = data.get("fear_greed", 50)
    rsi    = data.get("rsi_4h")
    break_ = data.get("level_break")

    if regime == "Bull" and score > 65:
        line1 = f"Market structure is bullish with score at {score}/100 and momentum building."
    elif regime in ("Bear", "Extreme Bear"):
        line1 = f"Bears are in control — score dropped to {score}/100 and risk is elevated."
    else:
        line1 = f"Market is ranging with no clear directional edge — score at {score}/100."

    if rsi and rsi > 70:
        line2 = f"BTC 4h RSI at {rsi} is overbought — watch for a pullback before entering longs."
    elif rsi and rsi < 30:
        line2 = f"BTC 4h RSI at {rsi} is oversold — potential bounce zone but wait for confirmation."
    elif break_:
        line2 = f"BTC just {break_} — this is the level to watch for follow-through."
    else:
        line2 = f"Fear & Greed at {fg}/100 ({data.get('fear_greed_label', '')}) — sentiment is {'cautious' if fg < 50 else 'stretched'}."

    gainer = data.get("top_gainer_symbol", "")
    gainer_pct = data.get("top_gainer_change") or 0
    line3 = f"{gainer} is leading the market today at +{gainer_pct:.1f}% — open the bot to dig into the setup."

    return f"{line1} {line2} {line3}"


# ============================================================================
# SECTION 5 — POST FORMATTER
# ============================================================================

def _score_emoji(score: int) -> str:
    if score >= 65: return "🟢"
    if score >= 48: return "🟡"
    if score >= 30: return "🔴"
    return "🔴🔴"


def _fg_emoji(fg: int) -> str:
    if fg <= 20:  return "😱"
    if fg <= 35:  return "😨"
    if fg <= 50:  return "😐"
    if fg <= 65:  return "🙂"
    return "🤑"


def format_channel_post(data: dict, narrative: str, tone: str = "morning") -> tuple[str, InlineKeyboardMarkup]:
    """
    Returns (message_text, reply_markup).
    Single button: Open PricePulse.
    """
    now      = datetime.now(timezone.utc).strftime("%a %d %b · %H:%M UTC")
    tone_hdr = "☀️ Morning Setup" if tone == "morning" else "🌙 Evening Wrap"

    btc_price  = data.get("btc_price", 0)
    btc_change = data.get("btc_change") or 0
    eth_price  = data.get("eth_price", 0)
    eth_change = data.get("eth_change") or 0
    fg         = data.get("fear_greed", 50)
    fg_label   = data.get("fear_greed_label", "")
    score      = data.get("score", 50)
    regime     = data.get("regime", "")
    dom        = data.get("btc_dominance") or 0
    mcap       = data.get("total_market_cap")
    mcap_chg   = data.get("market_cap_change") or 0
    rsi        = data.get("rsi_4h")
    ema_pos    = data.get("ema_position", "")
    level_break = data.get("level_break")
    score_dir  = data.get("score_direction") or f"at {score}"
    gainer_sym = data.get("top_gainer_symbol", "")
    gainer_pct = data.get("top_gainer_change") or 0
    loser_sym  = data.get("top_loser_symbol", "")
    loser_pct  = data.get("top_loser_change") or 0

    btc_arrow  = "▲" if btc_change >= 0 else "▼"
    eth_arrow  = "▲" if eth_change >= 0 else "▼"
    mcap_arrow = "▲" if mcap_chg >= 0 else "▼"

    level_line = f"⚡ BTC just *{level_break}*" if level_break else None

    lines = [
        f"*PricePulse · {tone_hdr}*",
        f"_{now}_",
        "",
        f"_{narrative}_",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"`BTC` *${btc_price:,.0f}*  {btc_arrow} {abs(btc_change):.1f}%",
        f"`ETH` *${eth_price:,.0f}*  {eth_arrow} {abs(eth_change):.1f}%",
        f"`Mkt` *{_fmt_mcap(mcap)}*  {mcap_arrow} {abs(mcap_chg):.1f}%  ·  Dom {dom:.1f}%",
        "",
        f"{_fg_emoji(fg)} Fear & Greed  *{fg}/100*  ({fg_label})",
        f"{_score_emoji(score)} Score *{score_dir}*  ·  Regime *{regime}*",
        f"📊 RSI *{rsi}*  ·  BTC {ema_pos}",
        level_line,
        "",
        f"🚀 *{gainer_sym}*  +{gainer_pct:.1f}%  ·  top gainer",
        f"💀 *{loser_sym}*  {loser_pct:.1f}%  ·  top loser",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "_Analysis only — not financial advice._",
    ]

    text = "\n".join(l for l in lines if l is not None)

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🤖 Open PricePulse",
            url=f"https://t.me/{BOT_USERNAME}",
        )
    ]])

    return text, markup


# ============================================================================
# SECTION 6 — CONTROL PANEL  (/sendupdate shows 4 buttons)
# ============================================================================

def _control_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("☀️ Preview Morning", callback_data="cu_preview_morning"),
            InlineKeyboardButton("🌙 Preview Evening", callback_data="cu_preview_evening"),
        ],
        [
            InlineKeyboardButton("⏰ Schedule Morning", callback_data="cu_schedule_morning"),
            InlineKeyboardButton("⏰ Schedule Evening", callback_data="cu_schedule_evening"),
        ],
    ])


async def channel_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sendupdate — admin-only control panel."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return  # silent fail

    # Show current schedule status if jobs exist
    jq = context.job_queue
    morning_jobs = jq.get_jobs_by_name("channel_morning")
    evening_jobs = jq.get_jobs_by_name("channel_evening")

    morning_status = f"✅ {morning_jobs[0].next_t.strftime('%H:%M')} UTC" if morning_jobs else "not set"
    evening_status = f"✅ {evening_jobs[0].next_t.strftime('%H:%M')} UTC" if evening_jobs else "not set"

    await update.message.reply_text(
        "📡 *Channel Update Control Panel*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"☀️ Morning schedule: *{morning_status}*\n"
        f"🌙 Evening schedule: *{evening_status}*\n\n"
        "Preview sends the post to your DM.\n"
        "Schedule sets a daily recurring post to the channel.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_control_panel_keyboard(),
    )


# ============================================================================
# SECTION 7 — PREVIEW CALLBACKS
# ============================================================================

async def _send_preview(query, context: ContextTypes.DEFAULT_TYPE, tone: str):
    """Fetch, generate, and send a preview post to the admin's DM."""
    await query.edit_message_text(
        f"⏳ Generating *{tone}* preview…",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        raw       = await fetch_all_channel_data()
        data      = enrich_data(raw)
        prompt    = build_ai_prompt(data, tone)
        narrative = await get_ai_narrative(prompt) or fallback_narrative(data)
        text, markup = format_channel_post(data, narrative, tone)

        await context.bot.send_message(
            chat_id      = query.from_user.id,
            text         = text,
            parse_mode   = ParseMode.MARKDOWN,
            reply_markup = markup,
            disable_web_page_preview = True,
        )
        await query.edit_message_text(
            f"✅ *{tone.title()} preview* sent to your DM.\n\n"
            f"Score: {data['score']}/100  ·  Regime: {data['regime']}",
            parse_mode   = ParseMode.MARKDOWN,
            reply_markup = _control_panel_keyboard(),
        )
    except Exception as e:
        logger.exception(f"[channel preview] {e}")
        await query.edit_message_text(
            f"❌ Preview failed: `{e}`",
            parse_mode   = ParseMode.MARKDOWN,
            reply_markup = _control_panel_keyboard(),
        )


async def cu_preview_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _send_preview(update.callback_query, context, "morning")


async def cu_preview_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _send_preview(update.callback_query, context, "evening")


# ============================================================================
# SECTION 8 — SCHEDULE CALLBACKS  (ask for time, then register job)
# ============================================================================

async def cu_schedule_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    _pending_schedule[user_id] = "morning"
    await query.edit_message_text(
        "☀️ *Schedule Morning Post*\n\n"
        "Reply with the time you want the morning post sent every day.\n\n"
        "Format: `HH:MM` in UTC\n"
        "Examples: `08:00`  `07:30`  `09:00`\n\n"
        "_Type /cancelschedule to go back._",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cu_schedule_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    _pending_schedule[user_id] = "evening"
    await query.edit_message_text(
        "🌙 *Schedule Evening Post*\n\n"
        "Reply with the time you want the evening post sent every day.\n\n"
        "Format: `HH:MM` in UTC\n"
        "Examples: `20:00`  `18:30`  `21:00`\n\n"
        "_Type /cancelschedule to go back._",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cu_schedule_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Reads a HH:MM reply from the admin after tapping a schedule button.
    Cancels any existing job for that tone, registers a new daily job.
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        return
    if user_id not in _pending_schedule:
        return

    text = update.message.text.strip()

    if text.lower() == "/cancelschedule":
        _pending_schedule.pop(user_id, None)
        await update.message.reply_text(
            "↩️ Schedule cancelled.",
            reply_markup=_control_panel_keyboard(),
        )
        return

    # Parse HH:MM
    try:
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid format. Please reply with `HH:MM` — for example `08:00`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    tone    = _pending_schedule.pop(user_id)
    job_name = f"channel_{tone}"

    # Remove any existing job for this tone
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    # Register new daily job
    import datetime as dt
    job_time = dt.time(hour=hour, minute=minute, tzinfo=timezone.utc)

    context.job_queue.run_daily(
        callback  = _scheduled_job_callback,
        time      = job_time,
        name      = job_name,
        data      = tone,
    )

    await update.message.reply_text(
        f"✅ *{tone.title()} post* scheduled for *{hour:02d}:{minute:02d} UTC* daily.\n\n"
        f"Channel: `{CHANNEL_ID}`",
        parse_mode   = ParseMode.MARKDOWN,
        reply_markup = _control_panel_keyboard(),
    )


async def _scheduled_job_callback(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback — runs the full pipeline and posts to the channel."""
    tone = context.job.data
    if not CHANNEL_ID:
        logger.warning("[channel] CHANNEL_ID not set — skipping scheduled post")
        return
    try:
        raw       = await fetch_all_channel_data()
        data      = enrich_data(raw)
        prompt    = build_ai_prompt(data, tone)
        narrative = await get_ai_narrative(prompt) or fallback_narrative(data)
        text, markup = format_channel_post(data, narrative, tone)

        await context.bot.send_message(
            chat_id      = CHANNEL_ID,
            text         = text,
            parse_mode   = ParseMode.MARKDOWN,
            reply_markup = markup,
            disable_web_page_preview = True,
        )
        logger.info(f"[channel] {tone} post sent — score {data['score']}")
    except Exception as e:
        logger.exception(f"[channel] scheduled post failed: {e}")


# ============================================================================
# REGISTRATION
# ============================================================================

def register_channel_update_handler(app):
    from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters

    app.add_handler(CommandHandler("sendupdate", channel_update_command))

    app.add_handler(CallbackQueryHandler(cu_preview_morning,  pattern="^cu_preview_morning$"))
    app.add_handler(CallbackQueryHandler(cu_preview_evening,  pattern="^cu_preview_evening$"))
    app.add_handler(CallbackQueryHandler(cu_schedule_morning, pattern="^cu_schedule_morning$"))
    app.add_handler(CallbackQueryHandler(cu_schedule_evening, pattern="^cu_schedule_evening$"))

    # Catch the HH:MM reply — only fires when a schedule is pending for this user
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        cu_schedule_time_handler,
    ))

