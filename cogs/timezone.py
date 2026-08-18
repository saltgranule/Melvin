import datetime
import random
import zoneinfo

import aiosqlite
import discord
from discord import AllowedMentions, app_commands
from discord.ext import commands

from ui import ErrorUI, InfoUI, PositiveUI, ResponseUI

time_quotes = [
    "**Men talk of killing time, while time quietly kills them.**\n-# *-- Dion Boucicault*",
    "**Time brings all things to pass.**\n-# *-- Aeschylus*",
    "**Time is a storm in which we are all lost.**\n-# *-- William Carlos Williams*",
    "**The trouble is, you think you have time.**\n-# *-- Jack Kornfield*",
    "**The only reason for time is so that everything does not happen at once.**\n-# *-- Albert Einstein*",
    "**Who controls the past, controls the future: who controls the present controls the past.**\n-# *-- George Orwell*",
    "**They always say time changes things, but you actually have to change them yourself.**\n-# *-- Andy Warhol*",
    "**There is never enough time to do all the nothing you want.**\n-# *-- Bill Watterson*",
    "**It is not that we have little time, but more that we waste a good deal of it.**\n-# *-- Seneca*",
]


def format_ordinal(day: int) -> str:
    if 11 <= day <= 13:
        return f"{day}th"
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    return f"{day}{suffixes.get(day % 10, 'th')}"


def format_date(dt: datetime.datetime) -> str:
    month = dt.strftime("%B")
    day_str = format_ordinal(dt.day)
    year = dt.strftime("%Y")
    return f"{month} {day_str}, {year}"


