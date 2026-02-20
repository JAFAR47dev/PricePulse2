from models.db import get_connection
from models.analytics_db import get_analytics_connection
from datetime import datetime
import sqlite3

async def update_last_active(user_id: int, command_name: str = None):
    """
    Safely updates the user's last_active timestamp in core DB
    and logs command usage in analytics DB.
    Fully protected against 'database is locked' issues.
    """

    # ---------------------------
    # 1️⃣ Update core users table
    # ---------------------------
    core_conn = None
    try:
        core_conn = get_connection()
        core_cursor = core_conn.cursor()

        core_cursor.execute(
            "UPDATE users SET last_active = ? WHERE user_id = ?",
            (datetime.utcnow().isoformat(), user_id)
        )

        core_conn.commit()

    except sqlite3.OperationalError as e:
        print("⚠️ SQLite OperationalError in core DB:", e)
    except Exception as e:
        print("⚠️ Unexpected error in core DB:", e)
    finally:
        if core_conn:
            core_conn.close()

    # ---------------------------
    # 2️⃣ Log command usage in analytics DB
    # ---------------------------
    if command_name:
        analytics_conn = None
        try:
            analytics_conn = get_analytics_connection()
            analytics_cursor = analytics_conn.cursor()

            analytics_cursor.execute(
                "INSERT INTO command_usage (command, used_at) VALUES (?, ?)",
                (command_name, datetime.utcnow().isoformat())
            )

            analytics_conn.commit()

        except sqlite3.OperationalError as e:
            print("⚠️ SQLite OperationalError in analytics DB:", e)
        except Exception as e:
            print("⚠️ Unexpected error in analytics DB:", e)
        finally:
            if analytics_conn:
                analytics_conn.close()
                

import sqlite3
from datetime import datetime, timedelta

async def cleanup_old_analytics(context):
    """
    Delete analytics records older than 31 days.
    This runs as a background job via Telegram's job queue.
    
    Args:
        context: Required by telegram.ext JobQueue (even if unused)
    """
    analytics_conn = None
    try:
        analytics_conn = get_analytics_connection()
        analytics_cursor = analytics_conn.cursor()
        
        # Calculate cutoff date (31 days ago)
        cutoff_date = (datetime.utcnow() - timedelta(days=31)).isoformat()
        
        # Delete old records
        analytics_cursor.execute(
            "DELETE FROM command_usage WHERE used_at < ?",
            (cutoff_date,)
        )
        
        deleted = analytics_cursor.rowcount
        analytics_conn.commit()
        
        if deleted > 0:
            print(f"🧹 Analytics cleanup: Deleted {deleted} records older than 31 days")
        else:
            print("✓ Analytics cleanup: No old records to delete")
        
        return deleted
    
    except sqlite3.OperationalError as e:
        print(f"⚠️ SQLite error during analytics cleanup: {e}")
        return 0
    except Exception as e:
        print(f"⚠️ Unexpected error during analytics cleanup: {e}")
        return 0
    finally:
        if analytics_conn:
            analytics_conn.close()
                            