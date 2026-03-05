"""
handlers/risk_command.py

AI-powered interactive position sizing calculator.
Step flow:
  1. Account size
  2. Risk percent
  3. Leverage  ← NEW
  4. Entry price
  5. Stop loss  → generate report
  (or /skip after step 2 for a basic summary)

Leverage is used to:
  - Calculate actual margin required
  - Warn at dangerous leverage levels
  - Feed into AI analysis
  - Show liquidation price
  - Compute effective exposure correctly
"""

import os
import logging
import httpx

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
logger = logging.getLogger(__name__)


# ── Number formatter ──────────────────────────────────────────────────────────

def _fmt(num: float) -> str:
    """Format a number with appropriate precision and commas."""
    if num >= 1_000_000:
        return f"{num:,.0f}"
    if num >= 1_000:
        return f"{num:,.2f}"
    if num >= 100:
        return f"{num:,.2f}"
    if num >= 1:
        return f"{num:.4f}"
    return f"{num:.6f}"


def _pct(num: float) -> str:
    return f"{num:.2f}%"


# ── Liquidation price calculator ──────────────────────────────────────────────

def _liquidation_price(entry: float, leverage: float, is_long: bool) -> float:
    """
    Simplified cross-margin liquidation estimate.
    Assumes 100% of margin is used (worst case).
    Long:  liq = entry * (1 - 1/leverage)
    Short: liq = entry * (1 + 1/leverage)
    """
    if leverage <= 1:
        return 0.0   # spot — no liquidation
    if is_long:
        return entry * (1 - 1 / leverage)
    else:
        return entry * (1 + 1 / leverage)


# ── Leverage risk label ───────────────────────────────────────────────────────

def _leverage_label(lev: float) -> tuple[str, str]:
    """Return (emoji, label) for a given leverage value."""
    if lev <= 1:
        return "✅", "Spot (no liquidation risk)"
    if lev <= 3:
        return "🟡", "Low leverage"
    if lev <= 5:
        return "⚠️", "Moderate leverage"
    if lev <= 10:
        return "🔴", "High leverage"
    if lev <= 20:
        return "🚨", "Very high leverage"
    return "💀", "Extreme leverage — account at serious risk"


# ============================================================================
# ENTRY POINT
# ============================================================================

