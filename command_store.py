"""Saving, loading, and changing custom commands in the database.

The cog and the dashboard both go through here, so the rules for names,
duplicates, and missing commands live in one place.
"""

import re
import time
from dataclasses import dataclass

import aiosqlite

from command_engine import migrate_brackets
from globals import DATA_DIR

DB_PATH = DATA_DIR / "tags.db"
COMMAND_NAME = re.compile(r"[a-z0-9_-]{1,32}")
CACHE_SECONDS = 5
COMMAND_LIMIT = 250

ADDED_COLUMNS = (
    ("args", "TEXT NOT NULL DEFAULT ''"),
    ("permission", "TEXT NOT NULL DEFAULT 'none'"),
)
RETIRED_COLUMNS = ("actions", "cooldown")
EDITABLE = ("content", "args", "permission")

_db_ready = False
_cache: dict[tuple[int, str], tuple[float, "Command | None"]] = {}


class CommandMissing(LookupError):
    pass


class CommandExists(ValueError):
    pass


class CommandLimit(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    name: str
    content: str
    args: str
    permission: str
    author_id: int
    created_at: float
    updated_at: float


def clean_name(name: str) -> str | None:
    name = name.strip().lower()
    return name if COMMAND_NAME.fullmatch(name) else None


def _forget(guild_id: int, name: str | None = None) -> None:
    for key in [key for key in _cache if key[0] == guild_id]:
        if name is None or key[1] == name:
            _cache.pop(key, None)


def old_actions_to_statements(actions: str) -> list[str]:
    statements = []
    for line in actions.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].lower() in ("addrole", "removerole"):
            statements.append(f"${parts[0].lower()}{{{parts[1]}|{parts[2]}}}")
    return statements


def with_statements(content: str, statements: list[str]) -> str:
    if not statements:
        return content
    block = "\n".join(statements)
    lines = content.splitlines()
    if lines and lines[0].strip().lower() in ("{embed}", "{container}"):
        return "\n".join([lines[0], block, *lines[1:]])
    return f"{block}\n{content}"


async def _columns(conn: aiosqlite.Connection) -> set[str]:
    cursor = await conn.execute("PRAGMA table_info(tags)")
    return {row[1] for row in await cursor.fetchall()}


async def _convert_legacy(conn: aiosqlite.Connection, existing: set[str]) -> None:
    if "actions" in existing:
        query = (
            "SELECT guild_id, name, content, actions FROM tags "
            "WHERE content LIKE '%[%' OR actions != ''"
        )
    else:
        query = "SELECT guild_id, name, content, '' FROM tags WHERE content LIKE '%[%'"
    cursor = await conn.execute(query)
    for guild_id, name, content, actions in await cursor.fetchall():
        migrated = migrate_brackets(content)
        if actions:
            migrated = with_statements(migrated, old_actions_to_statements(actions))
        if migrated != content:
            await conn.execute(
                "UPDATE tags SET content = ? WHERE guild_id = ? AND name = ?",
                (migrated, guild_id, name),
            )


async def init_db() -> None:
    global _db_ready
    if _db_ready:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                author_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                args TEXT NOT NULL DEFAULT '',
                permission TEXT NOT NULL DEFAULT 'none',
                PRIMARY KEY (guild_id, name)
            )
            """,
        )
        existing = await _columns(conn)
        for column, definition in ADDED_COLUMNS:
            if column not in existing:
                await conn.execute(f"ALTER TABLE tags ADD COLUMN {column} {definition}")

        await _convert_legacy(conn, existing)
        for column in RETIRED_COLUMNS:
            if column in existing:
                await conn.execute(f"ALTER TABLE tags DROP COLUMN {column}")
        await conn.commit()
    _db_ready = True


_SELECT = """
    SELECT name, content, args, permission, author_id, created_at, updated_at
    FROM tags
