import logging

import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import ERROR_MESSAGE
from ui import ErrorUI, open_config

log = logging.getLogger(__name__)


# server only, installed to a server and used in it, never in dms or as a user app
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class AutoPublishCog(
    commands.GroupCog,
    name="autopublish",
    description="Publish messages in announcement channels automatically.",
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

    @app_commands.command(
        name="config",
        description="Change which announcement channels are published automatically.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "autopublish")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # the channel type is free to check, so it goes before anything that hits the db
        if message.guild is None or message.channel.type is not discord.ChannelType.news:
            return
        # "thread created", "poll ended" and friends can't be published anyway
        if message.is_system() or message.author.system:
            return
        if not await module_settings.is_enabled(message.guild.id, "autopublish"):
            return

        settings = await module_config.get_all(message.guild.id, "autopublish")
        if str(message.channel.id) not in (settings["channels"] or "").split(","):
            return
        # webhooks count as bots here, which is what feeds from other apps usually are
        if message.author.bot and settings["bots"] != "on":
            return

        # discord allows 10 publishes an hour per channel. past that, discord.py waits
        # until it's allowed again, so a busy channel publishes late rather than never
        try:
            await message.publish()
        except discord.Forbidden:
            log.info(
                "Missing permissions to publish in channel %s of guild %s",
                message.channel.id,
                message.guild.id,
            )
        except discord.HTTPException:
            log.warning(
                "Couldn't publish message %s in guild %s",
                message.id,
                message.guild.id,
            )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            await module_config.clear_module(guild.id, "autopublish")
        except Exception:
            log.exception(
                "Couldn't clean up autopublish settings for guild %s",
                guild.id,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoPublishCog(bot))
