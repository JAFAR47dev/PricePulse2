import sqlite3
import os

# Path to the database file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, 'data', 'app.db')

# Ensure the /data directory exists
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)


def get_connection():
    """
    Returns a connection to the SQLite database with:
    - timeout to avoid 'database is locked'
    - check_same_thread=False for multi-thread access
    """
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)

    # Enable WAL mode to prevent database locking during concurrent access
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    return conn