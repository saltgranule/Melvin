import asyncio
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from module_settings import DATA_DIR, DB_PATH

if TYPE_CHECKING:
    from collections.abc import Callable

CACHE_SECONDS = 10

IMAGE_DIR = DATA_DIR / "config_images"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024

COLOR_PATTERN = re.compile(r"^#?([0-9a-fA-F]{6})(?:\s*-\s*#?([0-9a-fA-F]{6}))?$")
SNOWFLAKE_PATTERN = re.compile(r"^\d{15,21}$")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    description: str
    # channel, role, choice, text, url, color, or image
    kind: str
    default: str | None = None
    # (value, label) pairs for choice settings
    choices: tuple[tuple[str, str], ...] = ()
    max_length: int = 100
    placeholder: str = ""
    # a discord permission needed on top of Manage Server to change this setting
    permission: str | None = None


FONTS = (
    ("cherry_bomb", "Sakura"),
    ("chicle", "Jellybean"),
    ("museo_moderno", "Modern"),
    ("neo_castel", "Medieval"),
    ("pixelify", "8Bit"),
    ("sinistre", "Vampyre"),
    ("default", "GG Sans"),
    ("zilla_slab", "Tempo"),
)
EFFECTS = (
    ("solid", "Solid"),
    ("gradient", "Gradient"),
    ("neon", "Neon"),
    ("toon", "Toon"),
    ("pop", "Pop"),
)

CONFIG: dict[str, tuple[Setting, ...]] = {
    "audit": (
        Setting(
            "log_channel",
            "Log channel",
            "The channel audit logs are posted in. Nothing is logged until one is set.",
            "channel",
        ),
    ),
    "welcome": (
        Setting(
            "channel",
            "Welcome channel",
            "The channel welcome messages are sent in. Nothing is sent until one is set.",
            "channel",
        ),
        Setting(
            "message",
            "Message",
            "Use {member} to mention the new member and {member_count} for the member count.",
            "text",
            default="Welcome, {member}!",
            max_length=2000,
            placeholder="Welcome, {member}! We're at {member_count} members now.",
        ),
        Setting("image", "Image", "Shown under the message.", "image"),
        Setting(
            "button1_label",
            "First button label",
            "The text on the first link button.",
            "text",
            default="Link 1",
            max_length=80,
        ),
        Setting(
            "button1_url",
            "First button link",
            "Where the first button goes. Leave empty for no button.",
            "url",
            placeholder="https://",
        ),
        Setting(
            "button2_label",
            "Second button label",
            "The text on the second link button.",
            "text",
            default="Link 2",
            max_length=80,
        ),
        Setting(
            "button2_url",
            "Second button link",
            "Where the second button goes. Leave empty for no button.",
            "url",
            placeholder="https://",
        ),
    ),
    "thanks": (
        Setting(
            "announce",
            "Thank messages",
            "Whether Melvin posts a message when someone is thanked. Thanks are counted either way.",
            "choice",
            default="on",
            choices=(("on", "On"), ("off", "Off")),
        ),
        Setting(
            "cooldown",
            "Cooldown",
            "How long each member waits between giving thanks.",
            "choice",
            default="60",
            choices=(
                ("30", "30 seconds"),
                ("60", "1 minute"),
                ("300", "5 minutes"),
                ("600", "10 minutes"),
            ),
        ),
    ),
    "mod": (
        Setting(
            "auto_role",
            "Auto-role",
            "Given to members when they join. Leave empty for none.",
            "role",
            permission="manage_roles",
        ),
    ),
    "style": (
        Setting(
            "font",
            "Font",
            "The font of Melvin's name in this server.",
            "choice",
            default="cherry_bomb",
            choices=FONTS,
        ),
        Setting(
            "effect",
            "Effect",
            "The effect on Melvin's name in this server.",
            "choice",
            default="gradient",
            choices=EFFECTS,
        ),
        Setting(
            "colors",
            "Colors",
            "One hex color, or two joined by a dash for the gradient effect, like F4A261-FFFFFF.",
            "color",
            default="FFFFFF",
            placeholder="F4A261-FFFFFF",
        ),
    ),
}


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


