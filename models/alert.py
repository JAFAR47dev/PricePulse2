from models.db import get_connection

def create_price_alert(user_id, symbol, condition, target_price, repeat):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alerts (user_id, symbol, condition, target_price, repeat)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, symbol, condition, target_price, repeat))
    conn.commit()
    conn.close()
    
def create_percent_alert(user_id, symbol, base_price, threshold_percent, repeat):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO percent_alerts (user_id, symbol, base_price, threshold_percent, repeat)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, symbol, base_price, threshold_percent, repeat)
    )
    conn.commit()
    conn.close()
    
def create_volume_alert(user_id, symbol, multiplier, timeframe, repeat):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO volume_alerts (user_id, symbol, multiplier, timeframe, repeat)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, symbol, multiplier, timeframe, repeat)
    )
    conn.commit()
    conn.close()
    
def create_risk_alert(user_id, symbol, stop_price, take_price, repeat):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO risk_alerts (user_id, symbol, stop_price, take_price, repeat)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, symbol, stop_price, take_price, repeat)
    )
    conn.commit()
    conn.close()
    
    
import json
def create_indicator_alert(user_id, symbol, indicator, operator, value, timeframe="1h", repeat=0):
    conn = get_connection()
    cursor = conn.cursor()

    condition_json = json.dumps({"operator": operator, "value": value})

    cursor.execute(
        """
        INSERT INTO indicator_alerts (user_id, symbol, indicator, condition, timeframe, repeat)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            symbol.upper(),
            indicator.upper(),
            condition_json,
            timeframe,
            repeat
        )
    )

    conn.commit()
    conn.close()
    
    
    
#def count_user_price_alerts(user_id):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute("SELECT COUNT(*) FROM alerts WHERE user_id = ?", (user_id,))
#    count = cursor.fetchone()[0]
#    conn.close()
#    return count
#    
# 
#def update_price_alert(alert_id, condition, new_price):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute(
#        "UPDATE alerts SET condition = ?, target_price = ? WHERE id = ?",
#        (condition, new_price, alert_id)
#    )
#    conn.commit()
#    conn.close()
#    
#def update_percent_alert(alert_id, new_percent):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute(
#        "UPDATE percent_alerts SET threshold_percent = ? WHERE id = ?",
#        (new_percent, alert_id)
#    )
#    conn.commit()
#    conn.close()
#    
#def update_risk_alert(alert_id, stop_price, take_price):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute(
#        "UPDATE risk_alerts SET stop_price = ?, take_price = ? WHERE id = ?",
#        (stop_price, take_price, alert_id)
#    )
#    conn.commit()
#    conn.close()
#    
#def update_volume_alert(alert_id, multiplier):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute(
#        "UPDATE volume_alerts SET multiplier = ? WHERE id = ?",
#        (multiplier, alert_id)
#    )
#    conn.commit()
#    conn.close()
#    
#def update_custom_alert(alert_id, price_cond, price_val, indicator_cond, indicator_val):
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute("""
#        UPDATE custom_alerts
#        SET price_condition = ?, price_value = ?, rsi_condition = ?, rsi_value = ?
#        WHERE id = ?
#    """, (price_cond, price_val, indicator_cond, indicator_val, alert_id))
#    conn.commit()
#    conn.close()
#    
def get_price_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, condition, target_price, repeat
        FROM alerts
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows
    
def get_percent_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, base_price, threshold_percent, repeat
        FROM percent_alerts
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows
    
def get_volume_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, timeframe, multiplier, repeat
        FROM volume_alerts
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows
    
def get_risk_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, stop_price, take_price, repeat
        FROM risk_alerts
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows
    
import json

def get_indicator_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, indicator, condition, timeframe, repeat
        FROM indicator_alerts
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    parsed = []
    for row in rows:
        alert_id, symbol, indicator, condition_json, timeframe, repeat = row
        condition = json.loads(condition_json) if condition_json else {}

        parsed.append(
            (alert_id, symbol, indicator, condition, timeframe, repeat)
        )

    return parsed
    

from models.db import get_connection

def get_portfolio_value_limits(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT loss_limit, profit_target, repeat_limit_loss, repeat_limit_profit
            FROM portfolio_limits
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        if not row:
            return None

        loss_limit, profit_target, repeat_loss, repeat_profit = row

        # Only return if at least one limit exists
        if (loss_limit and loss_limit > 0) or (profit_target and profit_target > 0):
            return {
                "loss_limit": loss_limit,
                "profit_target": profit_target,
                "repeat_loss": repeat_loss if repeat_loss is not None else 0,
                "repeat_profit": repeat_profit if repeat_profit is not None else 0
            }
        else:
            return None

    except Exception as e:
        print("❌ Error fetching portfolio limits:", e)
        return None

    finally:
        conn.close()
        
    
def get_price_alert_by_id(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alerts WHERE user_id = ? AND id = ?", (user_id, alert_id))
    row = cursor.fetchone()
    conn.close()
    return row

def get_percent_alert_by_id(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM percent_alerts WHERE user_id = ? AND id = ?", (user_id, alert_id))
    row = cursor.fetchone()
    conn.close()
    return row

def get_volume_alert_by_id(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM volume_alerts WHERE user_id = ? AND id = ?", (user_id, alert_id))
    row = cursor.fetchone()
    conn.close()
    return row

def get_risk_alert_by_id(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM risk_alerts WHERE user_id = ? AND id = ?", (user_id, alert_id))
    row = cursor.fetchone()
    conn.close()
    return row


def get_indicator_alert_by_id(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, symbol, indicator, condition, timeframe, repeat, created_at
        FROM indicator_alerts
        WHERE user_id = ? AND id = ?
    """, (user_id, alert_id))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    alert_id, user_id, symbol, indicator, condition_json, timeframe, repeat, created_at = row
    condition = json.loads(condition_json) if condition_json else {}

    return (alert_id, user_id, symbol, indicator, condition, timeframe, repeat, created_at)
    
    

def delete_price_alert(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM alerts WHERE id = ? AND user_id = ?",
        (alert_id, user_id)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0
    
def delete_percent_alert(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM percent_alerts WHERE id = ? AND user_id = ?",
        (alert_id, user_id)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0
    
def delete_volume_alert(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM volume_alerts WHERE id = ? AND user_id = ?",
        (alert_id, user_id)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0
    
def delete_risk_alert(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM risk_alerts WHERE id = ? AND user_id = ?",
        (alert_id, user_id)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0
    
def delete_indicator_alert(user_id, alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM indicator_alerts WHERE id = ? AND user_id = ?",
        (alert_id, user_id)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0
    

from models.db import get_connection

def delete_portfolio_limit(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE portfolio_limits SET loss_limit = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def delete_portfolio_target(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE portfolio_limits SET profit_target = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success
    

    
def clear_user_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()