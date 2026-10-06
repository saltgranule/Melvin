import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

import module_config
import module_settings
from globals import (
    ERROR_MESSAGE,
    LOG_CHANNEL,
    MELVIN_BANNER,
    DisplayNameEffect,
    DisplayNameFont,
)
from ui import ErrorUI, GalleryWithItem, open_config

if TYPE_CHECKING:
    from main import Melvin

log = logging.getLogger(__name__)


# server only, installed to a server and used in it, never in dms or as a user app
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class StyleCog(
    commands.GroupCog,
    name="style",
    description="Name style configuration commands.",
):
    def __init__(self, bot: Melvin) -> None:
        super().__init__()
        self.bot = bot
        # what was last sent to discord per guild, so unchanged styles aren't resent
        self._applied: dict[int, tuple[str | None, ...]] = {}
        self._synced_at = time.time()

    async def cog_load(self) -> None:
        self.sync_styles.start()

    async def cog_unload(self) -> None:
        self.sync_styles.cancel()

    # cogwide error handling
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
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def apply_style(self, guild: discord.Guild) -> None:
        values = await module_config.get_all(guild.id, "style")
        key = (values["font"], values["effect"], values["colors"])
        if self._applied.get(guild.id) == key:
            return

        colors = (values["colors"] or "FFFFFF").split("-")
        effect = DisplayNameEffect[values["effect"]]
        # gradients need two colors and everything else uses one
        if effect is DisplayNameEffect.gradient:
            colors = [colors[0], colors[-1]]
        else:
            colors = colors[:1]

        await self.bot.set_name_style(
            guild=guild,
            font_id=DisplayNameFont[values["font"]],
            effect_id=effect,
            colors=colors,
        )
        self._applied[guild.id] = key

    # picks up changes made on the dashboard, which can't reach the bot directly
    @tasks.loop(seconds=15)
    async def sync_styles(self) -> None:
        since = self._synced_at
        started = time.time()
        changed = await module_config.changed_since("style", since)
        self._synced_at = started

        for guild_id in changed:
            guild = self.bot.get_guild(guild_id)
            if guild is None or not await module_settings.is_enabled(guild_id, "style"):
                continue
            try:
                await self.apply_style(guild)
            except discord.HTTPException:
                log.exception("Failed to apply the name style in guild %s", guild_id)
                # look from the same point next time, so this guild is retried
                self._synced_at = since

    @sync_styles.before_loop
    async def before_sync_styles(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        # only the style is part of the module, the join log always happens
        if await module_settings.is_enabled(guild.id, "style"):
            try:
                await self.apply_style(guild)
            except discord.HTTPException:
                log.exception("Failed to apply the name style in guild %s", guild.id)

        log_channel = self.bot.get_channel(LOG_CHANNEL)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Melvin was just added to {guild.name}.**\n"
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

    @app_commands.command(
        name="config",
        description="Change Melvin's name style for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "style", on_change=self.apply_style)


async def setup(bot: Melvin) -> None:
    await bot.add_cog(StyleCog(bot))
