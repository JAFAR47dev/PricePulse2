from models.db import get_connection

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

    # Alerts by type
    for table in [
        "alerts", "percent_alerts", "volume_alerts",
        "risk_alerts", "custom_alerts", "portfolio_alerts", "watchlist"
    ]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cursor.fetchone()[0]

    # Task Completion
    cursor.execute("""
        SELECT COUNT(*) FROM task_progress
        WHERE task1_done = 1 AND task2_done = 1 AND task3_done = 1 AND approved_by_admin = 1
    """)
    stats["task_completers"] = cursor.fetchone()[0]

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