import sqlite3
from models.db import get_connection  # Adjust path if needed

def check_plans():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT plan FROM users")
    rows = cursor.fetchall()
    
    print("📦 Distinct plan values:")
    for row in rows:
        print("-", row[0])

    conn.close()

if __name__ == "__main__":
    check_plans()
    
    
