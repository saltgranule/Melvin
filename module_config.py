import asyncio
import re
import secrets
import time
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import aiosqlite

from globals import DATA_DIR
from module_registry import CONFIG, MAX_CHANNELS, Setting
from module_settings import DB_PATH

if TYPE_CHECKING:
    from collections.abc import Callable

CACHE_SECONDS = 10

IMAGE_DIR = DATA_DIR / "config_images"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_URL_LENGTH = 512
MAX_EMOJIS = 10

COLOR_PATTERN = re.compile(r"^#?([0-9a-fA-F]{6})(?:\s*-\s*#?([0-9a-fA-F]{6}))?$")
SNOWFLAKE_PATTERN = re.compile(r"^\d{15,21}$")
CUSTOM_EMOJI_PATTERN = re.compile(r"^<a?:\w{2,32}:\d{15,21}>$")

_UPSERT = """
    INSERT INTO guild_settings (guild_id, module, key, value, updated_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(guild_id, module, key) DO UPDATE SET
        value = excluded.value,
        updated_at = excluded.updated_at
"""

_cache: dict[tuple[int, str], tuple[float, dict[str, str | None]]] = {}
_db_ready = False


class ConfigError(ValueError):
    pass


def is_configurable(module: str) -> bool:
    return module in CONFIG


def get_setting(module: str, key: str) -> Setting:
    for setting in CONFIG[module]:
        if setting.key == key:
            return setting
    msg = f"unknown setting {module}.{key}"
    raise KeyError(msg)


def choice_label(setting: Setting, value: str | None) -> str | None:
    return dict(setting.choices).get(value) if value else None


def _is_unicode_emoji(token: str) -> bool:
    if len(token) > 32:
        return False
    categories = {unicodedata.category(char) for char in token}
    return "So" in categories and categories <= {"So", "Sk", "Mn", "Cf"}


def _fail(msg: str) -> NoReturn:
    raise ConfigError(msg)


