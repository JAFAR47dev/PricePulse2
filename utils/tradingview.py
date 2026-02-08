"""
Simplified chart generator with exchange fallback (lighter version)
"""

import os
import httpx
import urllib.parse
from telegram.helpers import escape_markdown

SCREENSHOT_ONE_KEY = os.getenv("SCREENSHOT_ONE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# ====== EXPANDED TIMEFRAME MAPPING ======
TF_MAP = {
    # Minutes
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "45m": "45",
    
    # Hours
    "1h": "60",
    "2h": "120",
    "3h": "180",
    "4h": "240",
    "6h": "360",
    "8h": "480",
    "12h": "720",
    
    # Days
    "1d": "1D",
    "2d": "2D",
    "3d": "3D",
    
    # Weeks & Months
    "1w": "1W",
    "1M": "1M",
}

# ====== EXCHANGE FALLBACK ORDER ======
EXCHANGE_FALLBACKS = [
    "BINANCE",
    "COINBASE",
    "BYBIT",
    "KUCOIN",
    "OKX",
    "KRAKEN",
    "MEXC",
    "GATEIO",
]

# Common quote currencies to try
QUOTE_CURRENCIES = ["USDT", "USD", "BUSD", "USDC", "PERP"]


async def generate_chart_image(symbol, timeframe, context):
    """
    Generate chart with automatic exchange fallback.
    Tries multiple exchanges if the first one fails.
    
    Args:
        symbol: Trading symbol (e.g., 'BTC', 'BTCUSDT')
        timeframe: Chart timeframe from TF_MAP
        context: Telegram context
    
    Returns:
        bytes: PNG image or None
    """
    try:
        # Validate timeframe
        if timeframe not in TF_MAP:
            return None

        interval = TF_MAP[timeframe]
        base_symbol = symbol.upper()
        
        # Clean symbol to get base (remove common suffixes)
        for quote in QUOTE_CURRENCIES:
            if base_symbol.endswith(quote):
                base_symbol = base_symbol.replace(quote, "")
                break
        
        # Try exchanges in order until one works
        for exchange in EXCHANGE_FALLBACKS:
            for quote in QUOTE_CURRENCIES:
                pair = f"{base_symbol}{quote}"
                
                # Try to generate screenshot
                image_bytes = await _try_exchange(exchange, pair, interval, context)
                
                if image_bytes:
                    print(f"✅ Chart generated: {exchange}:{pair} ({timeframe})")
                    return image_bytes
        
        # If we get here, nothing worked
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Failed to find `{escape_markdown(symbol, version=2)}` on any exchange",
                parse_mode="MarkdownV2"
            )
        
        return None

    except Exception as e:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ Chart generation error:\n`{escape_markdown(str(e), version=2)}`",
                parse_mode="MarkdownV2"
            )
        return None


async def _try_exchange(exchange: str, symbol: str, interval: str, context) -> bytes:
    """
    Try to generate chart for specific exchange:symbol pair.
    
    Returns:
        bytes: Image data if successful, None if failed
    """
    try:
        tv_url = (
            f"https://s.tradingview.com/widgetembed/"
            f"?symbol={exchange}:{symbol}"
            f"&interval={interval}"
            f"&hidesidetoolbar=1"
            f"&symboledit=1"
            f"&saveimage=1"
            f"&toolbarbg=F1F3F6"
            f"&studies=[]"
            f"&theme=dark"
            f"&style=1"
            f"&timezone=Etc/UTC"
        )
        
        encoded_url = urllib.parse.quote(tv_url, safe="")

        screenshot_url = (
            f"https://api.screenshotone.com/take"
            f"?access_key={SCREENSHOT_ONE_KEY}"
            f"&url={encoded_url}"
            f"&format=png"
            f"&viewport_width=1280"
            f"&viewport_height=720"
            f"&delay=1"
        )

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(screenshot_url)

        # Accept 200 as success
        if resp.status_code == 200:
            # Basic validation: check if image is not too small (likely error page)
            if len(resp.content) > 10000:  # >10KB suggests valid chart
                return resp.content
        
        return None

    except Exception as e:
        # Silent fail - we'll try next exchange
        print(f"Failed {exchange}:{symbol} - {str(e)[:50]}")
        return None


def get_timeframe_help() -> str:
    """Get user-friendly timeframe list"""
    return (
        "⏱️ **Available Timeframes:**\n\n"
        "**Minutes:** 1m, 3m, 5m, 15m, 30m, 45m\n"
        "**Hours:** 1h, 2h, 3h, 4h, 6h, 8h, 12h\n"
        "**Days:** 1d, 2d, 3d\n"
        "**Weeks/Months:** 1w, 1M"
    )

