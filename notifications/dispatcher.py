# notifications/dispatcher.py
#
# Formats and sends all notification types:
#   1. Daily brief  — scheduled morning/evening market summary
#   2. Signal alert — event-driven per-coin trigger
#
# This is the ONLY file that imports from telegram.
# All logic lives in detector.py and db.py.

import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import Forbidden, BadRequest

from notifications.db import (
    record_sent,
    update_alert_triggered,
    get_all_enabled_users,
)
from notifications.detector import build_daily_brief, check_all_alerts

# ============================================================================
# TIMEFRAME DISPLAY NAMES
# ============================================================================

TF_NAMES = {
    "5m": "5 Min", "15m": "15 Min", "30m": "30 Min",
    "1h": "1 Hour", "4h": "4 Hours", "1d": "1 Day",
}


# ============================================================================
# DAILY BRIEF
# ============================================================================

def _format_daily_brief(brief: Dict, send_time: str) -> str:
    """
    Formats the daily brief dict into a Telegram HTML message.

    Example output:
    ────────────────────
    📡 Daily Signal Brief — Mon, Mar 23

    🔥 3 Strongest Setups · 1 Hour
    ────────────────────
    1. SOL/USDT  $142.30
       Strategy : Breakout with Momentum
       Score    : 8  |  RSI: 52.4
       Signal   : Breaking above EMA, volume rising

    ...

    ⚠️ 3 Weakest Setups
    ...

    📊 100 coins scanned · 14 matches · Best TF: 4H
    ⏱ 07:00 UTC
    ────────────────────
    """
    top   = brief.get("top", [])
    weak  = brief.get("weak", [])
    tf    = TF_NAMES.get(brief.get("timeframe", "1h"), brief.get("timeframe", "1h"))
    total = brief.get("total_matches", 0)
    best  = TF_NAMES.get(brief.get("best_timeframe", "1h"), "1h")
    day   = datetime.now(timezone.utc).strftime("%a, %b %-d")

    lines = []
    lines.append(f"📡 <b>Daily Signal Brief — {day}</b>\n")

    # --- Top setups ---
    if top:
        lines.append(f"🔥 <b>3 Strongest Setups · {tf}</b>")
        lines.append("─" * 22)
        for i, coin in enumerate(top, 1):
            price = coin.get("price")
            rsi   = coin.get("rsi")
            price_str = _fmt_price(price)
            rsi_str   = f"{rsi:.1f}" if rsi is not None else "N/A"

            lines.append(
                f"{i}. <b>{coin['symbol']}/USDT</b>  <code>{price_str}</code>\n"
                f"   Strategy : {coin['best_strategy_name']}\n"
                f"   Score    : {coin['best_score']}  |  RSI: {rsi_str}\n"
                f"   Signal   : <i>{coin['signal_summary']}</i>"
            )
    else:
        lines.append("🔥 <b>Strongest Setups</b>")
        lines.append("─" * 22)
        lines.append("No strong setups found on this timeframe right now.")

    lines.append("")

    # --- Weak setups ---
    if weak:
        lines.append("⚠️ <b>3 Weakest Setups</b>")
        lines.append("─" * 22)
        for i, coin in enumerate(weak, 1):
            price = coin.get("price")
            rsi   = coin.get("rsi")
            price_str = _fmt_price(price)
            rsi_str   = f"{rsi:.1f}" if rsi is not None else "N/A"

            lines.append(
                f"{i}. <b>{coin['symbol']}/USDT</b>  <code>{price_str}</code>\n"
                f"   Score : {coin['best_score']}  |  RSI: {rsi_str}\n"
                f"   Note  : <i>Weak setup — avoid or watch only</i>"
            )
    else:
        lines.append("⚠️ <b>Weakest Setups</b>")
        lines.append("─" * 22)
        lines.append("Not enough data to determine weak setups.")

    lines.append("")

    # --- Footer ---
    lines.append("─" * 22)
    lines.append(
        f"📊 100 coins scanned · {total} matches · Best TF: {best}\n"
        f"⏱ {send_time} UTC"
    )

    return "\n".join(lines)