"""


async def fetch(guild_id: int, name: str) -> Command | None:
    key = (guild_id, name)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    await init_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(_SELECT + " WHERE guild_id = ? AND name = ?", (guild_id, name)) as cursor:
            row = await cursor.fetchone()
    command = Command(*row) if row else None
    _cache[key] = (time.monotonic(), command)
    return command


async def lookup(guild_id: int, name: str) -> str | None:
    command = await fetch(guild_id, name)
    return command.content if command else None


async def count_commands(guild_id: int) -> int:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM tags WHERE guild_id = ?", (guild_id,)) as cursor:
            (total,) = await cursor.fetchone()
    return total


async def list_commands(guild_id: int, query: str = "") -> list[Command]:
    await init_db()
    needle = query.strip().lower()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            _SELECT
            + """
            WHERE guild_id = ? AND (? = '' OR instr(name, ?) > 0)
            ORDER BY (instr(name, ?) = 1) DESC, name
            """,
            (guild_id, needle, needle, needle),
        ) as cursor:
            return [Command(*row) for row in await cursor.fetchall()]


async def autocomplete_names(guild_id: int, current: str, limit: int) -> list[str]:
    await init_db()
    needle = current.strip().lower()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """
            SELECT name FROM tags
            WHERE guild_id = ? AND (? = '' OR instr(name, ?) > 0)
            ORDER BY (instr(name, ?) = 1) DESC, name
            LIMIT ?
            """,
            (guild_id, needle, needle, needle, limit),
        ) as cursor:
            return [name for (name,) in await cursor.fetchall()]


async def create(
    guild_id: int,
    name: str,
    content: str,
    author_id: int,
    *,
    args: str = "",
    permission: str = "none",
) -> None:
    await init_db()
    now = time.time()
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute("SELECT COUNT(*) FROM tags WHERE guild_id = ?", (guild_id,)) as cursor:
                (total,) = await cursor.fetchone()
            if total >= COMMAND_LIMIT:
                raise CommandLimit(COMMAND_LIMIT)
            await conn.execute(
                """
                INSERT INTO tags (guild_id, name, content, author_id, created_at, updated_at, args, permission)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, name, content, author_id, now, now, args, permission),
            )
            await conn.commit()
    except aiosqlite.IntegrityError as error:
        raise CommandExists(name) from error
    _forget(guild_id, name)


async def update(guild_id: int, name: str, changes: dict[str, str]) -> None:
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        msg = f"can't change {', '.join(sorted(unknown))}"
        raise ValueError(msg)
    await init_db()
    assignments = ", ".join(f"{column} = ?" for column in changes)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            f"UPDATE tags SET {assignments}, updated_at = ? WHERE guild_id = ? AND name = ?",
            (*changes.values(), time.time(), guild_id, name),
        )
        changed = cursor.rowcount
        await conn.commit()
    _forget(guild_id, name)
    if not changed:
        raise CommandMissing(name)


async def rename(guild_id: int, old: str, new: str) -> None:
    await init_db()
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "UPDATE tags SET name = ?, updated_at = ? WHERE guild_id = ? AND name = ?",
                (new, time.time(), guild_id, old),
            )
            changed = cursor.rowcount
            await conn.commit()
    except aiosqlite.IntegrityError as error:
        raise CommandExists(new) from error
    _forget(guild_id)
    if not changed:
        raise CommandMissing(old)


async def copy(guild_id: int, source: str, new: str, author_id: int) -> None:
    command = await fetch(guild_id, source)
    if command is None:
        raise CommandMissing(source)
    await create(
        guild_id,
        new,
        command.content,
        author_id,
        args=command.args,
        permission=command.permission,
    )


async def delete(guild_id: int, name: str) -> bool:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "DELETE FROM tags WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        )
        deleted = cursor.rowcount
        await conn.commit()
    _forget(guild_id, name)
    return bool(deleted)


async def delete_guild(guild_id: int) -> None:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM tags WHERE guild_id = ?", (guild_id,))
        await conn.commit()
    _forget(guild_id)
