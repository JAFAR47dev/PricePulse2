from models.db import get_connection
from datetime import datetime

async def update_last_active(user_id: int):
    """Update user's last_active time whenever they interact."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET last_active = ? WHERE user_id = ?",
        (datetime.utcnow().isoformat(), user_id)
    )
    conn.commit()
    conn.close()