def _build_brief_keyboard(preferred_tf: str = "1h") -> InlineKeyboardMarkup:
    """Buttons shown under the daily brief."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔍 Full Screener",
                callback_data=f"screener_strat_1"
            ),
            InlineKeyboardButton(
                "⚙️ Preferences",
                callback_data="notif_settings"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔕 Pause Alerts",
                callback_data="notif_pause"
            ),
        ]
    ])


async def send_daily_brief(bot: Bot, user_id: int, preferred_tf: str = "1h") -> bool:
    """
    Build and send the daily brief to a single user.
    Returns True on success, False on failure.
    Handles blocked/deactivated bot gracefully.
    """
    brief = build_daily_brief(timeframe=preferred_tf)
    send_time = datetime.now(timezone.utc).strftime("%H:%M")
    text = _format_daily_brief(brief, send_time)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=_build_brief_keyboard(preferred_tf),
        )
        record_sent(user_id, alert_type="daily_brief", timeframe=preferred_tf)
        return True

    except Forbidden:
        # User blocked the bot — disable their notifications silently
        from notifications.db import update_prefs
        update_prefs(user_id, is_enabled=0)
        print(f"[dispatcher] User {user_id} blocked bot — notifications disabled")
        return False

    except BadRequest as e:
        print(f"[dispatcher] BadRequest sending brief to {user_id}: {e}")
        return False

    except Exception as e:
        print(f"[dispatcher] Error sending brief to {user_id}: {e}")
        return False


async def dispatch_daily_briefs(bot: Bot) -> None:
    """
    Send the daily brief to ALL enabled users.
    Called by the scheduler at morning_time and evening_time.
    Respects each user's preferred_tf setting.
    """
    users = get_all_enabled_users()
    if not users:
        print("[dispatcher] No users with notifications enabled")
        return

    print(f"[dispatcher] Sending daily brief to {len(users)} users...")
    sent = 0
    failed = 0

    for user in users:
        success = await send_daily_brief(
            bot,
            user_id=user["user_id"],
            preferred_tf=user["preferred_tf"],
        )
        if success:
            sent += 1
        else:
            failed += 1

    print(f"[dispatcher] Daily brief done — {sent} sent, {failed} failed")


# ============================================================================
# SIGNAL ALERTS
# ============================================================================

def _format_signal_alert(alert: Dict) -> str:
    """
    Formats a signal alert dict into a Telegram HTML message.

    Example:
    ────────────────────
    ⚡ Signal Detected — SOL/USDT

    Strategy  : Breakout with Momentum
    Timeframe : 1 Hour
    Score     : 8/10

    Price : $142.30
    RSI   : 52.4 — room to run

    Near support, bounce signals
    ────────────────────
    """
    symbol   = alert["symbol"]
    strat    = alert["strategy_name"]
    tf       = TF_NAMES.get(alert["timeframe"], alert["timeframe"])
    score    = alert["score"]
    price    = alert.get("price")
    rsi      = alert.get("rsi")
    summary  = alert.get("signal_summary", "")

    price_str = _fmt_price(price)
    rsi_str, rsi_note = _fmt_rsi(rsi)

    return (
        f"⚡ <b>Signal Detected — {symbol}/USDT</b>\n\n"
        f"Strategy  : {strat}\n"
        f"Timeframe : {tf}\n"
        f"Score     : {score}/10\n\n"
        f"Price : <code>{price_str}</code>\n"
        f"RSI   : <code>{rsi_str}</code>{rsi_note}\n\n"
        f"<i>{summary}</i>\n"
        "─" * 22
    )


def _build_signal_keyboard(alert: Dict) -> InlineKeyboardMarkup:
    """Buttons shown under each signal alert."""
    symbol      = alert["symbol"]
    strategy_key = alert["strategy_key"]
    timeframe   = alert["timeframe"]
    alert_id    = alert["alert_id"]

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 View Setup",
                callback_data=f"setup_{symbol}"
            ),
            InlineKeyboardButton(
                "🔍 Full Screener",
                callback_data=f"screener_tf_{strategy_key}_{timeframe}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔕 Mute This Alert",
                callback_data=f"notif_mute_{alert_id}"
            ),
        ]
    ])


async def dispatch_signal_alerts(bot: Bot) -> None:
    """
    Check all active signal alerts against the current screener cache
    and send any that are pending.

    Called from screener_job.py after every precompute_all_coins() call.
    """
    from notifications.detector import _build_signal_summary

    pending = check_all_alerts()

    if not pending:
        return

    print(f"[dispatcher] {len(pending)} signal alerts to send...")
    sent = 0

    for alert in pending:
        # Enrich with signal summary if not already present
        if "signal_summary" not in alert:
            alert["signal_summary"] = _build_signal_summary(
                alert["strategy_key"], alert.get("rsi")
            )

        try:
            await bot.send_message(
                chat_id=alert["user_id"],
                text=_format_signal_alert(alert),
                parse_mode="HTML",
                reply_markup=_build_signal_keyboard(alert),
            )

            # Log it so cooldown works
            record_sent(
                user_id=alert["user_id"],
                alert_type="signal",
                symbol=alert["symbol"],
                strategy_key=alert["strategy_key"],
                timeframe=alert["timeframe"],
                score=alert["score"],
                price=alert.get("price"),
            )

            # Stamp last_triggered on the alert row
            update_alert_triggered(alert["alert_id"])
            sent += 1

        except Forbidden:
            from notifications.db import update_prefs
            update_prefs(alert["user_id"], is_enabled=0)
            print(f"[dispatcher] User {alert['user_id']} blocked bot")

        except Exception as e:
            print(f"[dispatcher] Error sending signal to {alert['user_id']}: {e}")

    print(f"[dispatcher] Signal alerts done — {sent}/{len(pending)} sent")


# ============================================================================
# HELPERS
# ============================================================================

def _fmt_price(price) -> str:
    """Format price for display — handles micro-cap coins."""
    if price is None:
        return "N/A"
    if price < 0.0001:
        return f"${price:.8f}"
    if price < 1:
        return f"${price:.4f}"
    return f"${price:.2f}"


def _fmt_rsi(rsi) -> tuple:
    """Returns (rsi_string, note_string)."""
    if rsi is None:
        return "N/A", ""
    rsi_str = f"{rsi:.1f}"
    if rsi < 30:
        return rsi_str, " — heavily oversold"
    if rsi < 40:
        return rsi_str, " — oversold"
    if rsi > 70:
        return rsi_str, " — overbought"
    if rsi > 60:
        return rsi_str, " — elevated"
    return rsi_str, " — neutral"
