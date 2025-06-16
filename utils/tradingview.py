
import os
import httpx
import urllib.parse
from telegram.helpers import escape_markdown

SCREENSHOT_ONE_KEY = os.getenv("SCREENSHOT_ONE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID",))  # Replace or fetch from config

TF_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1d": "1D",
}

async def generate_chart_image(symbol, timeframe, context):
    try:
        if timeframe not in TF_MAP:
            return None

        interval = TF_MAP[timeframe]
        symbol = symbol.upper()

        tv_url = (
            f"https://s.tradingview.com/widgetembed/?symbol=BINANCE:{symbol}&interval={interval}"
            f"&hidesidetoolbar=1&symboledit=1&saveimage=1&toolbarbg=F1F3F6&studies=[]&theme=dark"
            f"&style=1&timezone=Africa/Lagos"
        )
        encoded_url = urllib.parse.quote(tv_url, safe="")

        # ScreenshotOne API
        screenshot_url = (
            f"https://api.screenshotone.com/take"
            f"?access_key={SCREENSHOT_ONE_KEY}"
            f"&url={encoded_url}"
            f"&format=png&viewport_width=1280&viewport_height=720"
        )

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(screenshot_url)

        if resp.status_code != 200:
            try:
                err = resp.json()
                code = err.get("error_code", "unknown")
                msg = err.get("error_message", resp.text)
            except Exception:
                code, msg = "unknown", resp.text

            # Notify admin
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ Screenshot API error ({code}):\n`{escape_markdown(msg, version=2)}`",
                parse_mode="MarkdownV2"
            )
            return None

        return resp.content  # image bytes

    except Exception as e:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❌ Screenshot Exception:\n`{escape_markdown(str(e), version=2)}`",
            parse_mode="MarkdownV2"
        )
        return None