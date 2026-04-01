# handlers/fxchart.py
import os
import io
import httpx
import urllib.parse
import asyncio
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

# Timeframe mapping used by TradingView embed
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

# ============================================================================
# SUPPORTED FOREX PAIRS ONLY
# ============================================================================

SUPPORTED_FX_PAIRS = [
    # Major FX pairs (most liquid)
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    
    # EUR crosses
    "EURJPY", "EURGBP", "EURAUD", "EURCAD", "EURCHF", "EURNZD",
    
    # GBP crosses
    "GBPJPY", "GBPAUD", "GBPCAD", "GBPCHF", "GBPNZD",
    
    # AUD crosses
    "AUDJPY", "AUDNZD", "AUDCAD", "AUDCHF",
    
    # NZD crosses
    "NZDJPY", "NZDCAD", "NZDCHF",
    
    # JPY crosses
    "CHFJPY", "CADJPY",
    
    # Other crosses
    "CADCHF",
]


def normalize_pair(pair: str) -> str:
    """
    Normalize user input to standard forex pair format
    Returns: normalized_symbol or None if invalid
    """
    # Remove common separators and convert to uppercase
    p = pair.upper().replace("/", "").replace("-", "").replace(" ", "").strip()
    
    # Handle common aliases
    aliases = {
        "EURO": "EURUSD",
        "EUR": "EURUSD",
        "CABLE": "GBPUSD",
        "GBP": "GBPUSD",
        "POUND": "GBPUSD",
        "YEN": "USDJPY",
        "JPY": "USDJPY",
        "SWISSY": "USDCHF",
        "CHF": "USDCHF",
        "AUSSIE": "AUDUSD",
        "AUD": "AUDUSD",
        "LOONIE": "USDCAD",
        "CAD": "USDCAD",
        "KIWI": "NZDUSD",
        "NZD": "NZDUSD",
    }
    
    # Check aliases first
    if p in aliases:
        return aliases[p]
    
    # Check direct match
    if p in SUPPORTED_FX_PAIRS:
        return p
    
    # Try to intelligently parse incomplete pairs
    # e.g., "EURUSD" entered as "EU" or "EUR"
    for supported_pair in SUPPORTED_FX_PAIRS:
        if supported_pair.startswith(p) and len(p) >= 3:
            return supported_pair
    
    return None


def is_supported_pair(pair: str) -> bool:
    """Check if pair is a supported forex pair"""
    return normalize_pair(pair) is not None


def get_fx_pair_info(pair: str) -> dict:
    """
    Get display information for a forex pair
    Returns: {name, description, category}
    """
    normalized = normalize_pair(pair)
    
    if not normalized:
        return None
    
    # Categorize pairs
    majors = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]
    
    if normalized in majors:
        category = "Major"
    else:
        category = "Cross"
    
    # Create readable name
    base = normalized[:3]
    quote = normalized[3:]
    name = f"{base}/{quote}"
    
    return {
        "name": name,
        "description": f"{base} vs {quote}",
        "category": category,
        "symbol": normalized
    }


