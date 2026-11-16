import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from cogs import _greeting
from globals import DATA_DIR
from module_registry import Module, Setting
from ui import open_config

_MESSAGE = _greeting.message_settings(
    channel_label="Welcome channel",
    noun="welcome",
    event="join",
    default="Welcome, {member}!",
    example="Welcome, {member}! We're at {member_count} members now.",
    group="Welcome message",
)

MODULE = Module(
    "welcome",
    "Welcome",
    "Welcome messages for new members.",
    settings=(
        *_MESSAGE[:3],
        Setting(
            "bots",
            "Bot welcomes",
            "Whether bots get the welcome message too.",
            "choice",
            default="off",
            choices=(("off", "Skip bots"), ("on", "Welcome bots")),
            group="Welcome message",
        ),
        *_MESSAGE[3:],
    ),
    panel=_greeting.placeholder_panel("joined"),
)


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class WelcomeCog(
    commands.GroupCog,
    name="welcome",
    description="Configure welcome messages and settings for new members.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = DATA_DIR / "welcome.db"

    async def cog_load(self) -> None:
        await module_config.migrate_legacy(
            self.db_path,
            "welcome_channels",
            "welcome",
            lambda row: (
                int(row[0]),
                {
                    "channel": row[1],
                    "message": row[2],
                    "image": row[3],
                    "button1_url": row[4],
                    "button1_label": row[5],
                    "button2_url": row[6],
                    "button2_label": row[7],
                },
            ),
        )

    @app_commands.command(
        name="config",
        description="Change welcome message settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "welcome")

    @app_commands.command(
        name="preview",
        description="Preview what the configured welcome notification looks like.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def preview(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        when = interaction.user.joined_at or discord.utils.utcnow()
        await _greeting.preview(interaction, "welcome", when)

    @commands.Cog.listener()
    async def on_member_admit(self, member: discord.Member) -> None:
        if not await module_settings.is_enabled(member.guild.id, "welcome"):
            return
        values = await module_config.get_all(member.guild.id, "welcome")
        if member.bot and values["bots"] != "on":
            return
        when = member.joined_at or discord.utils.utcnow()
        await _greeting.send(self.bot, values, member, when)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await _greeting.clear(guild, "welcome")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
