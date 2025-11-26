from models.db import get_connection
from utils.prices import get_crypto_prices
import traceback
from collections import defaultdict
from utils.indicators import get_cached_rsi, get_cached_macd, get_cached_ema
import os
import time
import requests
from collections import defaultdict
import traceback, time, aiohttp, os
from dotenv import load_dotenv
from models.db import get_connection
from models.alert import get_portfolio_value_limits  # <-- import your helper

load_dotenv()
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Cache fiat prices for 5 minutes
fiat_cache = {}
CACHE_DURATION = 300  # 5 minutes


async def get_fiat_price(symbol):
    """
    Fetch fiat price (USD base) from Twelve Data API, with 5-minute caching.
    """
    symbol = symbol.upper()

    # Direct 1:1 mappings
    if symbol in ["USD", "USDT"]:
        return 1.0

    # Return cached value if not expired
    if symbol in fiat_cache and time.time() - fiat_cache[symbol]["time"] < CACHE_DURATION:
        return fiat_cache[symbol]["value"]

    # Supported fiats you want to fetch live (vs USD)
    supported_fiats = ["EUR", "GBP", "JPY", "NGN", "CAD", "AUD", "CHF"]
    if symbol not in supported_fiats:
        return None

    try:
        url = f"https://api.twelvedata.com/price?symbol={symbol}/USD&apikey={TWELVE_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                data = await response.json()
                if "price" in data:
                    price = float(data["price"])
                    fiat_cache[symbol] = {"value": price, "time": time.time()}
                    return price
    except Exception as e:
        print(f"⚠️ Error fetching fiat price for {symbol}: {e}")
    return None
    

async def check_price_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, user_id, symbol, condition, target_price, repeat FROM alerts")
        for alert_id, user_id, symbol, cond, target, repeat in cursor.fetchall():
            price = symbol_prices.get(symbol.upper())  # normalize

            if price is None:
                continue

            if (cond == ">" and price > target) or (cond == "<" and price < target):
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🔔 *Price Alert: {symbol.upper()}*\n"
                            f"Current price: ${price:.2f} {cond} {target}"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Price alert error: {e}")
                    traceback.print_exc()

                if not repeat:
                    cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))

        conn.commit()
    finally:
        conn.close()


async def check_percent_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()

    to_delete = []
    to_update = []

    try:
        cursor.execute("SELECT id, user_id, symbol, base_price, threshold_percent, repeat FROM percent_alerts")
        rows = cursor.fetchall()

        for alert_id, user_id, symbol, base_price, threshold_percent, repeat in rows:
            price = symbol_prices.get(symbol)
            
            if price is None:
                continue

            change = abs((price - base_price) / base_price * 100)

            if change >= threshold_percent:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"📉 *% Alert for {symbol}*\n"
                            f"Change: {change:.2f}% from ${base_price:.2f}\n"
                            f"Now: ${price:.2f}"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Percent alert error: {e}")
                    traceback.print_exc()

                if repeat:
                    to_update.append((price, alert_id))
                else:
                    to_delete.append(alert_id)

        # Batch update and delete
        if to_update:
            cursor.executemany("UPDATE percent_alerts SET base_price = ? WHERE id = ?", to_update)
        if to_delete:
            cursor.executemany("DELETE FROM percent_alerts WHERE id = ?", [(aid,) for aid in to_delete])

        conn.commit()
    finally:
        conn.close()


import traceback
from utils.indicators import get_volume_comparison

async def check_volume_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()
    to_delete = []

    try:
        cursor.execute("SELECT id, user_id, symbol, timeframe, multiplier, repeat FROM volume_alerts")
        rows = cursor.fetchall()

        for alert_id, user_id, symbol, tf, mult, repeat in rows:
            try:
                # ✅ Use the cached CryptoCompare function instead of get_ohlcv
                current_vol, avg_vol = await get_volume_comparison(symbol, tf)

                # ✅ Skip bad data
                if not current_vol or not avg_vol:
                    continue

                # ✅ Check alert condition
                if current_vol >= avg_vol * mult:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"📊 *Volume Alert: {symbol}*\n"
                            f"Timeframe: {tf}\n"
                            f"Current Volume = `{current_vol:,.2f}` USD\n"
                            f"Average Volume = `{avg_vol:,.2f}` USD\n"
                            f"➡️ Exceeds `{mult}×` average!"
                        ),
                        parse_mode="Markdown"
                    )

                    # ✅ Delete if not repeat
                    if not repeat:
                        to_delete.append(alert_id)

            except Exception as e:
                print(f"Volume alert error for {symbol}: {e}")
                traceback.print_exc()

        # ✅ Remove completed one-time alerts
        if to_delete:
            cursor.executemany("DELETE FROM volume_alerts WHERE id = ?", [(aid,) for aid in to_delete])
            conn.commit()

    finally:
        conn.close()

