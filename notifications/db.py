# notifications/db.py

import sqlite3
import time
from typing import Optional
from models.db import get_connection as _base_get_connection


def _get_db() -> sqlite3.Connection:
    """
    Wraps the project's get_connection() and adds row_factory = sqlite3.Row
    so all queries return rows accessible by column name (row["is_enabled"])
    instead of by index (row[0]).

    This is the ONLY function in this file that opens a connection.
    Every other function calls _get_db() — never get_connection() directly.
    """
    conn = _base_get_connection()
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================================
# SCHEMA MIGRATION
# ============================================================================

def migrate():
    """
    Create all notifications tables if they don't exist.
    Safe to call on every bot startup — uses IF NOT EXISTS throughout.
    Called from main.py before the bot starts.
    """
    db = _get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS notification_prefs (
            user_id         INTEGER PRIMARY KEY,
            is_enabled      INTEGER DEFAULT 1,
            morning_time    TEXT    DEFAULT '07:00',
            evening_time    TEXT    DEFAULT '20:00',
            frequency       TEXT    DEFAULT 'twice',
            preferred_tf    TEXT    DEFAULT '1h',
            created_at      REAL    DEFAULT (strftime('%s','now')),
            updated_at      REAL    DEFAULT (strftime('%s','now'))
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS signal_alerts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            symbol           TEXT    NOT NULL DEFAULT 'ANY',
            strategy_key     TEXT    NOT NULL DEFAULT 'ANY',
            timeframe        TEXT    NOT NULL DEFAULT '1h',
            min_score        INTEGER NOT NULL DEFAULT 5,
            is_active        INTEGER NOT NULL DEFAULT 1,
            cooldown_minutes INTEGER NOT NULL DEFAULT 240,
            created_at       REAL    DEFAULT (strftime('%s','now')),
            last_triggered   REAL    DEFAULT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            alert_type   TEXT    NOT NULL,
            symbol       TEXT,
            strategy_key TEXT,
            timeframe    TEXT,
            score        INTEGER,
            price        REAL,
            sent_at      REAL    DEFAULT (strftime('%s','now'))
        )
    """)

    db.commit()
    print("[notifications] ✅ DB migration complete")


# ============================================================================
# notification_prefs QUERIES
# ============================================================================

def get_prefs(user_id: int) -> Optional[sqlite3.Row]:
    db = _get_db()
    return db.execute(
        "SELECT * FROM notification_prefs WHERE user_id = ?",
        (user_id,)
    ).fetchone()


def ensure_prefs(user_id: int) -> sqlite3.Row:
    db = _get_db()
    db.execute("""
        INSERT OR IGNORE INTO notification_prefs (user_id)
        VALUES (?)
    """, (user_id,))
    db.commit()
    return get_prefs(user_id)


def update_prefs(user_id: int, **kwargs) -> None:
    allowed = {
        "is_enabled", "morning_time", "evening_time",
        "frequency", "preferred_tf"
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    fields["updated_at"] = time.time()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]

    db = _get_db()
    db.execute(
        f"UPDATE notification_prefs SET {set_clause} WHERE user_id = ?",
        values
    )
    db.commit()


def get_all_enabled_users() -> list:
    db = _get_db()
    return db.execute(
        "SELECT * FROM notification_prefs WHERE is_enabled = 1"
    ).fetchall()


# ============================================================================
# signal_alerts QUERIES
# ============================================================================

def get_user_alerts(user_id: int) -> list:
    db = _get_db()
    return db.execute(
        "SELECT * FROM signal_alerts WHERE user_id = ? AND is_active = 1",
        (user_id,)
    ).fetchall()


def get_all_active_alerts() -> list:
    db = _get_db()
    return db.execute(
        "SELECT * FROM signal_alerts WHERE is_active = 1"
    ).fetchall()


def add_alert(user_id: int, symbol: str = "ANY", strategy_key: str = "ANY",
              timeframe: str = "1h", min_score: int = 5,
              cooldown_minutes: int = 240) -> int:
    db = _get_db()

    count = db.execute(
        "SELECT COUNT(*) FROM signal_alerts WHERE user_id = ? AND is_active = 1",
        (user_id,)
    ).fetchone()[0]

    if count >= 5:
        raise ValueError("Maximum of 5 active alerts reached")

    cursor = db.execute("""
        INSERT INTO signal_alerts
            (user_id, symbol, strategy_key, timeframe, min_score, cooldown_minutes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, symbol.upper(), strategy_key, timeframe, min_score, cooldown_minutes))
    db.commit()
    return cursor.lastrowid


def deactivate_alert(alert_id: int, user_id: int) -> bool:
    db = _get_db()
    cursor = db.execute("""
        UPDATE signal_alerts
        SET is_active = 0
        WHERE id = ? AND user_id = ?
    """, (alert_id, user_id))
    db.commit()
    return cursor.rowcount > 0


def update_alert_triggered(alert_id: int) -> None:
    db = _get_db()
    db.execute(
        "UPDATE signal_alerts SET last_triggered = ? WHERE id = ?",
        (time.time(), alert_id)
    )
    db.commit()


# ============================================================================
# alert_history QUERIES
# ============================================================================

def was_recently_alerted(user_id: int, symbol: str, strategy_key: str,
                          timeframe: str, cooldown_minutes: int) -> bool:
    cutoff = time.time() - (cooldown_minutes * 60)
    db = _get_db()
    row = db.execute("""
        SELECT id FROM alert_history
        WHERE user_id      = ?
          AND symbol       = ?
          AND strategy_key = ?
          AND timeframe    = ?
          AND alert_type   = 'signal'
          AND sent_at      > ?
        LIMIT 1
    """, (user_id, symbol, strategy_key, timeframe, cutoff)).fetchone()
    return row is not None


def record_sent(user_id: int, alert_type: str, symbol: str = None,
                strategy_key: str = None, timeframe: str = None,
                score: int = None, price: float = None) -> None:
    db = _get_db()
    db.execute("""
        INSERT INTO alert_history
            (user_id, alert_type, symbol, strategy_key, timeframe, score, price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, alert_type, symbol, strategy_key, timeframe, score, price))
    db.commit()


def get_recent_history(user_id: int, limit: int = 10) -> list:
    db = _get_db()
    return db.execute("""
        SELECT * FROM alert_history
        WHERE user_id = ?
        ORDER BY sent_at DESC
        LIMIT ?
    """, (user_id, limit)).fetchall()
