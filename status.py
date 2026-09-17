import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "uptime.db"
START_TIME_FILE = DATA_DIR / "start_time.txt"

MAX_HISTORY_POINTS = 14
CHART_WIDTH = 200
CHART_HEIGHT = 60
CHART_PADDING = 4

log = logging.getLogger(__name__)


def set_start_time() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    START_TIME_FILE.write_text(now, encoding="utf-8")


def _get_start_time() -> datetime | None:
    try:
        if START_TIME_FILE.is_file():
            return datetime.fromisoformat(START_TIME_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        log.exception("retrieving the start time failed")
    return None


def _format_uptime(start: datetime) -> str:
    seconds = int((datetime.now(UTC) - start).total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)

    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


async def init_db() -> None:
    await asyncio.to_thread(DATA_DIR.mkdir, parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS shard_latency (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shard_id INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                api_latency_ms REAL,
                checked_at TEXT NOT NULL
            )
            """,
        )
        cursor = await db.execute("PRAGMA table_info(shard_latency)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "api_latency_ms" not in columns:
            await db.execute("ALTER TABLE shard_latency ADD COLUMN api_latency_ms REAL")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_shard_latency_shard_checked "
            "ON shard_latency (shard_id, checked_at)",
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_count INTEGER NOT NULL,
                member_count INTEGER NOT NULL,
                checked_at TEXT NOT NULL
            )
            """,
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_bot_metrics_checked ON bot_metrics (checked_at)",
        )
        await db.commit()


async def record_latency(shard_id: int, latency_ms: float, api_latency_ms: float) -> None:
    await init_db()
    checked_at = datetime.now(UTC).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO shard_latency (shard_id, latency_ms, api_latency_ms, checked_at)
            VALUES (?, ?, ?, ?)
            """,
            (shard_id, latency_ms, api_latency_ms, checked_at),
        )
        await db.execute(
            """
            DELETE FROM shard_latency
            WHERE shard_id = ? AND id NOT IN (
                SELECT id FROM shard_latency
                WHERE shard_id = ?
                ORDER BY checked_at DESC
                LIMIT ?
            )
            """,
            (shard_id, shard_id, MAX_HISTORY_POINTS),
        )
        await db.commit()


async def record_metrics(guild_count: int, member_count: int) -> None:
    await init_db()
    checked_at = datetime.now(UTC).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO bot_metrics (guild_count, member_count, checked_at)
            VALUES (?, ?, ?)
            """,
            (guild_count, member_count, checked_at),
        )
        await db.execute(
            """
            DELETE FROM bot_metrics
            WHERE id NOT IN (
                SELECT id FROM bot_metrics
                ORDER BY checked_at DESC
                LIMIT ?
            )
            """,
            (MAX_HISTORY_POINTS,),
        )
        await db.commit()


def _format_relative(checked_at: str) -> str:
    checked = datetime.fromisoformat(checked_at)
    seconds = int((datetime.now(UTC) - checked).total_seconds())

    if seconds < 10:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _build_area_points(history: list[float], lo: float, hi: float) -> str:
    n = len(history)
    if n == 0:
        return ""

    span = (hi - lo) or 1.0
    usable_height = CHART_HEIGHT - (CHART_PADDING * 2)

    if n == 1:
        y = CHART_HEIGHT - CHART_PADDING - ((history[0] - lo) / span) * usable_height
        return (
            f"0,{CHART_HEIGHT} 0,{y:.2f} "
            f"{CHART_WIDTH},{y:.2f} {CHART_WIDTH},{CHART_HEIGHT}"
        )

    step = CHART_WIDTH / (n - 1)
    top_edge = []
    for i, value in enumerate(history):
        x = i * step
        y = CHART_HEIGHT - CHART_PADDING - ((value - lo) / span) * usable_height
        top_edge.append(f"{x:.2f},{y:.2f}")

    return f"0,{CHART_HEIGHT} " + " ".join(top_edge) + f" {CHART_WIDTH},{CHART_HEIGHT}"


async def get_shard_status() -> list[dict]:
    await init_db()

    start_time = _get_start_time()
    uptime = _format_uptime(start_time) if start_time else "—"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT DISTINCT shard_id FROM shard_latency ORDER BY shard_id ASC",
        )
        shard_ids = [row["shard_id"] for row in await cursor.fetchall()]

        shards = []
        for shard_id in shard_ids:
            cursor = await db.execute(
                """
                SELECT latency_ms, api_latency_ms, checked_at FROM shard_latency
                WHERE shard_id = ?
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (shard_id, MAX_HISTORY_POINTS),
            )
            rows = list(reversed(await cursor.fetchall()))
            if not rows:
                continue

            gateway_history = [row["latency_ms"] for row in rows]
            api_history = [row["api_latency_ms"] or 0.0 for row in rows]
            latest = rows[-1]
            combined = gateway_history + api_history
            lo, hi = min(combined), max(combined)

            shards.append(
                {
                    "shard_id": shard_id,
                    "latency_ms": round(latest["latency_ms"]),
                    "api_latency_ms": round(latest["api_latency_ms"] or 0.0),
                    "last_checked": _format_relative(latest["checked_at"]),
                    "uptime": uptime,
                    "chart_points": _build_area_points(gateway_history, lo, hi),
                    "api_chart_points": _build_area_points(api_history, lo, hi),
                    "chart_width": CHART_WIDTH,
                    "chart_height": CHART_HEIGHT,
                },
            )

    return shards


async def get_metrics_status() -> dict | None:
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT guild_count, member_count, checked_at FROM bot_metrics
            ORDER BY checked_at DESC
            LIMIT ?
            """,
            (MAX_HISTORY_POINTS,),
        )
        rows = list(reversed(await cursor.fetchall()))

    if not rows:
        return None

    guild_history = [row["guild_count"] for row in rows]
    member_history = [row["member_count"] for row in rows]
    latest = rows[-1]

    guild_lo, guild_hi = min(guild_history), max(guild_history)
    member_lo, member_hi = min(member_history), max(member_history)

    return {
        "guild_count": latest["guild_count"],
        "member_count": latest["member_count"],
        "last_checked": _format_relative(latest["checked_at"]),
        "guild_chart_points": _build_area_points(guild_history, guild_lo, guild_hi),
        "member_chart_points": _build_area_points(member_history, member_lo, member_hi),
        "chart_width": CHART_WIDTH,
        "chart_height": CHART_HEIGHT,
    }