def clean_value(setting: Setting, raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None

    match setting.kind:
        case "channels":
            ids = list(
                dict.fromkeys(part for part in re.split(r"[\s,]+", value) if part),
            )
            if not all(SNOWFLAKE_PATTERN.match(part) for part in ids):
                _fail("That isn't a valid list of channels.")
            if len(ids) > MAX_CHANNELS:
                _fail(f"{setting.label} can have at most {MAX_CHANNELS} channels.")
            return ",".join(ids)
        case "channel" | "role":
            if not SNOWFLAKE_PATTERN.match(value):
                _fail(f"That isn't a valid {setting.kind}.")
        case "choice":
            if not any(value == key for key, _ in setting.choices):
                _fail(f"That isn't one of the options for {setting.label}.")
        case "emojis":
            tokens = list(
                dict.fromkeys(part for part in re.split(r"[\s,]+", value) if part),
            )
            if len(tokens) > MAX_EMOJIS:
                _fail(f"{setting.label} can have at most {MAX_EMOJIS} emojis.")
            for token in tokens:
                if CUSTOM_EMOJI_PATTERN.match(token):
                    continue
                if not _is_unicode_emoji(token):
                    _fail(f"{token} isn't an emoji Melvin can use.")
            return ",".join(tokens)
        case "number":
            if not value.isdigit():
                _fail(f"{setting.label} has to be a whole number.")
            number = int(value)
            if not setting.minimum <= number <= setting.maximum:
                _fail(
                    f"{setting.label} has to be between {setting.minimum} and {setting.maximum}.",
                )
            return str(number)
        case "text":
            if len(value) > setting.max_length:
                _fail(
                    f"{setting.label} can be at most {setting.max_length} characters.",
                )
        case "url":
            if not value.startswith(("http://", "https://")) or " " in value:
                _fail("Links must start with http:// or https://.")
            if len(value) > MAX_URL_LENGTH:
                _fail(f"Links can be at most {MAX_URL_LENGTH} characters.")
        case "color":
            color = COLOR_PATTERN.match(value)
            if not color:
                _fail("Colors must be a hex code like F4A261, or two joined by a dash.")
            return "-".join(part.upper() for part in color.groups() if part)
        case _:
            msg = f"{setting.kind} settings can't be set from text"
            raise ValueError(msg)

    return value


async def init_db() -> None:
    global _db_ready
    if _db_ready:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER NOT NULL,
                module TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                updated_at REAL NOT NULL,
                PRIMARY KEY (guild_id, module, key)
            )
            """,
        )
        await db.commit()
    _db_ready = True


async def _stored(guild_id: int, module: str) -> dict[str, str | None]:
    now = time.monotonic()
    cached = _cache.get((guild_id, module))
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]

    await init_db()
    async with (
        aiosqlite.connect(DB_PATH) as db,
        db.execute(
            "SELECT key, value FROM guild_settings WHERE guild_id = ? AND module = ?",
            (guild_id, module),
        ) as cursor,
    ):
        stored = {key: value async for key, value in cursor}

    _cache[guild_id, module] = (now, stored)
    return stored


async def get_all(guild_id: int, module: str) -> dict[str, str | None]:
    stored = await _stored(guild_id, module)
    return {
        setting.key: stored.get(setting.key) or setting.default
        for setting in CONFIG[module]
    }


async def get(guild_id: int, module: str, key: str) -> str | None:
    return (await get_all(guild_id, module))[key]


async def _write(module: str, rows: list[tuple[int, dict[str, str | None]]]) -> None:
    keys = {setting.key for setting in CONFIG[module]}
    for _, values in rows:
        for key in values:
            if key not in keys:
                msg = f"unknown setting {module}.{key}"
                raise KeyError(msg)

    await init_db()
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            _UPSERT,
            [
                (guild_id, module, key, value, now)
                for guild_id, values in rows
                for key, value in values.items()
            ],
        )
        await db.commit()

    for guild_id, _ in rows:
        _cache.pop((guild_id, module), None)


async def set_values(guild_id: int, module: str, values: dict[str, str | None]) -> None:
    await _write(module, [(guild_id, values)])


async def changed_since(module: str, since: float) -> set[int]:
    await init_db()
    async with (
        aiosqlite.connect(DB_PATH) as db,
        db.execute(
            "SELECT DISTINCT guild_id FROM guild_settings WHERE module = ? AND updated_at > ?",
            (module, since),
        ) as cursor,
    ):
        return {row[0] async for row in cursor}


async def clear_module(guild_id: int, module: str) -> None:
    images = [setting.key for setting in CONFIG[module] if setting.kind == "image"]
    old_paths = []
    if images:
        stored = await get_all(guild_id, module)
        old_paths = [stored[key] for key in images]

    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM guild_settings WHERE guild_id = ? AND module = ?",
            (guild_id, module),
        )
        await db.commit()

    _cache.pop((guild_id, module), None)
    for path in old_paths:
        await asyncio.to_thread(_delete_file, path)


def image_file(path: str | None) -> Path | None:
    if not path:
        return None
    file = (DATA_DIR.parent / path).resolve()
    if not file.is_file() or DATA_DIR.resolve() not in file.parents:
        return None
    return file


def _delete_file(path: str | None) -> None:
    file = image_file(path)
    if file is not None:
        file.unlink()


def check_image(filename: str, size: int) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in IMAGE_TYPES:
        _fail("Images must be PNG, JPG, GIF, or WebP.")
    if size > MAX_IMAGE_BYTES:
        _fail("Images must be 8 MB or smaller.")
    return extension


async def replace_image(
    guild_id: int,
    module: str,
    key: str,
    filename: str,
    data: bytes,
) -> str:
    extension = check_image(filename, len(data))
    old_path = await get(guild_id, module, key)
    path = IMAGE_DIR / f"{guild_id}-{module}-{key}-{secrets.token_hex(4)}{extension}"
    await asyncio.to_thread(IMAGE_DIR.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, data)
    await set_values(guild_id, module, {key: str(path)})
    await asyncio.to_thread(_delete_file, old_path)
    return str(path)


async def remove_image(guild_id: int, module: str, key: str) -> None:
    old_path = await get(guild_id, module, key)
    await set_values(guild_id, module, {key: None})
    await asyncio.to_thread(_delete_file, old_path)


async def migrate_legacy(
    db_path: str,
    table: str,
    module: str,
    rows_to_values: Callable[[tuple], tuple[int, dict[str, str | None]]],
) -> None:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ) as cursor:
            if await cursor.fetchone() is None:
                return

        async with db.execute(f"SELECT * FROM {table}") as cursor:  # ruff: ignore[hardcoded-sql-expression]
            rows = await cursor.fetchall()

        migrated = []
        for row in rows:
            guild_id, values = rows_to_values(row)
            cleaned = {key: value for key, value in values.items() if value}
            if cleaned:
                migrated.append((guild_id, cleaned))
        if migrated:
            await _write(module, migrated)

        await db.execute(f"ALTER TABLE {table} RENAME TO {table}_migrated")
        await db.commit()
