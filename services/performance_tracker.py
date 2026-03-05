import asyncio
import logging
from datetime import datetime, timedelta
from database.setup_db import get_connection
from services.setup_analyzer import fetch_candles

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    Real backtesting layer.

    Every /setup signal is logged to trade_setups with entry_price, SL, TP1, TP2.
    A background task (resolve_pending_outcomes) runs periodically and checks
    what price actually did at the 4h / 24h / 72h windows — scaled to the
    timeframe — and marks each setup as win / loss / open accordingly.

    get_similar_setups then returns real win rates, not illustrative numbers.
    """

    def __init__(self):
        self._ensure_schema()

    # ── Schema bootstrap ──────────────────────────────────────────────────────

    def _ensure_schema(self):
        """Create table if not exists, then migrate any missing columns."""
        conn = get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trade_setups (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER NOT NULL,
                    symbol        TEXT    NOT NULL,
                    timeframe     TEXT    NOT NULL,
                    score         INTEGER NOT NULL,
                    direction     TEXT    NOT NULL,
                    entry_price   REAL    NOT NULL,
                    stop_loss     REAL    NOT NULL,
                    take_profit_1 REAL    NOT NULL,
                    take_profit_2 REAL    NOT NULL,
                    risk_reward   REAL,
                    htf_trend     TEXT,
                    created_at    TEXT    NOT NULL,
                    price_4h      REAL,
                    price_24h     REAL,
                    price_72h     REAL,
                    outcome_4h    TEXT,
                    outcome_24h   TEXT,
                    outcome_72h   TEXT,
                    outcome       TEXT,
                    profit_pct    REAL,
                    resolved_at   TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_setups_symbol_tf
                    ON trade_setups (symbol, timeframe, score, created_at);
            """)

            existing = {
                row[1]
                for row in conn.execute("PRAGMA table_info(trade_setups)")
            }
            migrations = [
                ("risk_reward",  "REAL"),
                ("htf_trend",    "TEXT"),
                ("price_4h",     "REAL"),
                ("price_24h",    "REAL"),
                ("price_72h",    "REAL"),
                ("outcome_4h",   "TEXT"),
                ("outcome_24h",  "TEXT"),
                ("outcome_72h",  "TEXT"),
                ("outcome",      "TEXT"),
                ("profit_pct",   "REAL"),
                ("resolved_at",  "TEXT"),
            ]
            for col, col_type in migrations:
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE trade_setups ADD COLUMN {col} {col_type}"
                    )
                    logger.info(f"trade_setups: added column '{col}'")

            try:
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_setups_unresolved
                        ON trade_setups (created_at)
                        WHERE resolved_at IS NULL
                """)
            except Exception:
                pass

            conn.commit()
        finally:
            conn.close()

    # ── Write ─────────────────────────────────────────────────────────────────

    async def track_setup(
        self, user_id: int, symbol: str, timeframe: str, setup_data: dict
    ) -> int | None:
        """
        Persist a new setup signal. Returns the row id, or None on failure.
        """
        try:
            conn = get_connection()
            cur  = conn.cursor()
            cur.execute(
                """
                INSERT INTO trade_setups (
                    user_id, symbol, timeframe, score, direction,
                    entry_price, stop_loss, take_profit_1, take_profit_2,
                    risk_reward, htf_trend, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    symbol,
                    timeframe,
                    setup_data.get("score", 0),
                    setup_data.get("direction", "NEUTRAL"),
                    setup_data.get("current_price", 0),
                    setup_data.get("stop_loss", 0),
                    setup_data.get("take_profit_1", 0),
                    setup_data.get("take_profit_2", 0),
                    setup_data.get("risk_reward", 0),
                    setup_data.get("htf_trend", ""),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            row_id = cur.lastrowid
            conn.close()
            logger.info(
                f"Tracked setup #{row_id}: {symbol}/{timeframe} "
                f"score={setup_data.get('score')} dir={setup_data.get('direction')}"
            )
            return row_id
        except Exception as e:
            logger.error(f"track_setup error: {e}")
            return None

    # ── Outcome resolution ────────────────────────────────────────────────────

    async def resolve_pending_outcomes(self) -> int:
        """
        For every unresolved setup whose check windows have elapsed,
        fetch real price from the exchange and mark win/loss.
        Returns the number of setups resolved in this run.
        """
        resolved = 0
        conn     = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, symbol, timeframe, direction,
                       entry_price, stop_loss, take_profit_1,
                       created_at,
                       price_4h, price_24h, price_72h,
                       outcome_4h, outcome_24h, outcome_72h
                FROM trade_setups
                WHERE resolved_at IS NULL
                ORDER BY created_at ASC
                LIMIT 100
                """
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        for row in rows:
            try:
                resolved += await self._resolve_one(row)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"resolve_one error for setup #{row[0]}: {e}")

        if resolved:
            logger.info(f"resolve_pending_outcomes: resolved {resolved} setup(s)")
        return resolved

    async def _resolve_one(self, row: tuple) -> int:
        """Check and update a single pending setup. Returns 1 if fully resolved."""
        (
            setup_id, symbol, timeframe, direction,
            entry_price, stop_loss, tp1,
            created_at_str,
            price_4h, price_24h, price_72h,
            outcome_4h, outcome_24h, outcome_72h,
        ) = row

        created_at = datetime.fromisoformat(created_at_str)
        now        = datetime.utcnow()

        from handlers.setup import OUTCOME_WINDOWS
        windows  = OUTCOME_WINDOWS.get(timeframe, {"4h": 4, "24h": 24, "72h": 72})
        w4h_hrs  = windows["4h"]
        w24h_hrs = windows["24h"]
        w72h_hrs = windows["72h"]

        updates: dict = {}

        if outcome_4h is None and now >= created_at + timedelta(hours=w4h_hrs):
            price = await self._fetch_price_at(symbol, timeframe, created_at, w4h_hrs)
            if price:
                updates["price_4h"]   = price
                updates["outcome_4h"] = self._classify(
                    direction, entry_price, stop_loss, tp1, price
                )

        if outcome_24h is None and now >= created_at + timedelta(hours=w24h_hrs):
            price = await self._fetch_price_at(symbol, timeframe, created_at, w24h_hrs)
            if price:
                updates["price_24h"]   = price
                updates["outcome_24h"] = self._classify(
                    direction, entry_price, stop_loss, tp1, price
                )

        if outcome_72h is None and now >= created_at + timedelta(hours=w72h_hrs):
            price = await self._fetch_price_at(symbol, timeframe, created_at, w72h_hrs)
            if price:
                pct     = ((price - entry_price) / entry_price) * 100
                if direction == "BEARISH":
                    pct = -pct
                outcome                = self._classify(
                    direction, entry_price, stop_loss, tp1, price
                )
                updates["price_72h"]   = price
                updates["outcome_72h"] = outcome
                updates["outcome"]     = outcome
                updates["profit_pct"]  = round(pct, 2)
                updates["resolved_at"] = now.isoformat()

        if not updates:
            return 0

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values     = list(updates.values()) + [setup_id]
        conn       = get_connection()
        try:
            conn.execute(
                f"UPDATE trade_setups SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
        finally:
            conn.close()

        return 1 if "resolved_at" in updates else 0

    @staticmethod
    def _classify(
        direction: str,
        entry: float,
        stop_loss: float,
        tp1: float,
        current: float,
    ) -> str:
        if direction == "BULLISH":
            if current >= tp1:       return "win"
            if current <= stop_loss: return "loss"
        elif direction == "BEARISH":
            if current <= tp1:       return "win"
            if current >= stop_loss: return "loss"
        return "open"

    @staticmethod
    async def _fetch_price_at(
        symbol: str, timeframe: str, created_at: datetime, hours_later: float
    ) -> float | None:
        try:
            candles = await fetch_candles(symbol, timeframe, limit=200)
            if not candles:
                return None

            target_ms = int(
                (created_at + timedelta(hours=hours_later)).timestamp() * 1000
            )
            closest = min(candles, key=lambda c: abs(c["datetime"] - target_ms))

            _CANDLE_MS = {
                "5m":  300_000,   "15m": 900_000,   "30m": 1_800_000,
                "1h":  3_600_000, "2h":  7_200_000,  "4h":  14_400_000,
                "8h":  28_800_000,"1d":  86_400_000,
            }
            tolerance = _CANDLE_MS.get(timeframe, 3_600_000) * 3
            if abs(closest["datetime"] - target_ms) > tolerance:
                return None

            return closest["close"]

        except Exception as e:
            logger.warning(f"_fetch_price_at error for {symbol}: {e}")
            return None

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_similar_setups(
        self, symbol: str, timeframe: str, score: int
    ) -> dict | None:
        """
        Return real historical performance for setups similar to the current one.
        Requires at least 10 resolved setups to return data.
        """
        try:
            conn = get_connection()
            cur  = conn.cursor()
            cur.execute(
                """
                SELECT outcome, profit_pct, risk_reward,
                       outcome_4h, outcome_24h, outcome_72h
                FROM trade_setups
                WHERE symbol    = ?
                AND   timeframe = ?
                AND   score     BETWEEN ? AND ?
                AND   outcome   IS NOT NULL
                AND   created_at > datetime('now', '-90 days')
                ORDER BY created_at DESC
                LIMIT 200
                """,
                (symbol, timeframe, score - 7, score + 7),
            )
            rows = cur.fetchall()
            conn.close()

            if not rows or len(rows) < 10:
                return None

            total  = len(rows)
            wins   = [r for r in rows if r[0] == "win"]
            losses = [r for r in rows if r[0] == "loss"]
            w_n    = len(wins)
            l_n    = len(losses)

            win_rate   = (w_n / total) * 100
            avg_win    = (sum(r[1] for r in wins)   / w_n)  if w_n else 0.0
            avg_loss   = (sum(r[1] for r in losses) / l_n)  if l_n else 0.0
            expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)
            avg_rr     = sum(r[2] for r in rows if r[2]) / total

            def _wr(col_idx: int) -> float | None:
                resolved = [r for r in rows if r[col_idx] in ("win", "loss")]
                if len(resolved) < 5:
                    return None
                w = sum(1 for r in resolved if r[col_idx] == "win")
                return round(w / len(resolved) * 100, 1)

            return {
                "total_setups":    total,
                "win_rate":        round(win_rate, 1),
                "wins":            w_n,
                "losses":          l_n,
                "avg_win":         round(avg_win, 2),
                "avg_loss":        round(avg_loss, 2),
                "expectancy":      round(expectancy, 2),
                "avg_risk_reward": round(avg_rr, 2),
                "win_rate_4h":     _wr(3),
                "win_rate_24h":    _wr(4),
                "win_rate_72h":    _wr(5),
            }

        except Exception as e:
            logger.error(f"get_similar_setups error: {e}")
            return None

    # ── Admin / stats ─────────────────────────────────────────────────────────

    async def get_global_stats(self) -> dict:
        """Overall stats across all symbols/timeframes. Useful for a /perf command."""
        try:
            conn = get_connection()
            cur  = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(*)                                         AS total,
                    SUM(CASE WHEN outcome='win'  THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
                    AVG(CASE WHEN outcome='win'  THEN profit_pct END) AS avg_win,
                    AVG(CASE WHEN outcome='loss' THEN profit_pct END) AS avg_loss,
                    COUNT(DISTINCT symbol)                           AS symbols
                FROM trade_setups
                WHERE outcome IS NOT NULL
                """
            )
            r = cur.fetchone()
            conn.close()
            if not r or not r[0]:
                return {}
            total = r[0]; wins = r[1] or 0; losses = r[2] or 0
            return {
                "total":    total,
                "wins":     wins,
                "losses":   losses,
                "win_rate": round(wins / total * 100, 1) if total else 0,
                "avg_win":  round(r[3] or 0, 2),
                "avg_loss": round(r[4] or 0, 2),
                "symbols":  r[5],
                "pending":  total - wins - losses,
            }
        except Exception as e:
            logger.error(f"get_global_stats error: {e}")
            return {}