async def check_risk_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()

    to_delete = []

    try:
        cursor.execute("SELECT id, user_id, symbol, stop_price, take_price, repeat FROM risk_alerts")
        rows = cursor.fetchall()

        for alert_id, user_id, symbol, stop_price, take_price, repeat in rows:
            price = symbol_prices.get(symbol)
            
            if price is None:
                continue

            if price <= stop_price or price >= take_price:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🛡 *Risk Alert for {symbol}*\n"
                            f"Price hit ${price:.2f}.\n"
                            f"SL: ${stop_price:.2f}, TP: ${take_price:.2f}"
                        ),
                        parse_mode="Markdown"
                    )

                    if not repeat:
                        to_delete.append(alert_id)

                except Exception as e:
                    print(f"Risk alert error: {e}")
                    traceback.print_exc()

        if to_delete:
            cursor.executemany("DELETE FROM risk_alerts WHERE id = ?", [(aid,) for aid in to_delete])
            conn.commit()

    finally:
        conn.close()

async def check_custom_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()
    to_delete = []
    indicator_cache = {}

    try:
        cursor.execute("""
            SELECT id, user_id, symbol, price_condition, price_value, 
                   rsi_condition, rsi_value, repeat 
            FROM custom_alerts
        """)
        rows = cursor.fetchall()

        for alert_id, user_id, symbol, p_cond, p_val, r_cond, r_val, repeat in rows:
            price = symbol_prices.get(symbol)
            
            if price is None:
                continue

            price_match = (p_cond == ">" and price > p_val) or (p_cond == "<" and price < p_val)
            indicator_match = False

            try:
                # RSI condition
                if r_cond in [">", "<"] and r_val is not None:
                    if symbol not in indicator_cache:
                        indicator_cache[symbol] = {}
                    if "rsi" not in indicator_cache[symbol]:
                        indicator_cache[symbol]["rsi"] = await get_cached_rsi(symbol)
                    rsi = indicator_cache[symbol]["rsi"]
                    indicator_match = (r_cond == ">" and rsi > r_val) or (r_cond == "<" and rsi < r_val)

                # MACD condition
                elif r_cond == "macd":
                    if symbol not in indicator_cache:
                        indicator_cache[symbol] = {}
                    if "macd" not in indicator_cache[symbol]:
                        indicator_cache[symbol]["macd"] = await get_cached_macd(symbol)
                    macd, signal, hist = indicator_cache[symbol]["macd"]
                    indicator_match = hist > 0

                # EMA condition (e.g. ema>20)
                elif r_cond.startswith("ema>"):
                    period = int(r_cond.split(">")[1])
                    if symbol not in indicator_cache:
                        indicator_cache[symbol] = {}
                    ema_key = f"ema{period}"
                    if ema_key not in indicator_cache[symbol]:
                        indicator_cache[symbol][ema_key] = await get_cached_ema(symbol, period)
                    ema = indicator_cache[symbol][ema_key]
                    indicator_match = ema is not None and price > ema

            except Exception as e:
                print(f"Custom alert indicator error for {symbol}: {e}")
                traceback.print_exc()
                continue

            # If both price and indicator match, trigger alert
            if price_match and indicator_match:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🧠 *Custom Alert for {symbol}*\n"
                            f"Price: ${price:.2f} ({p_cond}{p_val}) ✅\n"
                            f"Indicator: `{r_cond}` ✅"
                        ),
                        parse_mode="Markdown"
                    )

                    if not repeat:
                        to_delete.append(alert_id)

                except Exception as e:
                    print(f"Custom alert send error for {symbol}: {e}")
                    traceback.print_exc()
            else:
                print(f"Skipped alert for {symbol}: price_match={price_match}, indicator_match={indicator_match}")

        if to_delete:
            cursor.executemany("DELETE FROM custom_alerts WHERE id = ?", [(aid,) for aid in to_delete])
            conn.commit()

    finally:
        conn.close()



