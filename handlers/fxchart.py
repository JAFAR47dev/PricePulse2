# handlers/fxchart.py
import os
import io
import httpx
import urllib.parse
from dotenv import load_dotenv
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from tasks.handlers import handle_streak
from models.user_activity import update_last_active
from models.user import get_user_plan

load_dotenv()
SCREENSHOT_ONE_KEY = os.getenv("SCREENSHOT_ONE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# timeframe mapping used by TradingView embed (same mapping as your /c command)
TF_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1d": "1D",
    "1w": "1W",
}


def pick_tv_symbol(pair: str) -> str:
    """
    Pick a TradingView symbol for the requested pair.
    Rules:
      - If looks like FX (3+3 letters and no USDT), use FX:PAIR (EURUSD)
      - If endswith USDT or USD or BTC/usd etc, prefer BINANCE:PAIR for crypto
      - Fallback to "COINBASE:" or plain pair with FX: prefix
    """
    p = pair.upper().replace("/", "").strip()

    # FX (common format: EURUSD, GBPJPY)
    if len(p) == 6 and p.isalpha():
        return f"FX:{p}"

    # Crypto-like pairs (end with USDT / USD / BTC)
    # prefer BINANCE for symbols like BTCUSDT / ETHUSDT
    if p.endswith("USDT") or p.endswith("USD") or p.endswith("BTC"):
        # try BINANCE first
        return f"BINANCE:{p}"

    # If it contains a dash or colon (user provided exchange), pass through
    if ":" in pair or "-" in pair:
        return pair

    # fallback to FX
    return f"FX:{p}"


async def fxchart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    try:
        args = context.args or []
        if not args:
            return await update.message.reply_text(
                "📊 Usage: `/fxchart [PAIR] [timeframe]`\nExamples:\n`/fxchart EURUSD 1h`\n`/fxchart BTCUSDT 4h`",
                parse_mode=ParseMode.MARKDOWN
            )

        pair = args[0].upper()
        timeframe = args[1].lower() if len(args) > 1 else "1h"
        
        plan = get_user_plan(user_id)
        if plan == "free" and timeframe != "1h":
            await update.message.reply_text(
                "🔒 Only the `1h` chart is available for Free users.\nUse /upgrade to unlock other timeframes: 1m, 5m, 15m, 30m, 4h, 1d.",
                parse_mode="Markdown"
            )
            return
        
        if timeframe not in TF_MAP:
            return await update.message.reply_text(
                "⚠️ Invalid timeframe. Use one of: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`.",
                parse_mode=ParseMode.MARKDOWN
            )
                        
        if not SCREENSHOT_ONE_KEY:
            return await update.message.reply_text(
                "⚠️ Screenshot API key not configured. Contact the bot admin.",
                parse_mode=ParseMode.MARKDOWN
            )

        interval = TF_MAP[timeframe]
        tv_symbol = pick_tv_symbol(pair)

        # Build TradingView widget URL
        tv_url = (
            f"https://s.tradingview.com/widgetembed/?symbol={urllib.parse.quote(tv_symbol, safe='')}"
            f"&interval={interval}"
            f"&hidesidetoolbar=1&symboledit=1&saveimage=1&toolbarbg=F1F3F6"
            f"&theme=dark&style=1&timezone=Etc/UTC"
        )

        encoded_url = urllib.parse.quote(tv_url, safe="")

        screenshot_url = (
            f"https://api.screenshotone.com/take"
            f"?access_key={SCREENSHOT_ONE_KEY}"
            f"&url={encoded_url}"
            f"&format=png&viewport_width=1280&viewport_height=720"
        )

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(screenshot_url)

        if resp.status_code != 200 or not resp.content:
            # try to include a small part of the response for debugging
            err_txt = None
            try:
                err_json = resp.json()
                err_txt = err_json.get("error_message") or err_json.get("message") or str(err_json)[:300]
            except Exception:
                err_txt = resp.text[:300] if resp.text else f"status {resp.status_code}"

            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ Screenshot API error for {pair} ({timeframe}): {escape_markdown(str(err_txt), version=2)}",
                    parse_mode="MarkdownV2"
                )

            return await update.message.reply_text("⚠️ Failed to fetch chart image. Try again later.")

        image_bytes = resp.content
        bio = io.BytesIO(image_bytes)
        bio.name = f"{pair}_{timeframe}.png"
        bio.seek(0)

        caption = f"📈 *{pair}* — {timeframe.upper()} chart (TradingView)"
        await update.message.reply_photo(photo=InputFile(bio, filename=bio.name), caption=caption, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        # notify admin with escaped message if configured
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ FXChart Exception for {pair if 'pair' in locals() else 'unknown'}:\n`{escape_markdown(str(e), version=2)}`",
                    parse_mode="MarkdownV2"
                )
            except Exception:
                pass
        print("FXChart error:", e)
        await update.message.reply_text("⚠️ Could not generate chart. Try again later.")