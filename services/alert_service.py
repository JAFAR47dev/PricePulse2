import sqlite3
import time
from telegram import Update
from telegram.ext import ContextTypes
from utils.prices import get_crypto_prices
from models.db import get_connection
from collections import defaultdict
import time
import asyncio
from datetime import datetime
from telegram.ext import ContextTypes
from telegram import Bot
import traceback
from services.alert_checkers import (
    check_price_alerts,
    check_percent_alerts,
    check_volume_alerts,
    check_risk_alerts,
    check_indicator_alerts,
    check_portfolio_alerts,
    check_watchlist_alerts
)

async def check_alerts(context):
    try:
        print(f"\n🕒 [check_alerts] Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        conn = get_connection()
        cursor = conn.cursor()
        indicator_cache = defaultdict(dict)

        # 1️⃣ Gather all unique symbols from all alert tables
        all_symbols = set()
        alert_tables = [
            "alerts", "percent_alerts", "volume_alerts",
            "risk_alerts", "indicator_alerts", "portfolio", "watchlist"
        ]

        for table in alert_tables:
            try:
                cursor.execute(f"SELECT DISTINCT symbol FROM {table}")
                rows = cursor.fetchall()
                all_symbols.update(row[0] for row in rows)
            except Exception as e:
                print(f"⚠️ Skipped table {table}: {e}")

        print(f"📊 Found {len(all_symbols)} unique symbols to check.")

        # ✅ Fetch prices for ALL symbols at once to avoid rate limits
        symbol_prices = {}

        try:
            prices = await get_crypto_prices(list(all_symbols))

            if not prices or not isinstance(prices, dict):
                print("❌ Price API returned None or invalid format. Aborting price checks.")
                return

            for symbol in all_symbols:
                price = prices.get(symbol.upper()) or prices.get(symbol.lower())
                if price is not None:
                    symbol_prices[symbol] = price

        except Exception as e:
            print(f"❌ Price fetch failed: {e}")
            traceback.print_exc()
            return
    
        # 3️⃣ Run all modular alert checks safely
        all_checks_successful = True
        check_functions = [
            check_price_alerts,
            check_percent_alerts,
            check_volume_alerts,
            check_risk_alerts,
            check_indicator_alerts,
            check_portfolio_alerts,
            check_watchlist_alerts,
        ]

        for func in check_functions:
            try:
                await func(context, symbol_prices)
            except Exception as e:
                print(f"❌ Error in {func.__name__}: {e}")
                traceback.print_exc()
                all_checks_successful = False

        # ✅ Print one success message only if *all* checks succeeded
        if all_checks_successful:
            print(f"✅ [check_alerts] All alert checks completed successfully at {datetime.now().strftime('%H:%M:%S')}.\n")
        else:
            print(f"⚠️ [check_alerts] Completed with some errors at {datetime.now().strftime('%H:%M:%S')}.\n")

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
    price = get_crypto_prices(symbol)
    if price is not None:
        price_cache[symbol] = {"price": price, "timestamp": now}
    return price
    


def delete_all_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    tables = [
        "alerts",              # price alerts
        "percent_alerts",
        "volume_alerts",
        "risk_alerts",
        "indicator_alerts",
        "portfolio_limits",
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
    job_queue.run_repeating(check_alerts, interval=20, first=10)
    
