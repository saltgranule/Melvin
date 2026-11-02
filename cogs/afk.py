import logging
import time
from dataclasses import dataclass

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_settings
from globals import DATA_DIR
from module_registry import Module
from ui import ErrorUI, InfoUI

log = logging.getLogger(__name__)

KEY = "afk"

MODULE = Module(
    KEY,
    "AFK",
    "Lets members leave an away message that shows when they're mentioned.",
)

REASON_LENGTH = 200
NOTICE_COOLDOWN = 30.0
MAX_NOTICES = 5
NO_PINGS = discord.AllowedMentions.none()


@dataclass(frozen=True)
class AfkStatus:
    reason: str
    since: int


def _clean_reason(reason: str | None) -> str:
    return " ".join((reason or "").split())


def _describe(status: AfkStatus) -> str:
    went = f"Went AFK <t:{status.since}:R>"
    if not status.reason:
        return went
    return f"{went}: {discord.utils.escape_markdown(status.reason)}"


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class AfkCog(
    commands.GroupCog,
    name=KEY,
    description="Leave an away message for this server.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = DATA_DIR / "afk.db"
        # on_message reads this for every message, so it stays out of the database
        self._statuses: dict[int, dict[int, AfkStatus]] = {}
        self._last_notice: dict[tuple[int, int], float] = {}

    async def cog_load(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS afk_statuses (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    since INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """,
            )
            await db.commit()
            async with db.execute(
                "SELECT guild_id, user_id, reason, since FROM afk_statuses",
            ) as cursor:
                async for guild_id, user_id, reason, since in cursor:
                    self._statuses.setdefault(guild_id, {})[user_id] = AfkStatus(
                        reason,
                        since,
                    )

    async def _set_status(
        self,
        guild_id: int,
        user_id: int,
        status: AfkStatus,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO afk_statuses (guild_id, user_id, reason, since)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    reason = excluded.reason,
                    since = excluded.since
                """,
                (guild_id, user_id, status.reason, status.since),
            )
            await db.commit()
        self._statuses.setdefault(guild_id, {})[user_id] = status

    async def _clear_status(self, guild_id: int, user_id: int) -> AfkStatus | None:
        guild_statuses = self._statuses.get(guild_id, {})
        if user_id not in guild_statuses:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM afk_statuses WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await db.commit()
        status = guild_statuses.pop(user_id)
        if not guild_statuses:
            self._statuses.pop(guild_id, None)
        return status

    def _take_notices(
        self,
        channel_id: int,
        members: list[discord.abc.User],
    ) -> list[discord.abc.User]:
        now = time.monotonic()
        self._last_notice = {
            key: last
            for key, last in self._last_notice.items()
            if now - last < NOTICE_COOLDOWN
        }
        due = [m for m in members if (channel_id, m.id) not in self._last_notice]
        for member in due:
            self._last_notice[channel_id, member.id] = now
        return due

    @app_commands.command(name="set", description="Go AFK in this server.")
    @app_commands.describe(reason="What to tell people who mention you.")
    async def afk_set(
        self,
        interaction: discord.Interaction,
        reason: app_commands.Range[str, 1, REASON_LENGTH] | None = None,
    ) -> None:
        status = AfkStatus(_clean_reason(reason), int(time.time()))
        await self._set_status(interaction.guild_id, interaction.user.id, status)
        content = f"{interaction.user.mention} is now AFK"
        if status.reason:
            content += f"\n-# **{discord.utils.escape_markdown(status.reason)}**"
        await interaction.response.send_message(content, allowed_mentions=NO_PINGS)

    @app_commands.command(name="clear", description="Clear a member's AFK status.")
    @app_commands.describe(user="The member to clear.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def afk_clear(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        if await self._clear_status(interaction.guild_id, user.id) is None:
            await interaction.response.send_message(
                view=ErrorUI(f"**{user.mention} isn't AFK.**"),
                allowed_mentions=NO_PINGS,
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"{user.mention} is no longer AFK",
            allowed_mentions=NO_PINGS,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or message.is_system():
            return
        guild_statuses = self._statuses.get(message.guild.id)
        if not guild_statuses:
            return

        returning = message.author.id in guild_statuses
        mentioned = [
            member
            for member in message.mentions
            if member.id in guild_statuses and member.id != message.author.id
        ]
        if not returning and not mentioned:
            return
        if not await module_settings.is_enabled(message.guild.id, KEY):
            return

        lines = [
            f"{member.mention}: {_describe(guild_statuses[member.id])}"
            for member in self._take_notices(message.channel.id, mentioned)
        ]
        hidden = len(lines) - MAX_NOTICES
        lines = lines[:MAX_NOTICES]
        if hidden > 0:
            lines.append(f"-# And {hidden} more.")

        status = await self._clear_status(message.guild.id, message.author.id)
        try:
            if status is not None:
                await message.reply(
                    f"{message.author.mention} is no longer AFK",
                    allowed_mentions=NO_PINGS,
                )
            if lines:
                await message.reply(
                    view=InfoUI(title="Currently AFK", subtitle="\n".join(lines)),
                    allowed_mentions=NO_PINGS,
                )
        except discord.HTTPException:
            pass

    # these run even when the module is off, so nothing is kept for people who left
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        try:
            await self._clear_status(member.guild.id, member.id)
        except Exception:
            log.exception(
                "Couldn't clear the AFK status of %s in guild %s",
                member.id,
                member.guild.id,
            )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM afk_statuses WHERE guild_id = ?",
                    (guild.id,),
                )
                await db.commit()
            self._statuses.pop(guild.id, None)
        except Exception:
            log.exception("Couldn't clean up %s data for guild %s", KEY, guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AfkCog(bot))
