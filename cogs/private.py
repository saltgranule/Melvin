import math
import random
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import server_stats
import site_banner
from globals import (
    LOG_CHANNEL,
    MELVIN_JOINED_BANNER,
    MELVIN_LEFT_BANNER,
    MELVIN_MISC_EMOJI,
    QUATERNARY,
    SERVER_EVENTS,
)
from helpers.text import censor
from ui import ErrorUI, GalleryWithItem, GatedUI, PositiveUI, SmallSeparator

if TYPE_CHECKING:
    from main import Melvin


DENSITIES = {
    "low": (15, 3, 40),
    "medium": (90, 12, 600),
    "high": (450, 45, 6000),
}
DENSITY_CHOICES = [
    app_commands.Choice(name=key.title(), value=key) for key in DENSITIES
]
BANNER_TYPE_CHOICES = [
    app_commands.Choice(name=key.title(), value=key) for key in site_banner.KINDS
]
POPULATE_HOURS = 30 * 24
LOG_COLOR = discord.Color.from_str(QUATERNARY)
MAX_ARG_LENGTH = 100


def _fake_stats(density: str) -> list[tuple[int, int, int, int]]:
    peak_messages, peak_voice, members = DENSITIES[density]
    members *= random.uniform(0.8, 1.2)
    growth = random.uniform(0.001, 0.004)
    first = server_stats.hour_start() - (POPULATE_HOURS - 1) * server_stats.HOUR

    rows = []
    day_mood = 1.0
    for i in range(POPULATE_HOURS):
        hour = first + i * server_stats.HOUR
        hour_of_day = hour // server_stats.HOUR % 24
        day = hour // server_stats.DAY
        if hour_of_day == 0 or i == 0:
            day_mood = random.uniform(0.6, 1.4)
        weekend = 1.25 if (day + 3) % 7 in {5, 6} else 1.0

        curve = 0.55 - 0.45 * math.cos((hour_of_day - 8) / 24 * 2 * math.pi)
        activity = curve * day_mood * weekend * random.uniform(0.7, 1.3)

        messages = max(0, round(peak_messages * activity))
        in_voice = max(0, round(peak_voice * activity * random.uniform(0.5, 1.2)))
        voice_minutes = sum(random.randint(15, 60) for _ in range(in_voice))

        change = members * growth / 24 * random.uniform(-1.5, 3)
        if random.random() < 0.003:
            change -= members * random.uniform(0.002, 0.008)
        members = max(1.0, members + change)

        rows.append((hour, messages, voice_minutes, round(members)))
    return rows


def _argument(value: object) -> str:
    text = value.filename if isinstance(value, discord.Attachment) else str(value)
    text = discord.utils.escape_mentions(discord.utils.escape_markdown(text))
    return text[: MAX_ARG_LENGTH - 3] + "..." if len(text) > MAX_ARG_LENGTH else text


def _guild_label(guild: discord.Guild) -> str:
    return discord.utils.escape_markdown(censor(guild.name)) or "an unknown server"


