import math
import random
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import server_stats
from globals import LOG_CHANNEL, MELVIN_BANNER, MELVIN_MISC_EMOJI, QUATERNARY
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
# covers the full 30 day range
POPULATE_HOURS = 30 * 24


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


class PrivateCog(
    commands.GroupCog,
    name="private",
    description="Private administrative and developer utilities.",
):
    def __init__(self, bot: Melvin) -> None:
        super().__init__()
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log_channel = self.bot.get_channel(LOG_CHANNEL)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Melvin was just removed from {guild.name}.**\n"
                    f"Now in **{len(self.bot.guilds)}** guild(s).",
                ),
                GalleryWithItem(MELVIN_BANNER),
            ),
        )
        try:
            await log_channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden, discord.HTTPException:
            pass

    @app_commands.command(name="sync", description="Sync the application command tree.")
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not await self.bot.is_owner(interaction.user):
            view = GatedUI()
            await interaction.followup.send(view=view, ephemeral=True)
            return
        try:
            synced = await self.bot.tree.sync()
        except discord.HTTPException as e:
            view = ErrorUI(message=f"**{e}**")
            await interaction.followup.send(view=view, ephemeral=True)
            return
        view = PositiveUI(
            title="Tree Sync Complete",
            subtitle=f"**Synced {len(synced)} command(s).**",
        )
        await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(
        name="populate",
        description="Fill this server's stats with made up data.",
    )
    @app_commands.describe(density="How much activity to make up.")
    @app_commands.choices(density=DENSITY_CHOICES)
    # server only, since stats are per server
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def populate(
        self,
        interaction: discord.Interaction,
        density: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not await self.bot.is_owner(interaction.user):
            view = GatedUI()
            await interaction.followup.send(view=view, ephemeral=True)
            return
        if interaction.guild_id is None:
            return

        rows = _fake_stats(density.value)
        await server_stats.init_db()
        await server_stats.replace(interaction.guild_id, rows)
        view = PositiveUI(
            title="Server Stats Populated",
            subtitle=(
                f"**Replaced this server's stats with {len(rows)} hours of "
                f"{density.name.lower()} density data.**"
            ),
        )
        await interaction.followup.send(view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command,
    ) -> None:
        log_channel = self.bot.get_channel(LOG_CHANNEL)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        guild = interaction.guild

        if guild:
            location = f"in {guild.name}"
        elif isinstance(interaction.channel, (discord.DMChannel, discord.GroupChannel)):
            location = "in DMs (invoked as app)"
        else:
            location = ""

        args_lines = []
        if interaction.namespace:
            for key, value in vars(interaction.namespace).items():
                if isinstance(value, discord.Attachment):
                    val = value.filename
                else:
                    val = str(value)

                val = discord.utils.escape_markdown(val)
                val = discord.utils.escape_mentions(val)
                if len(val) > 100:
                    val = val[:97] + "..."

                args_lines.append(f"**{key}: {val}**")

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# {MELVIN_MISC_EMOJI} Command Used | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.Section(
                f"**User: {interaction.user.mention} | {interaction.user.id}**\n"
                f"**Command: /{command.qualified_name} {location}**",
                accessory=discord.ui.Thumbnail(
                    media=interaction.user.display_avatar.url,
                ),
            ),
            accent_color=discord.Color.from_str(QUATERNARY),
        )

        if args_lines:
            args_text = "\n".join(args_lines)
            container.add_item(SmallSeparator())
            container.add_item(
                discord.ui.TextDisplay(f"### Arguments\n{args_text}"),
            )

        view = discord.ui.LayoutView()
        view.add_item(container)

        try:
            await log_channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden, discord.HTTPException:
            pass


async def setup(bot: Melvin) -> None:
    await bot.add_cog(PrivateCog(bot))