async def check_portfolio_alerts(context, symbol_prices):
    from collections import defaultdict
    import traceback

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Fetch all portfolio holdings
        cursor.execute("SELECT user_id, symbol, amount FROM portfolio")
        rows = cursor.fetchall()
        if not rows:
            return

        portfolios = defaultdict(list)
        for user_id, symbol, amount in rows:
            portfolios[user_id].append((symbol, amount))

        for user_id, assets in portfolios.items():
            # Fetch portfolio limit/target + repeat flags
            limit_data = get_portfolio_value_limits(user_id)
            if not limit_data:
                continue

            loss_limit = limit_data.get("loss_limit")
            profit_target = limit_data.get("profit_target")
            repeat_loss = limit_data.get("repeat_loss", 0)       # 0 = one-time, 1 = repeat
            repeat_profit = limit_data.get("repeat_profit", 0)   # 0 = one-time, 1 = repeat

            total_value = 0
            for symbol, amount in assets:
                symbol = symbol.upper().strip()

                fiat_price = await get_fiat_price(symbol)
                if fiat_price is not None:
                    price = fiat_price
                else:
                    price = symbol_prices.get(symbol) or symbol_prices.get(f"{symbol}USDT")

                if price is None:
                    continue

                total_value += price * amount

            # -------------------------------
            # 🔻 LOSS LIMIT CHECK
            # -------------------------------
            if loss_limit is not None and total_value <= loss_limit:
                try:
                    if context:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"⚠️ *Portfolio Loss Alert*\n"
                                f"Your total value dropped to **${total_value:,.2f}**.\n"
                                f"Loss limit: **${loss_limit:,.2f}**"
                            ),
                            parse_mode="Markdown"
                        )

                    # Remove limit ONLY if not repeating
                    if repeat_loss == 0:
                        cursor.execute(
                            "UPDATE portfolio_limits SET loss_limit = NULL WHERE user_id = ?",
                            (user_id,)
                        )

                except Exception:
                    traceback.print_exc()

            # -------------------------------
            # 🎯 PROFIT TARGET CHECK
            # -------------------------------
            if profit_target is not None and total_value >= profit_target:
                try:
                    if context:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"🎯 *Portfolio Target Reached*\n"
                                f"Your total value is now **${total_value:,.2f}**.\n"
                                f"Target goal: **${profit_target:,.2f}**"
                            ),
                            parse_mode="Markdown"
                        )

                    # Remove limit ONLY if not repeating
                    if repeat_profit == 0:
                        cursor.execute(
                            "UPDATE portfolio_limits SET profit_target = NULL WHERE user_id = ?",
                            (user_id,)
                        )

                except Exception:
                    traceback.print_exc()

        conn.commit()

    except Exception:
        traceback.print_exc()

    finally:
        conn.close()
        

async def check_watchlist_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT user_id, symbol, base_price, threshold_percent, timeframe 
            FROM watchlist 
            WHERE threshold_percent > 0
        """)

        for user_id, symbol, base_price, threshold, timeframe in cursor.fetchall():
            price = symbol_prices.get(symbol)
            
            if price is None:
                continue

            change = abs((price - base_price) / base_price * 100)
            if change >= threshold:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"📡 *Watchlist Alert for {symbol}*\n"
                            f"Price moved ±{threshold:.1f}% from ${base_price:.2f}.\n"
                            f"Timeframe: `{timeframe}`\n"
                            f"Current: ${price:.2f} ({change:.2f}% change)"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Watchlist alert error: {e}")
                    traceback.print_exc()

                cursor.execute(
                    "UPDATE watchlist SET base_price = ? WHERE user_id = ? AND symbol = ?",
                    (price, user_id, symbol)
                )

        conn.commit()

    finally:
        conn.close()