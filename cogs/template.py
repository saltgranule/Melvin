# a blank module to start new ones from. it isn't loaded, so nothing here shows up in
# discord until it's copied. to make a real module out of it:
#   1. copy this file to cogs/<key>.py and swap every "template" for the new key
#   2. add the key to MODULES in module_settings.py, it's what gives the module its switch
#          "template": ("Template", "One short line about what it does."),
#   3. load it in main.py, next to the other cogs
#          await bot.load_extension("cogs.<key>")
#   4. give it a page in docs/, and a config section if it has settings
# docs/developers.md has the long version

import logging

import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import ERROR_MESSAGE
from ui import ErrorUI, ResponseUI, open_config

log = logging.getLogger(__name__)

KEY = "template"


# server only. drop both decorators if the commands make sense in dms or as a user app
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

    # commands are blocked on their own when the module's off. nothing to check here
    @app_commands.command(name="hello", description="Say hello.")
    async def hello(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            view=ResponseUI(f"**Hello, {interaction.user.mention}!**"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # settings live in CONFIG in module_config.py, keyed by KEY. once there's an entry,
    # this command and the dashboard's Config button both work. no entry yet? delete it
    @app_commands.command(
        name="config",
        description="Change this module's settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, KEY)

    # listeners are a different thing. they run either way, so each one checks first
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or not await module_settings.is_enabled(member.guild.id, KEY):
            return

    # runs whether the module's on or not, the guild is gone either way
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