async def risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /risk — AI-powered interactive position sizing calculator.
    Now collects leverage before entry price so all calculations
    (margin, liquidation, effective exposure) are accurate.
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/risk")
    await handle_streak(update, context)

    plan    = get_user_plan(user_id)
    is_pro  = is_pro_plan(plan)

    context.user_data["risk_flow"] = {
        "active":    True,
        "step":      "account_size",
        "is_pro":    is_pro,
        "data":      {},
    }

    await update.message.reply_text(
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


# ============================================================================
# CENTRAL MESSAGE ROUTER
# ============================================================================

async def risk_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route incoming messages to the correct step handler."""
    flow = context.user_data.get("risk_flow")
    if not flow or not flow.get("active"):
        return

    text = update.message.text.strip()

    if text.lower() in ("/cancel", "cancel"):
        context.user_data["risk_flow"] = {"active": False}
        await update.message.reply_text(
            "❌ Risk calculator cancelled.\n\nUse /risk to start again.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    step = flow["step"]
    try:
        dispatch = {
            "account_size": _step_account_size,
            "risk_percent": _step_risk_percent,
            "leverage":     _step_leverage,
            "entry_price":  _step_entry_price,
            "stop_loss":    _step_stop_loss,
        }
        handler = dispatch.get(step)
        if handler:
            await handler(update, context, text)
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid input — please enter a valid number.\n\n_Type /cancel to exit_",
            parse_mode=ParseMode.MARKDOWN,
        )


# ============================================================================
# STEP HANDLERS
# ============================================================================

async def _step_account_size(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    account_size = float(text.replace(",", "").replace("$", ""))
    if account_size <= 0:
        await update.message.reply_text("❌ Account size must be positive. Try again:")
        return

    # Category + advice
    if account_size < 1_000:
        category, advice = "Micro", "Focus on 1–2% risk max while growing"
    elif account_size < 5_000:
        category, advice = "Small",  "Stay disciplined — 1–2% per trade"
    elif account_size < 25_000:
        category, advice = "Medium", "1–2% risk is optimal here"
    else:
        category, advice = "Large",  "Conservative 0.5–1.5% protects capital"

    flow = context.user_data["risk_flow"]
    flow["data"]["account_size"] = account_size
    flow["data"]["size_category"] = category
    flow["step"] = "risk_percent"

    # Build personalised recommendation lines
    recommendations = []
    if account_size < 1_000:
        for pct in [1, 2]:
            recommendations.append(f"`{pct}%` → ${_fmt(account_size * pct / 100)}")
    elif account_size < 10_000:
        for pct in [1, 2, 3]:
            recommendations.append(f"`{pct}%` → ${_fmt(account_size * pct / 100)}")
    else:
        for pct in [0.5, 1, 2]:
            recommendations.append(f"`{pct}%` → ${_fmt(account_size * pct / 100)}")

    recs = "\n".join(recommendations)

    await update.message.reply_text(
        f"✅ Account: `${_fmt(account_size)}` ({category})\n"
        f"💡 {advice}\n\n"
        f"*Step 2 of 5:* Risk Percentage\n\n"
        f"⚠️ What % of your account do you want to risk per trade?\n\n"
        f"*Recommended for your account size:*\n"
        f"{recs}\n\n"
        f"_Type /cancel to exit_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _step_risk_percent(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    risk_percent = float(text.replace("%", "").strip())
    if not (0 < risk_percent <= 100):
        await update.message.reply_text("❌ Risk % must be between 0 and 100. Try again:")
        return

    flow         = context.user_data["risk_flow"]
    account_size = flow["data"]["account_size"]
    risk_amount  = account_size * risk_percent / 100

    # Risk level
    if risk_percent > 5:
        warning    = "⚠️ *CRITICAL:* >5% risk — 10 losses wipes 50%+ of account."
        risk_level = "extreme"
    elif risk_percent > 3:
        warning    = "⚠️ *Warning:* >3% is aggressive. Only viable with a proven 60%+ win rate."
        risk_level = "aggressive"
    elif risk_percent >= 2:
        warning    = "✅ Standard professional risk level."
        risk_level = "standard"
    elif risk_percent >= 1:
        warning    = "✅ Conservative — excellent for capital preservation."
        risk_level = "conservative"
    else:
        warning    = "✅ Ultra-conservative. Great for compounding safely."
        risk_level = "ultra_conservative"

    flow["data"]["risk_percent"] = risk_percent
    flow["data"]["risk_level"]   = risk_level
    flow["step"] = "leverage"

    await update.message.reply_text(
        f"✅ Risk: `{risk_percent}%` → `${_fmt(risk_amount)}` per trade\n"
        f"{warning}\n\n"
        f"*Step 3 of 5:* Leverage\n\n"
        f"⚡ What leverage will you use?\n\n"
        f"*Examples:*\n"
        f"`1` → Spot / No leverage ✅\n"
        f"`3` → 3× leverage 🟡\n"
        f"`5` → 5× leverage ⚠️\n"
        f"`10` → 10× leverage 🔴\n"
        f"`20` → 20× leverage 🚨\n\n"
        f"💡 Higher leverage = smaller margin, bigger liquidation risk.\n\n"
        f"_Type /cancel to exit_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _step_leverage(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    raw = text.lower().replace("x", "").replace("×", "").strip()
    leverage = float(raw)

    if leverage < 1:
        await update.message.reply_text("❌ Leverage must be 1 or higher (use 1 for spot). Try again:")
        return
    if leverage > 125:
        await update.message.reply_text("❌ Max leverage supported is 125×. Try again:")
        return

    flow         = context.user_data["risk_flow"]
    account_size = flow["data"]["account_size"]
    risk_percent = flow["data"]["risk_percent"]
    risk_amount  = account_size * risk_percent / 100

    lev_emoji, lev_label = _leverage_label(leverage)

    # Margin required per $1 of position
    margin_note = ""
    if leverage > 1:
        margin_pct   = 100 / leverage
        margin_note  = f"\n💡 Each $100 of position requires `${margin_pct:.1f}` margin."

    flow["data"]["leverage"] = leverage
    flow["step"] = "entry_price"

    await update.message.reply_text(
        f"✅ Leverage: `{leverage:.0f}×` {lev_emoji} {lev_label}{margin_note}\n\n"
        f"*Step 4 of 5:* Entry Price\n\n"
        f"💰 At what price are you entering?\n\n"
        f"*Examples:*\n"
        f"`95000` → $95,000 (BTC)\n"
        f"`3500` → $3,500 (ETH)\n"
        f"`150` → $150 (SOL)\n\n"
        f"_Type /skip for a basic summary without position sizing_\n"
        f"_Type /cancel to exit_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _step_entry_price(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text.lower() == "/skip":
        await _generate_basic_report(update, context)
        return

    entry_price = float(text.replace(",", "").replace("$", ""))
    if entry_price <= 0:
        await update.message.reply_text("❌ Entry price must be positive. Try again:")
        return

    flow     = context.user_data["risk_flow"]
    leverage = flow["data"]["leverage"]

    # Asset guess
    if entry_price > 40_000:
        asset = "BTC"
    elif 2_000 < entry_price < 10_000:
        asset = "ETH / BNB"
    elif 50 < entry_price < 500:
        asset = "SOL / AVAX"
    elif entry_price < 10:
        asset = "Altcoin"
    else:
        asset = "Mid-cap"

    # Suggest stops (tighter when leverage is high)
    base_sl_pct = max(1.5, min(8.0, 8.0 / leverage))   # tighten with leverage
    long_sl     = entry_price * (1 - base_sl_pct / 100)
    short_sl    = entry_price * (1 + base_sl_pct / 100)

    lev_stop_note = ""
    if leverage > 5:
        lev_stop_note = (
            f"\n⚠️ At {leverage:.0f}× leverage, a {base_sl_pct:.1f}% move against you "
            f"loses {base_sl_pct * leverage:.0f}% of margin."
        )

    flow["data"]["entry_price"]  = entry_price
    flow["data"]["likely_asset"] = asset
    flow["step"] = "stop_loss"

    await update.message.reply_text(
        f"✅ Entry: `${_fmt(entry_price)}`  ({asset})\n\n"
        f"*Step 5 of 5:* Stop Loss\n\n"
        f"🛡️ Where is your stop loss?\n\n"
        f"*Suggested stops at {leverage:.0f}× leverage ({base_sl_pct:.1f}%):*\n"
        f"• Long stop: `${_fmt(long_sl)}`\n"
        f"• Short stop: `${_fmt(short_sl)}`\n"
        f"{lev_stop_note}\n\n"
        f"_Type /cancel to exit_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _step_stop_loss(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    stop_loss = float(text.replace(",", "").replace("$", ""))
    if stop_loss <= 0:
        await update.message.reply_text("❌ Stop loss must be positive. Try again:")
        return

    await update.message.reply_text("⏳ Running analysis…")

    flow = context.user_data["risk_flow"]
    flow["data"]["stop_loss"] = stop_loss

    await _generate_full_report(update, context)
    context.user_data["risk_flow"] = {"active": False}


# ============================================================================
# REPORT GENERATORS
# ============================================================================

async def _generate_basic_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Basic summary when user skips entry/stop steps."""
    flow = context.user_data["risk_flow"]
    data = flow["data"]

    account_size = data["account_size"]
    risk_percent = data["risk_percent"]
    leverage     = data.get("leverage", 1)
    risk_amount  = account_size * risk_percent / 100
    lev_emoji, lev_label = _leverage_label(leverage)

    # Streak survival
    streak_lines = ""
    for losses in [5, 10, 20]:
        remaining = account_size * ((1 - risk_percent / 100) ** losses)
        loss_pct  = (1 - remaining / account_size) * 100
        streak_lines += f"{losses} losses: `${_fmt(remaining)}` (-{loss_pct:.1f}%)\n"

    # Quick scenarios
    scenario_lines = ""
    for pct in [0.5, 1, 2, 3, 5]:
        amt   = account_size * pct / 100
        mark  = " ← yours" if pct == risk_percent else ""
        emoji = "✅" if pct <= 2 else "⚠️" if pct <= 3 else "🔴"
        scenario_lines += f"{emoji} `{pct}%` → `${_fmt(amt)}`{mark}\n"

    msg = (
        f"💰 *Basic Risk Summary*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"`${_fmt(account_size)}` account · `{risk_percent}%` risk · `{leverage:.0f}×` {lev_emoji}\n\n"
        f"──────────────────────\n"
        f"💵 *Risk Per Trade*\n"
        f"──────────────────────\n"
        f"Max loss: `${_fmt(risk_amount)}`\n"
        f"Leverage: `{leverage:.0f}×` — {lev_label}\n\n"
        f"──────────────────────\n"
        f"📊 *Risk Comparison*\n"
        f"──────────────────────\n"
        f"{scenario_lines}\n"
        f"──────────────────────\n"
        f"📉 *Losing Streak Survival*\n"
        f"──────────────────────\n"
        f"{streak_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 Run /risk again with entry + stop loss\n"
        f"for full position sizing, liquidation price,\n"
        f"and AI risk assessment."
    )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    context.user_data["risk_flow"] = {"active": False}


async def _generate_full_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full position-sized report with leverage, liquidation, and AI analysis."""
    flow = context.user_data["risk_flow"]
    data = flow["data"]
    is_pro = flow["is_pro"]

    account_size = data["account_size"]
    risk_percent = data["risk_percent"]
    leverage     = data.get("leverage", 1.0)
    entry_price  = data["entry_price"]
    stop_loss    = data["stop_loss"]

    risk_amount     = account_size * risk_percent / 100
    is_long         = stop_loss < entry_price
    direction_label = "LONG 🟢" if is_long else "SHORT 🔴"

    # Core metrics
    stop_distance     = abs(entry_price - stop_loss)
    stop_distance_pct = stop_distance / entry_price * 100

    # Position sizing
    # units = risk_amount / stop_distance
    # position_value = units * entry_price
    # margin_required = position_value / leverage
    if stop_distance <= 0:
        await update.message.reply_text("❌ Stop loss cannot equal entry price. Please /risk again.")
        return

    units           = risk_amount / stop_distance
    position_value  = units * entry_price
    margin_required = position_value / leverage
    exposure_pct    = position_value / account_size * 100   # leveraged notional vs account

    # Liquidation price
    liq_price = _liquidation_price(entry_price, leverage, is_long)
    liq_distance_pct = abs(entry_price - liq_price) / entry_price * 100 if liq_price else 0

    # ── Grades ────────────────────────────────────────────────────────
    # Stop quality
    if stop_distance_pct < 2:
        stop_grade = "✅ Tight"
    elif stop_distance_pct < 5:
        stop_grade = "🟡 Normal"
    elif stop_distance_pct < 10:
        stop_grade = "⚠️ Wide"
    else:
        stop_grade = "🔴 Very Wide"

    # Leverage warning
    lev_emoji, lev_label = _leverage_label(leverage)

    # Liquidation vs stop warning
    if leverage > 1 and is_long:
        liq_is_safe = liq_price < stop_loss   # liq below stop = stop triggers first ✅
    elif leverage > 1:
        liq_is_safe = liq_price > stop_loss   # short: liq above stop = stop triggers first ✅
    else:
        liq_is_safe = True   # spot

    liq_warn = "" if liq_is_safe else "\n⚠️ *Liquidation hits BEFORE your stop loss!* Reduce leverage or widen stop."

    # Overall grade
    lev_penalty = max(0, leverage - 5) * 5   # each lever above 5× adds penalty
    grade_score = 100 - (risk_percent * 10) - (stop_distance_pct * 2) - lev_penalty
    if grade_score >= 85:
        grade, grade_label = "A+", "Exceptional"
    elif grade_score >= 70:
        grade, grade_label = "A",  "Excellent"
    elif grade_score >= 55:
        grade, grade_label = "B",  "Good"
    elif grade_score >= 40:
        grade, grade_label = "C",  "Fair"
    else:
        grade, grade_label = "D",  "High Risk"

    # ── Build message ─────────────────────────────────────────────────
    msg = (
        f"🤖 *AI Risk Report — {direction_label.split()[0]}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"`${_fmt(account_size)}` · `{risk_percent}%` risk · `{leverage:.0f}×` {lev_emoji} · Grade: *{grade}*\n\n"

        f"──────────────────────\n"
        f"📍 *Trade Setup*\n"
        f"──────────────────────\n"
        f"Direction: {direction_label}\n"
        f"Entry:    `${_fmt(entry_price)}`\n"
        f"Stop:     `${_fmt(stop_loss)}`  ({_pct(stop_distance_pct)} away)  {stop_grade}\n"
        f"Leverage: `{leverage:.0f}×`  {lev_emoji} {lev_label}\n\n"

        f"──────────────────────\n"
        f"💰 *Position Sizing*\n"
        f"──────────────────────\n"
        f"Size:          `{units:.4f}` units\n"
        f"Position value: `${_fmt(position_value)}`\n"
        f"Margin used:   `${_fmt(margin_required)}` ({_pct(margin_required / account_size * 100)} of account)\n"
        f"Notional exposure: {_pct(exposure_pct)}\n\n"

        f"──────────────────────\n"
        f"⚖️ *Risk Metrics*\n"
        f"──────────────────────\n"
        f"Max loss:    `${_fmt(risk_amount)}`  ({risk_percent}%)\n"
        f"Grade:       {grade} — {grade_label}\n"
    )

    # Liquidation section
    if leverage > 1:
        msg += (
            f"\n──────────────────────\n"
            f"🔥 *Liquidation Price*\n"
            f"──────────────────────\n"
            f"Liq price: `${_fmt(liq_price)}`  ({_pct(liq_distance_pct)} from entry)\n"
            f"Stop hits first: {'✅ Yes' if liq_is_safe else '❌ No'}{liq_warn}\n"
        )

    # ── Profit Targets (all users get 2:1; Pro gets full table) ───────
    msg += (
        f"\n──────────────────────\n"
        f"🎯 *Profit Targets*\n"
        f"──────────────────────\n"
    )

    rr_range = [1, 2, 3, 4, 5] if is_pro else [2]
    for rr in rr_range:
        if is_long:
            target = entry_price + stop_distance * rr
        else:
            target = entry_price - stop_distance * rr

        profit  = risk_amount * rr
        roi_pct = profit / account_size * 100

        tag = ""
        if rr == 2:
            tag = "  ✅ Min"
        elif rr == 3:
            tag = "  🎯 Sweet"
        elif rr == 5:
            tag = "  🏆 Moon"

        msg += f"`{rr}:1` → `${_fmt(target)}`  +`${_fmt(profit)}` (+{roi_pct:.1f}%){tag}\n"

    # ── AI Section (Pro only) ──────────────────────────────────────────
    if is_pro:
        msg += (
            f"\n──────────────────────\n"
            f"🤖 *AI Risk Assessment*\n"
            f"──────────────────────\n"
        )

        ai_text = await _get_ai_analysis(data, liq_price, liq_is_safe)
        if ai_text:
            msg += f"{ai_text}\n"
        else:
            msg += _fallback_analysis(risk_percent, stop_distance_pct, leverage, liq_is_safe)

        # Optimised alternative (only when stop is wide or leverage is risky)
        if stop_distance_pct > 5 or leverage > 10:
            optimised = await _get_ai_optimised(data)
            if optimised:
                opt_dist  = abs(entry_price - optimised["stop"])
                opt_units = risk_amount / opt_dist if opt_dist else 0
                opt_margin = (opt_units * entry_price) / leverage

                msg += (
                    f"\n──────────────────────\n"
                    f"💡 *AI-Optimised Setup*\n"
                    f"──────────────────────\n"
                    f"Stop:   `${_fmt(optimised['stop'])}`  "
                    f"({abs(entry_price - optimised['stop']) / entry_price * 100:.1f}% away)\n"
                    f"Size:   `{opt_units:.4f}` units  |  Margin: `${_fmt(opt_margin)}`\n\n"
                    f"Targets:\n"
                    f"TP1: `${_fmt(optimised['tp1'])}` (1:1)\n"
                    f"TP2: `${_fmt(optimised['tp2'])}` (2:1)\n"
                    f"TP3: `${_fmt(optimised['tp3'])}` (3:1)\n\n"
                    f"_Tighter stop = more units at same `${_fmt(risk_amount)}` risk_\n"
                )

    # ── Upgrade prompt (free users) ────────────────────────────────────
    if not is_pro:
        msg += (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔓 *Unlock Pro:*\n\n"
            f"• Full 1:1 to 5:1 target table\n"
            f"• AI risk assessment & coaching\n"
            f"• AI-optimised trade suggestions\n"
            f"• Liquidation scenario analysis\n"
            f"• Streak survival projections\n\n"
            f"👉 /upgrade"
        )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ============================================================================
# AI CALLS
# ============================================================================

async def _get_ai_analysis(data: dict, liq_price: float, liq_is_safe: bool) -> str | None:
    """AI risk analysis paragraph — concise, practical, no jargon."""
    if not OPENROUTER_API_KEY:
        return None

    account_size     = data["account_size"]
    risk_percent     = data["risk_percent"]
    entry_price      = data["entry_price"]
    stop_loss        = data["stop_loss"]
    leverage         = data.get("leverage", 1.0)
    is_long          = stop_loss < entry_price
    direction        = "long" if is_long else "short"
    stop_dist_pct    = abs(entry_price - stop_loss) / entry_price * 100
    liq_note         = (
        f"Liquidation at ${liq_price:,.2f} ({'safe — stop hits first' if liq_is_safe else 'DANGER — liq hits before stop'})"
        if leverage > 1 else "Spot trade — no liquidation risk"
    )

    prompt = (
        f"You are a trading risk manager reviewing a trade. Be direct and concise — max 100 words.\n\n"
        f"Trade:\n"
        f"- Direction: {direction.upper()}\n"
        f"- Account: ${account_size:,.0f}\n"
        f"- Risk: {risk_percent}% (${account_size * risk_percent / 100:,.0f})\n"
        f"- Entry: ${entry_price:,.4f}\n"
        f"- Stop: ${stop_loss:,.4f} ({stop_dist_pct:.1f}% away)\n"
        f"- Leverage: {leverage:.0f}×\n"
        f"- {liq_note}\n\n"
        f"Assess in this order:\n"
        f"1. Is the stop distance appropriate for this leverage level?\n"
        f"2. Is the liquidation situation safe?\n"
        f"3. One specific improvement.\n\n"
        f"No preamble. Write like you're texting a trading partner."
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "anthropic/claude-3-haiku",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.5,
                },
            )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        logger.warning(f"[AI Risk] {resp.status_code}: {resp.text[:100]}")
        return None
    except Exception as e:
        logger.warning(f"[AI Risk] {e}")
        return None


async def _get_ai_optimised(data: dict) -> dict | None:
    """Ask AI for an optimised stop + TP1/2/3."""
    if not OPENROUTER_API_KEY:
        return None

    entry     = data["entry_price"]
    stop      = data["stop_loss"]
    leverage  = data.get("leverage", 1.0)
    is_long   = stop < entry
    direction = "LONG" if is_long else "SHORT"

    # Target a tighter stop: 3–5% for spot, tighter for high leverage
    target_pct = max(1.0, min(5.0, 5.0 / max(leverage / 2, 1)))

    prompt = (
        f"Suggest an optimised {direction} trade setup for entry ${entry:,.4f}.\n"
        f"Leverage: {leverage:.0f}×. Aim for a stop ~{target_pct:.1f}% from entry.\n\n"
        f"Respond ONLY in this exact format, no extra text:\n"
        f"STOP: [number]\n"
        f"TARGET1: [number]\n"
        f"TARGET2: [number]\n"
        f"TARGET3: [number]"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "anthropic/claude-3-haiku",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "temperature": 0.3,
                },
            )
        if resp.status_code != 200:
            return None

        lines     = resp.json()["choices"][0]["message"]["content"].strip().split("\n")
        optimised = {}
        for line in lines:
            if "STOP:"    in line: optimised["stop"] = float(line.split(":")[1].strip().replace(",", ""))
            if "TARGET1:" in line: optimised["tp1"]  = float(line.split(":")[1].strip().replace(",", ""))
            if "TARGET2:" in line: optimised["tp2"]  = float(line.split(":")[1].strip().replace(",", ""))
            if "TARGET3:" in line: optimised["tp3"]  = float(line.split(":")[1].strip().replace(",", ""))

        return optimised if len(optimised) == 4 else None
    except Exception as e:
        logger.warning(f"[AI Optimise] {e}")
        return None


# ============================================================================
# FALLBACK ANALYSIS (when AI is unavailable)
# ============================================================================

def _fallback_analysis(risk_pct: float, stop_pct: float, leverage: float, liq_safe: bool) -> str:
    lines = []

    if not liq_safe:
        lines.append(
            "🚨 Your liquidation price hits BEFORE your stop loss. "
            "Either reduce leverage or move your stop closer to entry."
        )
    if leverage > 10:
        lines.append(
            f"At {leverage:.0f}× leverage a {100/leverage:.1f}% adverse move wipes your margin. "
            "Consider reducing leverage to ≤5× to give your trade room to breathe."
        )
    if stop_pct > 8:
        lines.append(
            f"Your {stop_pct:.1f}% stop is wide. "
            "Wide stops force tiny positions and shrink profit potential. "
            "Tighten to a clear technical level and keep the same dollar risk."
        )
    if risk_pct > 3:
        lines.append(
            f"At {risk_pct}% risk you need a 60%+ win rate just to stay flat. "
            "Reduce to 1–2% until your strategy is proven over 100+ trades."
        )
    if not lines:
        lines.append(
            "Solid setup — risk controlled, stop reasonable. "
            "Ensure your stop is at a real support/resistance level, not arbitrary. "
            "Never take a trade below 2:1 R:R."
        )

    return "\n".join(lines) + "\n"
