from models.db import get_connection

def drop_command_usage_table():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS command_usage")

    conn.commit()
    conn.close()

    print("✅ command_usage table dropped from core database")

# Run the function directly
if __name__ == "__main__":
    drop_command_usage_table()
    