import discord
from discord import app_commands
from discord.ext import commands

from globals import (
    INVITE_URL,
    LOG_CHANNEL,
    MELVIN_BANNER,
    MELVIN_WARN_EMOJI,
)
from ui import ErrorUI, PositiveUI, ResponseUI


class PrivateCog(
    commands.GroupCog,
    name="private",
    description="Private administrative and developer utilities.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
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
                discord.ui.MediaGallery(discord.MediaGalleryItem(media=f"{MELVIN_BANNER}")),
            ),
        )

        try:
            await log_channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

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
                discord.ui.MediaGallery(discord.MediaGalleryItem(media=f"{MELVIN_BANNER}")),
            ),
        )

        try:
            await log_channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(name="sync", description="Sync the application command tree.")
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not await self.bot.is_owner(interaction.user):
            view = ResponseUI(f"{MELVIN_WARN_EMOJI} **This command is gated. Please read our documentation in our [support server]({INVITE_URL}).**")
            await interaction.followup.send(view=view, ephemeral=True)
            return

        try:
            synced = await self.bot.tree.sync()
        except discord.HTTPException as e:
            view = ErrorUI(message=f"**{e}**")
            await interaction.followup.send(view=view, ephemeral=True)
            return

        view = PositiveUI(title="Tree Sync Complete", subtitle=f"**Synced {len(synced)} command(s).**")
        await interaction.followup.send(view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PrivateCog(bot))
