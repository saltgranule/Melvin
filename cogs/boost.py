import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from cogs import _greeting
from module_registry import Module
from ui import open_config

MODULE = Module(
    "boost",
    "Boost",
    "Boost messages for new boosters.",
    settings=_greeting.message_settings(
        channel_label="Boost channel",
        noun="boost",
        event="boost",
        default="Thanks for boosting, {member}!",
        example="Thanks for boosting {server_name}, {member}!",
        group="Boost message",
    ),
    panel=_greeting.placeholder_panel("started boosting"),
)


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class BoostCog(
    commands.GroupCog,
    name="boost",
    description="Configure boost messages for new boosters.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(
        name="config",
        description="Change boost message settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "boost")

    @app_commands.command(
        name="preview",
        description="Preview what the configured boost notification looks like.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def preview(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        when = interaction.user.premium_since or discord.utils.utcnow()
        await _greeting.preview(interaction, "boost", when)

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        if before.premium_since is not None or after.premium_since is None:
            return
        if not await module_settings.is_enabled(after.guild.id, "boost"):
            return
        values = await module_config.get_all(after.guild.id, "boost")
        await _greeting.send(self.bot, values, after, after.premium_since)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await _greeting.clear(guild, "boost")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BoostCog(bot))
