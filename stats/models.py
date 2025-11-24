from models.db import get_connection
from datetime import datetime, timedelta

def get_top_commands(cursor, interval):
    cursor.execute(f"""
        SELECT command, COUNT(*) AS total
        FROM command_usage
        WHERE used_at >= DATETIME('now', '-{interval}')
        GROUP BY command
        ORDER BY total DESC
        LIMIT 5
    """)
    return cursor.fetchall()

def get_least_commands(cursor, interval):
    cursor.execute(f"""
        SELECT command, COUNT(*) AS total
        FROM command_usage
        WHERE used_at >= DATETIME('now', '-{interval}')
        GROUP BY command
        ORDER BY total ASC
        LIMIT 5
    """)
    return cursor.fetchall()
    
def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    stats = {}

    # Total users
    cursor.execute("SELECT COUNT(*) FROM users")
    stats["total_users"] = cursor.fetchone()[0]

    # Pro vs Free
    cursor.execute("SELECT COUNT(*) FROM users WHERE plan LIKE 'pro%'")
    stats["pro_users"] = cursor.fetchone()[0]
    stats["free_users"] = stats["total_users"] - stats["pro_users"]

    # Active users (last 24h / 7d / 30d)
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active >= DATETIME('now', '-1 day')")
    stats["active_24h"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active >= DATETIME('now', '-7 days')")
    stats["active_7d"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active >= DATETIME('now', '-30 days')")
    stats["active_30d"] = cursor.fetchone()[0]
    
    stats["top_commands_24h"] = get_top_commands(cursor, "1 day")
    stats["least_commands_24h"] = get_least_commands(cursor, "1 day")

    stats["top_commands_7d"] = get_top_commands(cursor, "7 days")
    stats["least_commands_7d"] = get_least_commands(cursor, "7 days")

    stats["top_commands_30d"] = get_top_commands(cursor, "30 days")
    stats["least_commands_30d"] = get_least_commands(cursor, "30 days")
    

    # Alerts by type
    for table in [
        "alerts", "percent_alerts", "volume_alerts",
        "risk_alerts", "custom_alerts", "portfolio_alerts", "watchlist"
    ]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cursor.fetchone()[0]

    
    # Referrals
    cursor.execute("SELECT COUNT(*) FROM referrals")
    stats["total_referrals"] = cursor.fetchone()[0]

    # Top referrer
    cursor.execute("""
        SELECT referrer_id, COUNT(*) AS count
        FROM referrals
        GROUP BY referrer_id
        ORDER BY count DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    stats["top_referrer"] = row[0] if row else None
    stats["top_referral_count"] = row[1] if row else 0

    conn.close()
    return stats
    
