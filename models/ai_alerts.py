import json
from models.db import get_connection

def save_ai_strategy(user_id: int, symbol: str, conditions: list[str], summary: str):
    """Save a new AI strategy alert to the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ai_alerts (user_id, symbol, conditions, summary)
        VALUES (?, ?, ?, ?)
    """, (user_id, symbol.upper(), json.dumps(conditions), summary))

    conn.commit()
    conn.close()