async def fxchart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/fxchart")
    await handle_streak(update, context)
    
    try:
        args = context.args or []
        if not args:
            return await update.message.reply_text(
                "💱 <b>Forex Chart Command</b>\n\n"
                "<b>Usage:</b> <code>/fxchart [PAIR] [timeframe]</code>\n\n"
                "<b>Examples:</b>\n"
                "• <code>/fxchart EURUSD 1h</code>\n"
                "• <code>/fxchart GBPJPY 4h</code>\n"
                "• <code>/fxchart CABLE 1d</code> (alias for GBPUSD)\n"
                "• <code>/fxchart AUSSIE 1h</code> (alias for AUDUSD)\n\n"
                "<b>📊 Supported Forex Pairs:</b>\n\n"
                "<b>Major Pairs:</b>\n"
                "• EURUSD (Euro/Dollar)\n"
                "• GBPUSD (Pound/Dollar) - aka Cable\n"
                "• USDJPY (Dollar/Yen)\n"
                "• USDCHF (Dollar/Swiss) - aka Swissy\n"
                "• AUDUSD (Aussie/Dollar)\n"
                "• USDCAD (Dollar/Canadian) - aka Loonie\n"
                "• NZDUSD (Kiwi/Dollar)\n\n"
                "<b>Popular Crosses:</b>\n"
                "• EURJPY, GBPJPY, AUDJPY\n"
                "• EURGBP, EURAUD, EURCAD\n"
                "• GBPAUD, GBPCAD, GBPCHF\n"
                "• AUDNZD, AUDCAD, NZDJPY\n"
                "• And 20+ more cross pairs...\n\n"
                "<b>⏰ Timeframes:</b>\n"
                "• <code>1m, 5m, 15m, 30m</code> - Scalping\n"
                "• <code>1h, 4h</code> - Intraday/Swing\n"
                "• <code>1d, 1w</code> - Position Trading\n\n"
                "<i>💡 Tip: Use aliases like CABLE, AUSSIE, LOONIE, KIWI</i>",
                parse_mode=ParseMode.HTML
            )

        pair = args[0].upper()
        timeframe = args[1].lower() if len(args) > 1 else "1h"
        
        # Normalize and validate pair
        normalized_pair = normalize_pair(pair)
        
        if not normalized_pair:
            return await update.message.reply_text(
                f"❌ <b>{pair} is not a supported forex pair</b>\n\n"
                f"<b>💱 Supported Forex Pairs:</b>\n\n"
                f"<b>Majors:</b>\n"
                f"EURUSD, GBPUSD, USDJPY, USDCHF\n"
                f"AUDUSD, USDCAD, NZDUSD\n\n"
                f"<b>EUR Crosses:</b>\n"
                f"EURJPY, EURGBP, EURAUD, EURCAD, EURCHF, EURNZD\n\n"
                f"<b>GBP Crosses:</b>\n"
                f"GBPJPY, GBPAUD, GBPCAD, GBPCHF, GBPNZD\n\n"
                f"<b>AUD/NZD Crosses:</b>\n"
                f"AUDJPY, AUDNZD, AUDCAD, NZDJPY, NZDCAD\n\n"
                f"<b>Other Crosses:</b>\n"
                f"CHFJPY, CADJPY, CADCHF, and more...\n\n"
                f"Use <code>/fxchart</code> to see the full list with examples.\n\n"
                f"<i>💡 Try aliases: CABLE, AUSSIE, LOONIE, KIWI, SWISSY</i>",
                parse_mode=ParseMode.HTML
            )
        
        # Get pair info
        pair_info = get_fx_pair_info(normalized_pair)
        
        # Check user plan for timeframe restrictions
        plan = get_user_plan(user_id)
        if plan == "free" and timeframe != "1h":
            await update.message.reply_text(
                "🔒 <b>Free Plan Limitation</b>\n\n"
                "Only the <code>1h</code> chart is available for Free users.\n\n"
                "<b>Upgrade to Pro to unlock:</b>\n"
                "• <code>1m, 5m, 15m, 30m</code> - Scalping timeframes\n"
                "• <code>4h</code> - Swing trading\n"
                "• <code>1d, 1w</code> - Position trading\n\n"
                "Use /upgrade to unlock all timeframes.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Validate timeframe
        if timeframe not in TF_MAP:
            return await update.message.reply_text(
                "⚠️ <b>Invalid Timeframe</b>\n\n"
                "<b>Available timeframes:</b>\n"
                "• <code>1m, 5m, 15m, 30m</code> - Short-term/Scalping\n"
                "• <code>1h, 4h</code> - Intraday/Swing Trading\n"
                "• <code>1d, 1w</code> - Daily/Weekly Position Trading\n\n"
                "<b>Example:</b> <code>/fxchart EURUSD 1h</code>",
                parse_mode=ParseMode.HTML
            )
        
        # Check API key
        if not SCREENSHOT_ONE_KEY:
            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text="⚠️ SCREENSHOT_ONE_KEY is not configured in .env",
                    parse_mode=ParseMode.HTML
                )
            return await update.message.reply_text(
                "⚠️ Chart service temporarily unavailable. Please try again later.",
                parse_mode=ParseMode.HTML
            )

        # ✅ SHOW LOADING MESSAGE
        loading_msg = await update.message.reply_text(
            f"💱 Loading <b>{pair_info['name']}</b> chart ({timeframe.upper()})...\n"
            f"<i>This may take 5-10 seconds...</i>",
            parse_mode=ParseMode.HTML
        )

        interval = TF_MAP[timeframe]
        
        # Use FX: prefix for all forex pairs (most reliable)
        tv_symbol = f"FX:{normalized_pair}"

        # Build TradingView widget URL optimized for forex
        tv_url = (
            f"https://s.tradingview.com/widgetembed/"
            f"?symbol={urllib.parse.quote(tv_symbol, safe='')}"
            f"&interval={interval}"
            f"&hidesidetoolbar=1"
            f"&symboledit=1"
            f"&saveimage=1"
            f"&toolbarbg=f1f3f6"
            f"&studies=[]"
            f"&theme=dark"
            f"&style=1"
            f"&timezone=Etc/UTC"
            f"&studies_overrides={{}}"
            f"&overrides={{}}"
            f"&enabled_features=[]"
            f"&disabled_features=[]"
            f"&locale=en"
            f"&utm_source=localhost"
            f"&utm_medium=widget_new"
            f"&utm_campaign=chart"
        )

        encoded_url = urllib.parse.quote(tv_url, safe="")

        # Screenshot API call with optimized settings for forex charts
        screenshot_url = (
            f"https://api.screenshotone.com/take"
            f"?access_key={SCREENSHOT_ONE_KEY}"
            f"&url={encoded_url}"
            f"&format=png"
            f"&viewport_width=1280"
            f"&viewport_height=720"
            f"&device_scale_factor=1"
            f"&block_ads=true"
            f"&block_cookie_banners=true"
            f"&block_banners_by_heuristics=false"
            f"&block_trackers=true"
            f"&delay=3"  # Wait for chart to fully load
            f"&timeout=30"
        )

        # Fetch screenshot with retry logic
        max_retries = 2
        last_error = None
        resp = None
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.get(screenshot_url)
                
                if resp.status_code == 200 and resp.content:
                    # Success!
                    break
                else:
                    last_error = f"Status {resp.status_code}"
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)  # Wait before retry
                        continue
            except httpx.TimeoutException:
                last_error = "Timeout"
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
        
        # Check if we got a valid response
        if not resp or resp.status_code != 200 or not resp.content:
            # Delete loading message
            try:
                await loading_msg.delete()
            except:
                pass
            
            # Try to extract error details
            err_txt = None
            try:
                if resp:
                    err_json = resp.json()
                    err_txt = err_json.get("error_message") or err_json.get("message") or str(err_json)[:300]
            except Exception:
                err_txt = last_error or "Unknown error"

            # Notify admin
            if ADMIN_ID:
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=(
                            f"❌ FXChart Screenshot API Error\n"
                            f"Pair: {normalized_pair}\n"
                            f"TradingView Symbol: {tv_symbol}\n"
                            f"Timeframe: {timeframe}\n"
                            f"User: {user_id}\n"
                            f"Error: {escape_markdown(str(err_txt), version=2)}"
                        ),
                        parse_mode="MarkdownV2"
                    )
                except Exception:
                    pass

            return await update.message.reply_text(
                f"⚠️ <b>Failed to generate chart for {pair_info['name']}</b>\n\n"
                f"<b>Possible reasons:</b>\n"
                f"• TradingView temporarily unavailable\n"
                f"• Screenshot service timeout\n"
                f"• Network connectivity issue\n\n"
                f"<b>What to try:</b>\n"
                f"• Wait 30 seconds and try again\n"
                f"• Try a different timeframe (e.g., <code>1h</code>)\n"
                f"• Try a major pair like <code>EURUSD</code>\n"
                f"• Contact support if issue persists\n\n"
                f"<i>Error: {err_txt}</i>",
                parse_mode=ParseMode.HTML
            )

        # Delete loading message before sending photo
        try:
            await loading_msg.delete()
        except:
            pass

        # Send chart
        image_bytes = resp.content
        bio = io.BytesIO(image_bytes)
        bio.name = f"{normalized_pair}_{timeframe}.png"
        bio.seek(0)

        # Create caption with pair details
        caption = (
            f"💱 <b>{pair_info['name']}</b> ({pair_info['category']} Pair)\n"
            f"⏰ Timeframe: {timeframe.upper()}\n"
            f"📊 Source: TradingView\n"
            f"<i>{pair_info['description']}</i>"
        )
        
        await update.message.reply_photo(
            photo=InputFile(bio, filename=bio.name), 
            caption=caption, 
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        # Delete loading message if it exists
        try:
            if 'loading_msg' in locals():
                await loading_msg.delete()
        except:
            pass
        
        # Notify admin with detailed error info
        if ADMIN_ID:
            try:
                error_details = (
                    f"❌ FXChart Exception\n"
                    f"User: {user_id}\n"
                    f"Pair Input: {pair if 'pair' in locals() else 'unknown'}\n"
                    f"Normalized: {normalized_pair if 'normalized_pair' in locals() else 'unknown'}\n"
                    f"Timeframe: {timeframe if 'timeframe' in locals() else 'unknown'}\n"
                    f"Error: `{escape_markdown(str(e)[:500], version=2)}`"
                )
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=error_details,
                    parse_mode="MarkdownV2"
                )
            except Exception:
                pass
        
        print(f"FXChart error: {e}")
        import traceback
        traceback.print_exc()
        
        await update.message.reply_text(
            "⚠️ <b>Unexpected Error</b>\n\n"
            "Could not generate chart due to an unexpected error.\n\n"
            "Please try again in a moment. If the issue persists, contact support.",
            parse_mode=ParseMode.HTML
        )
