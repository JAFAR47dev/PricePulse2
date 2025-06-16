from models.db import get_connection
    
def get_watchlist_alerts(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, base_price, threshold_percent, timeframe
        FROM watchlist
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows