from models.db import get_connection
from datetime import datetime

async def update_last_active(user_id: int, command_name: str = None):
    """
    Updates user's last_active timestamp and optionally logs the command usage.
    """
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
            "INSERT INTO command_usage (command) VALUES (?)",
            (command_name,)
        )

    conn.commit()
    conn.close()