def _location(interaction: discord.Interaction) -> str:
    if interaction.guild:
        return f"in {interaction.guild.name}"
    if isinstance(interaction.channel, discord.DMChannel | discord.GroupChannel):
        return "in DMs (invoked as app)"
    return ""


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class PrivateCog(
    commands.GroupCog,
    name="private",
    description="Private administrative and developer utilities.",
):
    banner = app_commands.Group(
        name="banner",
        description="The banner shown above the website's navbar.",
    )

    def __init__(self, bot: Melvin) -> None:
        super().__init__()
        self.bot = bot

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if await self.bot.is_owner(interaction.user):
            return True
        await interaction.response.send_message(view=GatedUI(), ephemeral=True)
        return False

    @banner.command(
        name="set",
        description="Show a message above the website's navbar.",
    )
    @app_commands.describe(
        text="What the banner says.",
        type="Primary is orange, positive is green, negative is red. Keeps the current type if left out.",
    )
    @app_commands.choices(type=BANNER_TYPE_CHOICES)
    async def banner_set(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, site_banner.MAX_LENGTH],
        type: app_commands.Choice[str] | None = None,  # ruff: ignore[builtin-argument-shadowing]
    ) -> None:
        if not await self._owner_only(interaction):
            return
        current = site_banner.load()
        kind = type.value if type else (current["kind"] if current else "primary")
        site_banner.save(text, kind)
        await interaction.response.send_message(
            view=PositiveUI(
                title="Banner Set",
                subtitle=f"**The website now shows a {kind} banner above the navbar.**",
            ),
            ephemeral=True,
        )

    @banner.command(
        name="type",
        description="Change the colour of the website's banner.",
    )
    @app_commands.describe(
        type="Primary is orange, positive is green, negative is red.",
    )
    @app_commands.choices(type=BANNER_TYPE_CHOICES)
    async def banner_type(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],  # ruff: ignore[builtin-argument-shadowing]
    ) -> None:
        if not await self._owner_only(interaction):
            return
        current = site_banner.load()
        if current is None:
            await interaction.response.send_message(
                view=ErrorUI(
                    "**There's no banner yet. Set one with /private banner set first.**",
                ),
                ephemeral=True,
            )
            return
        site_banner.save(current["text"], type.value)
        await interaction.response.send_message(
            view=PositiveUI(
                title="Banner Type Changed",
                subtitle=f"**The website's banner is now {type.value}.**",
            ),
            ephemeral=True,
        )

    @banner.command(name="clear", description="Remove the banner from the website.")
    async def banner_clear(self, interaction: discord.Interaction) -> None:
        if not await self._owner_only(interaction):
            return
        site_banner.clear()
        await interaction.response.send_message(
            view=PositiveUI(
                title="Banner Cleared",
                subtitle="**The website no longer shows a banner.**",
            ),
            ephemeral=True,
        )

    def _log_channel(self, channel_id: int = LOG_CHANNEL) -> discord.TextChannel | None:
        channel = self.bot.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _log(
        self,
        channel: discord.TextChannel,
        container: discord.ui.Container,
    ) -> None:
        view = discord.ui.LayoutView()
        view.add_item(container)
        try:
            await channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        channel = self._log_channel(SERVER_EVENTS)
        if channel is None:
            return
        await self._log(
            channel,
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Melvin was just added to {_guild_label(guild)}.**\n"
                    f"Now in **{len(self.bot.guilds)}** guild(s).",
                ),
                GalleryWithItem(MELVIN_JOINED_BANNER),
            ),
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        channel = self._log_channel(SERVER_EVENTS)
        if channel is None:
            return
        if guild.unavailable:
            return
        await self._log(
            channel,
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Melvin was just removed from {_guild_label(guild)}.**\n"
                    f"Now in **{len(self.bot.guilds)}** guild(s).",
                ),
                GalleryWithItem(MELVIN_LEFT_BANNER),
            ),
        )

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command,
    ) -> None:
        channel = self._log_channel()
        if channel is None:
            return

        user = interaction.user
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# {MELVIN_MISC_EMOJI} Command Used | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.Section(
                f"**User: {user.mention} | {user.id}**\n"
                f"**Command: /{command.qualified_name} {_location(interaction)}**",
                accessory=discord.ui.Thumbnail(media=user.display_avatar.url),
            ),
            accent_color=LOG_COLOR,
        )

        arguments = "\n".join(
            f"**{key}: {_argument(value)}**"
            for key, value in vars(interaction.namespace).items()
        )
        if arguments:
            container.add_item(SmallSeparator())
            container.add_item(discord.ui.TextDisplay(f"### Arguments\n{arguments}"))

        await self._log(channel, container)

    @app_commands.command(
        name="populate",
        description="Fill this server's stats with made up data.",
    )
    @app_commands.describe(density="How much activity to make up.")
    @app_commands.choices(density=DENSITY_CHOICES)
    async def populate(
        self,
        interaction: discord.Interaction,
        density: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not await self.bot.is_owner(interaction.user):
            await interaction.followup.send(view=GatedUI(), ephemeral=True)
            return
        if interaction.guild_id is None:
            await interaction.followup.send(
                view=ErrorUI("**This command only works in a server.**"),
                ephemeral=True,
            )
            return

        rows = _fake_stats(density.value)
        await server_stats.init_db()
        await server_stats.replace(interaction.guild_id, rows)
        await interaction.followup.send(
            view=PositiveUI(
                title="Server Stats Populated",
                subtitle=(
                    f"**Replaced this server's stats with {len(rows)} hours of "
                    f"{density.name.lower()} density data.**"
                ),
            ),
            ephemeral=True,
        )


async def setup(bot: Melvin) -> None:
    await bot.add_cog(PrivateCog(bot))
