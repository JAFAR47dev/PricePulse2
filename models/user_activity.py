from models.db import get_connection
from datetime import datetime
import sqlite3

async def update_last_active(user_id: int, command_name: str = None):
    """
    Safely updates the user's last_active timestamp and logs command usage.
    Fully protected against 'database is locked' issues.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Update last_active
        cursor.execute(
            "UPDATE users SET last_active = ? WHERE user_id = ?",
            (datetime.utcnow().isoformat(), user_id)
        )

        # Log command usage if provided
        if command_name:
            cursor.execute(
                "INSERT INTO command_usage (command, used_at) VALUES (?, ?)",
                (command_name, datetime.utcnow().isoformat())
            )

        conn.commit()

    except sqlite3.OperationalError as e:
        # Log but DO NOT crash bot
        print("⚠️ SQLite OperationalError in update_last_active:", e)

    except Exception as e:
        # Catch unexpected errors
        print("⚠️ Unexpected error in update_last_active:", e)

    finally:
        if conn:
            conn.close()