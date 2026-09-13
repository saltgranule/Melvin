import asyncio
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "uptime.db"

MAX_HISTORY_POINTS = 14
CHART_WIDTH = 200
CHART_HEIGHT = 60
CHART_PADDING = 4


async def init_db() -> None:
    await asyncio.to_thread(DATA_DIR.mkdir, parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS shard_latency (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shard_id INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                checked_at TEXT NOT NULL
            )
            """,
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_shard_latency_shard_checked "
            "ON shard_latency (shard_id, checked_at)",
        )
        await db.commit()


async def record_latency(shard_id: int, latency_ms: float) -> None:
    await init_db()
    checked_at = datetime.now(UTC).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO shard_latency (shard_id, latency_ms, checked_at)
            VALUES (?, ?, ?)
            """,
            (shard_id, latency_ms, checked_at),
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


def _format_relative(checked_at: str) -> str:
    checked = datetime.fromisoformat(checked_at)
    seconds = int((datetime.now(UTC) - checked).total_seconds())

    if seconds < 10:
        return "just now."
    if seconds < 60:
        return f"{seconds}s ago."
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago."
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago."
    return f"{hours // 24}d ago."


def _build_area_points(history: list[float]) -> str:
    n = len(history)
    if n == 0:
        return ""

    if n == 1:
        y = CHART_HEIGHT / 2
        return (
            f"0,{CHART_HEIGHT} 0,{y:.2f} "
            f"{CHART_WIDTH},{y:.2f} {CHART_WIDTH},{CHART_HEIGHT}"
        )

    lo = min(history)
    hi = max(history)
    span = (hi - lo) or 1.0
    usable_height = CHART_HEIGHT - (CHART_PADDING * 2)
    step = CHART_WIDTH / (n - 1)

    top_edge = []
    for i, value in enumerate(history):
        x = i * step
        y = CHART_HEIGHT - CHART_PADDING - ((value - lo) / span) * usable_height
        top_edge.append(f"{x:.2f},{y:.2f}")

    return f"0,{CHART_HEIGHT} " + " ".join(top_edge) + f" {CHART_WIDTH},{CHART_HEIGHT}"


async def get_shard_status() -> list[dict]:
    await init_db()

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
                SELECT latency_ms, checked_at FROM shard_latency
                WHERE shard_id = ?
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (shard_id, MAX_HISTORY_POINTS),
            )
            rows = list(reversed(await cursor.fetchall()))
            if not rows:
                continue

            history = [row["latency_ms"] for row in rows]
            latest = rows[-1]

            shards.append(
                {
                    "shard_id": shard_id,
                    "latency_ms": round(latest["latency_ms"]),
                    "last_checked": _format_relative(latest["checked_at"]),
                    "chart_points": _build_area_points(history),
                    "chart_width": CHART_WIDTH,
                    "chart_height": CHART_HEIGHT,
                },
            )

    return shards