def clean_value(setting: Setting, raw: str | None) -> str | None:
    # check a value typed or picked by a user, returning what to store, None clears it
    value = (raw or "").strip()
    if not value:
        return None

    if setting.kind in {"channel", "role"}:
        if not SNOWFLAKE_PATTERN.match(value):
            msg = f"That isn't a valid {setting.kind}."
            raise ConfigError(msg)
    elif setting.kind == "choice":
        if value not in dict(setting.choices):
            msg = f"That isn't one of the options for {setting.label}."
            raise ConfigError(msg)
    elif setting.kind == "text":
        if len(value) > setting.max_length:
            msg = f"{setting.label} can be at most {setting.max_length} characters."
            raise ConfigError(msg)
    elif setting.kind == "url":
        if not value.startswith(("http://", "https://")) or " " in value:
            msg = "Links must start with http:// or https://."
            raise ConfigError(msg)
        if len(value) > 512:
            msg = "Links can be at most 512 characters."
            raise ConfigError(msg)
    elif setting.kind == "color":
        match = COLOR_PATTERN.match(value)
        if not match:
            msg = "Colors must be a hex code like F4A261, or two joined by a dash."
            raise ConfigError(msg)
        value = "-".join(part.upper() for part in match.groups() if part)
    else:
        msg = f"{setting.kind} settings can't be set from text"
        raise ValueError(msg)

    return value


# storage, one row per changed setting, a NULL value means it was cleared
# (guild id, module) -> (when it was loaded, the stored values)
_cache: dict[tuple[int, str], tuple[float, dict[str, str | None]]] = {}


async def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # lets the bot and the website read and write at the same time without locking each other out
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


async def _stored(guild_id: int, module: str) -> dict[str, str | None]:
    cached = _cache.get((guild_id, module))
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    async with (
        aiosqlite.connect(DB_PATH) as db,
        db.execute(
            "SELECT key, value FROM guild_settings WHERE guild_id = ? AND module = ?",
            (guild_id, module),
        ) as cursor,
    ):
        stored = {key: value async for key, value in cursor}

    _cache[guild_id, module] = (time.monotonic(), stored)
    return stored


async def get_all(guild_id: int, module: str) -> dict[str, str | None]:
    # every setting for a module, with defaults filled in for anything not set
    stored = await _stored(guild_id, module)
    return {
        setting.key: stored.get(setting.key) or setting.default
        for setting in CONFIG[module]
    }


async def get(guild_id: int, module: str, key: str) -> str | None:
    return (await get_all(guild_id, module))[key]


async def set_values(
    guild_id: int,
    module: str,
    values: dict[str, str | None],
) -> None:
    for key in values:
        get_setting(module, key)

    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT INTO guild_settings (guild_id, module, key, value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, module, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            [(guild_id, module, key, value, now) for key, value in values.items()],
        )
        await db.commit()

    _cache.pop((guild_id, module), None)


async def changed_since(module: str, since: float) -> set[int]:
    # guilds with a setting in this module changed after a time.time() timestamp
    async with (
        aiosqlite.connect(DB_PATH) as db,
        db.execute(
            "SELECT DISTINCT guild_id FROM guild_settings WHERE module = ? AND updated_at > ?",
            (module, since),
        ) as cursor,
    ):
        return {row[0] async for row in cursor}


async def clear_module(guild_id: int, module: str) -> None:
    for setting in CONFIG[module]:
        if setting.kind == "image":
            await remove_image(guild_id, module, setting.key)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM guild_settings WHERE guild_id = ? AND module = ?",
            (guild_id, module),
        )
        await db.commit()

    _cache.pop((guild_id, module), None)


# images are stored as files, and the setting holds the path
def _delete_file(path: str | None) -> None:
    if not path:
        return
    file = Path(path).resolve()
    # never delete anything outside the data folder, whatever the setting says
    if file.is_file() and DATA_DIR.resolve() in file.parents:
        file.unlink()


async def replace_image(
    guild_id: int,
    module: str,
    key: str,
    filename: str,
    data: bytes,
) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in IMAGE_TYPES:
        msg = "Images must be PNG, JPG, GIF, or WebP."
        raise ConfigError(msg)
    if len(data) > MAX_IMAGE_BYTES:
        msg = "Images must be 8 MB or smaller."
        raise ConfigError(msg)

    old_path = await get(guild_id, module, key)
    # a new name each time, so discord doesn't show an older cached copy
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
    # move a cog's settings from its old table into guild_settings, once. the old table
    # is renamed to <table>_migrated rather than dropped, so nothing is lost
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ) as cursor:
            if await cursor.fetchone() is None:
                return

        # table names come from the cogs, never from users
        async with db.execute(f"SELECT * FROM {table}") as cursor:  # ruff: ignore[hardcoded-sql-expression]
            rows = await cursor.fetchall()

        await init_db()
        for row in rows:
            guild_id, values = rows_to_values(row)
            cleaned = {key: value for key, value in values.items() if value}
            if cleaned:
                await set_values(guild_id, module, cleaned)

        await db.execute(f"ALTER TABLE {table} RENAME TO {table}_migrated")
        await db.commit()