class TimezoneCog(
    commands.GroupCog,
    name="timezone",
    description="Set or view timezones for users.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = "data/timezones.db"

    async def _ensure_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_timezones (
                    user_id INTEGER PRIMARY KEY,
                    timezone TEXT NOT NULL
                )
            """)
            await conn.commit()

    async def cog_load(self) -> None:
        await self._ensure_db()

    async def _get_user_timezone(self, user_id: int) -> str | None:
        async with (
            aiosqlite.connect(self.db_path) as conn,
            conn.execute(
                "SELECT timezone FROM user_timezones WHERE user_id = ?",
                (user_id,),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            return row[0] if row else None

    async def _set_user_timezone(self, user_id: int, tz_string: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO user_timezones (user_id, timezone)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET timezone = excluded.timezone
            """,
                (user_id, tz_string),
            )
            await conn.commit()

    async def _reset_user_timezone(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM user_timezones WHERE user_id = ?",
                (user_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def timezone_autocomplete(
        self,
        _interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        all_tzs = sorted(zoneinfo.available_timezones())
        filtered = [
            tz
            for tz in all_tzs
            if current.lower() in tz.lower().replace("_", " ")
            or current.lower() in tz.lower()
        ]
        return [
            app_commands.Choice(name=tz.replace("_", " "), value=tz)
            for tz in filtered[:25]
        ]

    @app_commands.command(
        name="for",
        description="View a user's timezone, defaulting to your timezone.",
    )
    @app_commands.describe(user="The user whose timezone you want to view.")
    async def for_user(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        target_user = user or interaction.user
        target_tz_str = await self._get_user_timezone(target_user.id)

        # easter eggs
        if target_user == interaction.client.user:
            view = ResponseUI(random.choice(time_quotes))
            await interaction.response.send_message(view=view)
            return

        if target_user.bot:
            view = ErrorUI("You tried to view a bot's timezone.")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
            return

        if not target_tz_str:
            name = "You" if target_user == interaction.user else target_user.mention
            suffix = (
                " do not have a timezone set."
                if target_user == interaction.user else
                " does not have a timezone set."
            )
            view = ErrorUI(f"{name}{suffix}")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
            return

        now_utc = datetime.datetime.now(datetime.UTC)
        target_tz = zoneinfo.ZoneInfo(target_tz_str)
        target_time = now_utc.astimezone(target_tz)

        if target_user == interaction.user:
            time_str = target_time.strftime("%I:%M %p").lstrip("0")
            date_str = format_date(target_time)
            view = InfoUI(title="Your Timezone", subtitle=f"It is currently **{time_str}** for you. Today is **{date_str}**.")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
            return

        runner_tz_str = await self._get_user_timezone(interaction.user.id)
        if not runner_tz_str:
            time_str = target_time.strftime("%I:%M %p").lstrip("0")
            view = InfoUI(title=f"Timezone for {target_user.mention}", subtitle=f"It is currently **{time_str}** for {target_user.mention}. (Set your own timezone to see time differences.)")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
            return

        runner_tz = zoneinfo.ZoneInfo(runner_tz_str)
        runner_time = now_utc.astimezone(runner_tz)

        target_utcoffset = target_time.utcoffset()
        runner_utcoffset = runner_time.utcoffset()

        target_offset = target_utcoffset.total_seconds() / 3600 if target_utcoffset else 0.0
        runner_offset = runner_utcoffset.total_seconds() / 3600 if runner_utcoffset else 0.0

        diff_hours = abs(runner_offset - target_offset)

        diff_str = f"{int(diff_hours)}" if diff_hours.is_integer() else f"{diff_hours}"
        relation = "ahead" if runner_offset < target_offset else "behind"

        target_time_str = target_time.strftime("%I:%M %p").lstrip("0")
        runner_time_str = runner_time.strftime("%I:%M %p").lstrip("0")

        if target_time.date() == runner_time.date():
            day_ctx = "You are both on the same day."
        else:
            target_date_str = format_date(target_time)
            runner_date_str = format_date(runner_time)
            day_ctx = f"It is **{target_date_str}** for {target_user.mention}, while it is **{runner_date_str}** for you."

        if diff_hours == 0:
            view = InfoUI(
                title=f"Timezone for {target_user.mention}",
                subtitle=f"It is currently **{target_time_str}** for {target_user.mention}. You are both in the same timezone.",
            )
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
        else:
            view = InfoUI(
                title=f"Timezone for {target_user.mention}",
                subtitle=(
                    f"It is currently **{target_time_str}** for {target_user.mention}. You are **{diff_str}** hours behind, at **{runner_time_str}**. {day_ctx}"
                    if relation == "ahead"
                    else f"It is currently **{target_time_str}** for {target_user.mention}. You are **{diff_str}** hours ahead, at **{runner_time_str}**. {day_ctx}"
                ),
            )
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )

    @app_commands.command(name="at", description="View a timezone at a certain area.")
    @app_commands.describe(timezone="The name or region of the timezone to view.")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    async def at(self, interaction: discord.Interaction, timezone: str) -> None:
        try:
            tz = zoneinfo.ZoneInfo(timezone)
            now_utc = datetime.datetime.now(datetime.UTC)
            target_time = now_utc.astimezone(tz)

            time_str = target_time.strftime("%I:%M %p").lstrip("0")
            date_str = format_date(target_time)

            view = InfoUI(
                title=f"Timezone for {timezone.replace('_', ' ')}",
                subtitle=f"It is currently **{time_str}** for those in **{timezone.replace('_', ' ')}**. It is **{date_str}** for them.",
            )
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, KeyError):
            view = ErrorUI(f"{timezone.replace('_', ' ')} is not a valid timezone.")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )

    @app_commands.command(name="set", description="Set your timezone.")
    @app_commands.describe(timezone="The timezone to save for your account.")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    async def set(self, interaction: discord.Interaction, timezone: str) -> None:
        try:
            zoneinfo.ZoneInfo(timezone)
            await self._set_user_timezone(interaction.user.id, timezone)
            view = PositiveUI(title="Timezone Set", subtitle=f"Set your timezone to **{timezone.replace('_', ' ')}**.")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, KeyError):
            view = ErrorUI(f"{timezone.replace('_', ' ')} is not a valid timezone.")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )

    @app_commands.command(name="reset", description="Reset your timezone.")
    async def reset(self, interaction: discord.Interaction) -> None:
        deleted = await self._reset_user_timezone(interaction.user.id)
        if not deleted:
            view = ErrorUI("You do not have a timezone set.")
            await interaction.response.send_message(
                view=view, allowed_mentions=AllowedMentions.none(),
            )
            return

        view = PositiveUI(title="Timezone Reset", subtitle="Reset your timezone.")
        await interaction.response.send_message(
            view=view, allowed_mentions=AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TimezoneCog(bot))
