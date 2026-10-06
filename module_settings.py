import time
from pathlib import Path

import aiosqlite

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "modules.db"

# how long the bot trusts its cached settings before re-reading them, so changes
# made outside the bot (like the dashboard) still apply within a few seconds
CACHE_SECONDS = 10

# module key -> (label, description), keys match each cog's command group name
MODULES = {
    "mod": ("Moderation", "Warnings, kicks, bans, mutes, cases, and the auto-role."),
    "audit": ("Audit Logs", "Logs member, message, voice, channel, and role changes."),
    "welcome": ("Welcome", "Welcome messages for new members."),
    "thanks": ("Thanks", "Counts thanks between members."),
    "ai": ("AI", "Ask a free AI model questions."),
    "tool": ("Tools", "Encoding, decoding, speak, and 8ball."),
    "timezone": ("Timezones", "Set and compare member timezones."),
    "info": ("Info", "View avatars and banners."),
    "style": ("Style", "Melvin's display name style."),
}

_cache: dict = {"disabled": {}, "loaded_at": 0.0}


async def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_modules (
                guild_id INTEGER NOT NULL,
                module TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                PRIMARY KEY (guild_id, module)
            )
            """,
        )
        await db.commit()


async def _refresh() -> None:
    disabled: dict[int, set[str]] = {}
    async with (
        aiosqlite.connect(DB_PATH) as db,
        db.execute(
            "SELECT guild_id, module FROM guild_modules WHERE enabled = 0",
        ) as cursor,
    ):
        async for guild_id, module in cursor:
            disabled.setdefault(guild_id, set()).add(module)

    _cache["disabled"] = disabled
    _cache["loaded_at"] = time.monotonic()


async def disabled_modules(guild_id: int) -> set[str]:
    if time.monotonic() - _cache["loaded_at"] > CACHE_SECONDS:
        await _refresh()
    return _cache["disabled"].get(guild_id, set())


async def is_enabled(guild_id: int | None, module: str) -> bool:
    # modules only apply to guilds, and are on unless a guild turns them off
    if guild_id is None or module not in MODULES:
        return True
    return module not in await disabled_modules(guild_id)


async def set_enabled(guild_id: int, module: str, *, enabled: bool) -> None:
    if module not in MODULES:
        msg = f"unknown module {module!r}"
        raise ValueError(msg)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO guild_modules (guild_id, module, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, module) DO UPDATE SET enabled = excluded.enabled
            """,
            (guild_id, module, int(enabled)),
        )
        await db.commit()

    await _refresh()
