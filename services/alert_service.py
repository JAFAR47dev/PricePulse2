import sqlite3
import time
from telegram import Update
from telegram.ext import ContextTypes
from services.price_service import get_crypto_price
from models.db import get_connection
from collections import defaultdict
import time
import asyncio
from datetime import datetime
#from utils.prices import get_crypto_prices
import traceback
from services.alert_checkers import (
    check_price_alerts,
    check_percent_alerts,
    check_volume_alerts,
    check_risk_alerts,
    check_custom_alerts,
    check_portfolio_alerts,
    check_watchlist_alerts
)

async def check_alerts(context):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        indicator_cache = defaultdict(dict)

        # 1. Gather all unique symbols from alert tables
        all_symbols = set()
        for table in [
            "alerts", "percent_alerts", "volume_alerts",
            "risk_alerts", "custom_alerts", "portfolio_alerts", "watchlist"
        ]:
            cursor.execute(f"SELECT DISTINCT symbol FROM {table}")
            all_symbols.update(row[0] for row in cursor.fetchall())

        # 2. Fetch all prices once
        symbol_prices = {}
        for symbol in all_symbols:
            try:
                symbol_prices[symbol] = get_crypto_price(symbol)
            except Exception as e:
                print(f"❌ Failed to get price for {symbol}: {e}")
                traceback.print_exc()

        # 3. Modular alert checking
        await check_price_alerts(context, symbol_prices)
        await check_percent_alerts(context, symbol_prices)
        await check_volume_alerts(context, symbol_prices)
        await check_risk_alerts(context, symbol_prices)
        await check_custom_alerts(context, symbol_prices)
        await check_portfolio_alerts(context, symbol_prices)
        await check_watchlist_alerts(context, symbol_prices)

    except Exception as e:
        print("❌ Error in check_alerts master function:", e)
        traceback.print_exc()

    finally:
        try:
            conn.close()
        except:
            pass
    
def get_cached_price(symbol, ttl=60):
    symbol = symbol.upper()
    now = time.time()

    # If cache exists and is fresh, return it
    if symbol in price_cache:
        cached = price_cache[symbol]
        if now - cached["timestamp"] < ttl:
            return cached["price"]

    # Otherwise, fetch fresh from API
    price = get_crypto_price(symbol)
    if price is not None:
        price_cache[symbol] = {"price": price, "timestamp": now}
    return price
    
async def send_auto_delete(context, message_func, *args, **kwargs):
    """Wraps any send_message, send_photo, etc., and schedules deletion based on user settings."""
    user_id = kwargs.get("chat_id")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT autodelete FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    msg = await message_func(*args, **kwargs)

    if result and result[0]:
        delay = result[0] * 60
        context.job_queue.run_once(
            lambda c: asyncio.create_task(delete_message_safe(c, chat_id=user_id, message_id=msg.message_id)),
            when=delay
        )
    return msg
    


def delete_all_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    tables = [
        "alerts",              # price alerts
        "percent_alerts",
        "volume_alerts",
        "risk_alerts",
        "custom_alerts",
        "portfolio_alerts",
        "watchlist"
    ]

    for table in tables:
        # Delete all user alerts
        cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))

        # Reset autoincrement (global)
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))

    conn.commit()
    conn.close()
    
def start_alert_checker(job_queue):
    from telegram.ext import ContextTypes
    job_queue.run_repeating(check_alerts, interval=30, first=10)