import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYTICS_DB = os.path.join(BASE_DIR, "data", "analytics.db")

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)


def get_analytics_connection():
    conn = sqlite3.connect(
        ANALYTICS_DB,
        timeout=10,
        check_same_thread=False
    )

    # Optimized for write-heavy workloads
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    return conn