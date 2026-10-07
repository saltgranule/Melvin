# per-server activity totals for the dashboard's server stats. the serverstats cog writes
# them and the website reads them. only totals per server and hour are kept, never who
# sent what or what was said

import asyncio
import math
import time
from pathlib import Path

import aiosqlite

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "server_stats.db"

HOUR = 3600
DAY = 24 * HOUR
# a day longer than the longest range, so the oldest point is always complete
KEEP_SECONDS = 31 * DAY

# range key -> (label, most points shown, how far back it goes)
RANGES = {
    "24h": ("24 hours", 24, DAY),
    "7d": ("7 days", 7, 7 * DAY),
    "30d": ("30 days", 30, 30 * DAY),
}
DEFAULT_RANGE = "7d"

# point sizes to pick from, finest first. a range uses the finest one that fits its
# data into its most points, so a server with little data still gets a detailed chart
POINT_SIZES = (HOUR, 6 * HOUR, DAY)


async def init_db() -> None:
    await asyncio.to_thread(DATA_DIR.mkdir, parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # the bot writes while the website reads, WAL keeps them from blocking each other
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_stats (
                guild_id INTEGER NOT NULL,
                hour INTEGER NOT NULL,
                messages INTEGER NOT NULL DEFAULT 0,
                voice_minutes INTEGER NOT NULL DEFAULT 0,
                members INTEGER,
                PRIMARY KEY (guild_id, hour)
            )
            """,
        )
        await db.commit()


def hour_start(timestamp: float | None = None) -> int:
    now = time.time() if timestamp is None else timestamp
    return int(now // HOUR * HOUR)


async def record(rows: list[tuple[int, int, int, int, int | None]]) -> None:
    # rows are (guild id, hour, messages, voice minutes, members), counts are added to
    # whatever the hour already has and the member count replaces it
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT INTO guild_stats (guild_id, hour, messages, voice_minutes, members)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, hour) DO UPDATE SET
                messages = messages + excluded.messages,
                voice_minutes = voice_minutes + excluded.voice_minutes,
                members = COALESCE(excluded.members, members)
            """,
            rows,
        )
        await db.commit()


async def replace(guild_id: int, rows: list[tuple[int, int, int, int | None]]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM guild_stats WHERE guild_id = ?", (guild_id,))
        await db.executemany(
            """
            INSERT INTO guild_stats (guild_id, hour, messages, voice_minutes, members)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(guild_id, *row) for row in rows],
        )
        await db.commit()


async def prune() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM guild_stats WHERE hour < ?",
            (hour_start() - KEEP_SECONDS,),
        )
        await db.commit()


def _ago(seconds: int) -> str:
    # rounded, since the oldest point starts partway through its hour or day
    if seconds >= 2 * DAY:
        return f"{round(seconds / DAY)} days ago"
    if seconds >= 2 * HOUR:
        return f"{round(seconds / HOUR)} hours ago"
    return "1 hour ago"


async def get_series(guild_id: int, range_key: str) -> dict:
    # groups the hourly rows into points, oldest first, the last point being the
    # current, still filling up period. the chart starts where the server's data does,
    # if that's later than the start of the range
    label, max_points, length = RANGES[range_key]
    now_end = hour_start() + HOUR

    async with (
        aiosqlite.connect(DB_PATH) as db,
        db.execute(
            "SELECT MIN(hour) FROM guild_stats WHERE guild_id = ?",
            (guild_id,),
        ) as cursor,
    ):
        first_hour = (await cursor.fetchone())[0]

    data_start = now_end - length
    if first_hour is not None:
        data_start = max(data_start, first_hour)
    span = now_end - data_start

    size = next(
        (size for size in POINT_SIZES if math.ceil(span / size) <= max_points),
        POINT_SIZES[-1],
    )
    # points line up with whole hours, quarter days, or days in utc
    end = math.ceil(now_end / size) * size
    count = min(max_points, (end - data_start // size * size) // size)
    starts = [end - size * (count - i) for i in range(count)]
    first = starts[0]

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT hour, messages, voice_minutes, members FROM guild_stats
            WHERE guild_id = ? AND hour >= ?
            ORDER BY hour
            """,
            (guild_id, first),
        ) as cursor:
            rows = await cursor.fetchall()
        async with db.execute(
            """
            SELECT members FROM guild_stats
            WHERE guild_id = ? AND hour < ? AND members IS NOT NULL
            ORDER BY hour DESC LIMIT 1
            """,
            (guild_id, first),
        ) as cursor:
            before = await cursor.fetchone()

    messages = [0] * count
    voice = [0] * count
    members: list[int | None] = [None] * count
    for hour, hour_messages, hour_voice, hour_members in rows:
        index = (hour - first) // size
        messages[index] += hour_messages
        voice[index] += hour_voice
        if hour_members is not None:
            members[index] = hour_members

    # carry the member count over periods with no reading, like while the bot was offline
    carried = before[0] if before else None
    for index, value in enumerate(members):
        if value is None:
            members[index] = carried
        else:
            carried = value

    known = [value for value in members if value is not None]
    return {
        "label": label,
        "starts": starts,
        "size": size,
        "start_label": _ago(int(time.time()) - first),
        "messages": messages,
        "voice": voice,
        "members": members,
        "has_data": bool(rows),
        "total_messages": sum(messages),
        "total_voice": sum(voice),
        "member_count": known[-1] if known else None,
        "member_change": known[-1] - known[0] if known else 0,
    }
