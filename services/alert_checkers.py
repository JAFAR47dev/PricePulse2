from models.db import get_connection
from utils.prices import get_crypto_prices
from utils.notification_service import send_auto_delete
import traceback
from collections import defaultdict
from utils.indicators import get_cached_rsi, get_cached_macd, get_cached_ema


async def check_price_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, user_id, symbol, condition, target_price, repeat FROM alerts")
        for alert_id, user_id, symbol, cond, target, repeat in cursor.fetchall():
            price = symbol_prices.get(symbol)
            if price is None:
                continue
            
            if (cond == ">" and price > target) or (cond == "<" and price < target):
                try:
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🔔 *Price Alert: {symbol}*\nCurrent price: ${price:.2f} {cond} {target}",
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)
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
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=f"📉 *% Alert for {symbol}*\nChange: {change:.2f}% from ${base_price:.2f}\nNow: ${price:.2f}",
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)
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


from utils.indicators import get_volume_comparison  # if located elsewhere, adjust import

async def check_volume_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()

    to_delete = []

    try:
        cursor.execute("SELECT id, user_id, symbol, timeframe, multiplier, repeat FROM volume_alerts")
        rows = cursor.fetchall()

        for alert_id, user_id, symbol, tf, mult, repeat in rows:
            try:
                current_vol, avg_vol = await get_volume_comparison(symbol, tf)
                if current_vol >= avg_vol * mult:
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=f"📊 *Volume Alert: {symbol}*\n{tf} Volume = {current_vol:.2f}, exceeds {mult}× average ({avg_vol:.2f})",
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)
                    if not repeat:
                        to_delete.append(alert_id)
            except Exception as e:
                print(f"Volume alert error: {e}")
                traceback.print_exc()

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
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🛡 *Risk Alert for {symbol}*\n"
                            f"Price hit ${price:.2f}.\nSL: {stop_price}, TP: {take_price}"
                        ),
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)

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
                if r_cond in [">", "<"] and r_val is not None:
                    if symbol not in indicator_cache:
                        indicator_cache[symbol] = {}
                    if "rsi" not in indicator_cache[symbol]:
                        indicator_cache[symbol]["rsi"] = await get_cached_rsi(symbol)
                    rsi = indicator_cache[symbol]["rsi"]
                    indicator_match = (r_cond == ">" and rsi > r_val) or (r_cond == "<" and rsi < r_val)

                elif r_cond == "macd":
                    if symbol not in indicator_cache:
                        indicator_cache[symbol] = {}
                    if "macd" not in indicator_cache[symbol]:
                        indicator_cache[symbol]["macd"] = await get_cached_macd(symbol)
                    macd, signal, hist = indicator_cache[symbol]["macd"]
                    indicator_match = hist > 0

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
                print(f"Custom alert indicator error: {e}")
                traceback.print_exc()
                continue

            if price_match and indicator_match:
                try:
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🧠 *Custom Alert for {symbol}*\n"
                            f"Price: ${price:.2f} ({p_cond}{p_val}) ✅\n"
                            f"Indicator: `{r_cond}` ✅"
                        ),
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)
                    if not repeat:
                        to_delete.append(alert_id)
                except Exception as e:
                    print(f"Custom alert send error: {e}")
                    traceback.print_exc()
            else:
                print(f"Skipped alert for {symbol}: price_match={price_match}, indicator_match={indicator_match}")

        if to_delete:
            cursor.executemany("DELETE FROM custom_alerts WHERE id = ?", [(aid,) for aid in to_delete])
            conn.commit()

    finally:
        conn.close()

async def check_portfolio_alerts(context, symbol_prices):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT p.user_id, p.symbol, p.amount, l.loss_limit, l.profit_target
            FROM portfolio_alerts p
            LEFT JOIN portfolio_limits l ON p.user_id = l.user_id
        """)

        portfolios = defaultdict(list)
        limits = {}

        for user_id, symbol, quantity, loss_limit, profit_target in cursor.fetchall():
            portfolios[user_id].append((symbol, quantity))
            limits[user_id] = {
                "loss_limit": loss_limit,
                "profit_target": profit_target
            }

        for user_id, assets in portfolios.items():
            limit_data = limits.get(user_id, {})
            loss_limit = limit_data.get("loss_limit")
            profit_target = limit_data.get("profit_target")

            if loss_limit is None and profit_target is None:
                continue

            total_value = 0
            missing_data = False
            for symbol, amount in assets:
                price = symbol_prices.get(symbol)
                if price is None:
                    missing_data = True
                    break
                total_value += price * amount

            if missing_data:
                continue

            if loss_limit is not None and total_value <= loss_limit:
                try:
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚠️ *Portfolio Loss Alert*\n"
                            f"Your total value dropped to ${total_value:,.2f}.\n"
                            f"Loss limit was: ${loss_limit:,.2f}"
                        ),
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)
                    cursor.execute("UPDATE portfolio_limits SET loss_limit = NULL WHERE user_id = ?", (user_id,))
                except Exception as e:
                    print(f"Portfolio loss alert error: {e}")
                    traceback.print_exc()

            elif profit_target is not None and total_value >= profit_target:
                try:
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🎯 *Portfolio Target Reached*\n"
                            f"Your total value is now ${total_value:,.2f}.\n"
                            f"Target goal was: ${profit_target:,.2f}"
                        ),
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)
                    cursor.execute("UPDATE portfolio_limits SET profit_target = NULL WHERE user_id = ?", (user_id,))
                except Exception as e:
                    print(f"Portfolio profit alert error: {e}")
                    traceback.print_exc()

        conn.commit()

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
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"📡 *Watchlist Alert for {symbol}*\n"
                            f"Price moved ±{threshold:.1f}% from ${base_price:.2f}.\n"
                            f"Timeframe: `{timeframe}`\n"
                            f"Current: ${price:.2f} ({change:.2f}% change)"
                        ),
                        parse_mode="Markdown"
                    )
                    await send_auto_delete(context, msg)
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