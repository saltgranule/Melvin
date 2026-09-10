import discord
from discord import app_commands
from discord.ext import commands

from globals import LOG_CHANNEL, MELVIN_BANNER, MELVIN_MISC_EMOJI, QUATERNARY
from main import Melvin
from ui import ErrorUI, GalleryWithItem, GatedUI, PositiveUI, SmallSeparator


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
        except (discord.Forbidden, discord.HTTPException):
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
        view = PositiveUI(title="Tree Sync Complete", subtitle=f"**Synced {len(synced)} command(s).**")
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
                accessory=discord.ui.Thumbnail(media=interaction.user.display_avatar.url),
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
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot: Melvin) -> None:
    await bot.add_cog(PrivateCog(bot))
