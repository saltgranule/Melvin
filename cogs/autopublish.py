import logging

import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from module_registry import Module, Setting
from ui import open_config

MODULE = Module(
    "autopublish",
    "Auto-Publish",
    "Publishes messages in announcement channels.",
    settings=(
        Setting(
            "channels",
            "Channels",
            "Pick announcement channels, anything else is skipped.",
            "channels",
            channel_type="any",
            group="Publishing",
        ),
        Setting(
            "bots",
            "Bot messages",
            "Whether messages from bots and webhooks are published too, like feeds from other apps.",
            "choice",
            default="off",
            choices=(("off", "Skip them"), ("on", "Publish them")),
            group="Publishing",
        ),
    ),
)

log = logging.getLogger(__name__)


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

    @app_commands.command(
        name="config",
        description="Change which announcement channels are published automatically.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "autopublish")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if (
            guild is None
            or message.channel.type is not discord.ChannelType.news
            or message.is_system()
            or message.author.system
            or not await module_settings.is_enabled(guild.id, "autopublish")
        ):
            return

        settings = await module_config.get_all(guild.id, "autopublish")
        if message.author.bot and settings["bots"] != "on":
            return
        if str(message.channel.id) not in (settings["channels"] or "").split(","):
            return

        try:
            await message.publish()
        except discord.Forbidden:
            log.info(
                "Missing permissions to publish in channel %s of guild %s",
                message.channel.id,
                guild.id,
            )
        except discord.HTTPException:
            log.warning("Couldn't publish message %s in guild %s", message.id, guild.id)

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
