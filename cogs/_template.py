# a blank module to copy when making a new one. files starting with an underscore
# aren't loaded. to use it:
#   1. copy it to cogs/<key>.py and replace "template" with the key
#   2. fill in MODULE
#   3. restart the bot
# see docs/developers.md for details

import logging

import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import ERROR_MESSAGE
from module_registry import Module, Setting
from ui import ErrorUI, ResponseUI, open_config

log = logging.getLogger(__name__)

KEY = "template"

# the label and description are shown on /modules and the dashboard. settings are
# optional, without them remove the config command
MODULE = Module(
    KEY,
    "Template",
    "One short line about what it does.",
    settings=(
        Setting(
            "channel",
            "Channel",
            "Where this module posts. Nothing is posted until one is set.",
            "channel",
        ),
    ),
)


# server only. remove both decorators to allow dms and user installs
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class TemplateCog(
    commands.GroupCog,
    name=KEY,
    description="you'd describe what this cog / module does here",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "**You do not have permission to do this.**"
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "**This command can only be used in a server.**"
        else:
            log.error(error)
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    # commands are blocked automatically when the module is off
    @app_commands.command(name="hello", description="Say hello.")
    async def hello(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            view=ResponseUI(f"**Hello, {interaction.user.mention}!**"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # uses the settings in MODULE, like the dashboard's Config button
    @app_commands.command(
        name="config",
        description="Change this module's settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, KEY)

    # listeners aren't blocked when the module is off, so they check it themselves
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or not await module_settings.is_enabled(member.guild.id, KEY):
            return

    # runs even when the module is off
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        if not module_config.is_configurable(KEY):
            return
        try:
            await module_config.clear_module(guild.id, KEY)
        except Exception:
            log.exception("Couldn't clean up %s settings for guild %s", KEY, guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TemplateCog(bot))
