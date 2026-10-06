import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import ERROR_MESSAGE
from ui import ErrorUI, GalleryWithItem, ResponseUI, open_config

log = logging.getLogger(__name__)


async def safe_finish(
    interaction: discord.Interaction,
    view: discord.ui.LayoutView,
    file: discord.File | None = None,
) -> None:
    try:
        if file is not None:
            await interaction.edit_original_response(view=view, attachments=[file])
        else:
            await interaction.edit_original_response(view=view)
    except discord.NotFound:
        log.warning(
            "Original interaction response missing; falling back to followup.send",
        )
        try:
            if file is not None:
                await interaction.followup.send(view=view, file=file)
            else:
                await interaction.followup.send(view=view)
        except discord.NotFound, discord.HTTPException:
            log.exception("Followup send also failed")


def _load_image_file(path: str | None) -> discord.File | None:
    if not path or not Path(path).is_file():
        return None
    return discord.File(path, filename=Path(path).name)


@app_commands.guild_only
class WelcomeCog(
    commands.GroupCog,
    name="welcome",
    description="Configure welcome messages and settings for new members.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = "data/welcome.db"

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
            log.error(error)
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    def _build_welcome_ui(
        self,
        values: dict[str, str | None],
        target_member: discord.Member | discord.User,
    ) -> tuple[ResponseUI, discord.File | None]:
        text = (values["message"] or "").replace("{member}", target_member.mention)
        guild = getattr(target_member, "guild", None)
        if guild is not None:
            text = text.replace("{member_count}", str(guild.member_count))

        view = ResponseUI(text)

        file = _load_image_file(values["image"])
        if file is not None:
            view.container.add_item(GalleryWithItem(f"attachment://{file.filename}"))

        buttons = [
            discord.ui.Button(
                label=values[f"button{number}_label"],
                style=discord.ButtonStyle.link,
                url=values[f"button{number}_url"],
            )
            for number in (1, 2)
            if values[f"button{number}_url"]
        ]
        if buttons:
            view.container.add_item(discord.ui.ActionRow(*buttons))

        return view, file

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

        await interaction.response.defer()

        values = await module_config.get_all(interaction.guild.id, "welcome")
        if not values["channel"]:
            await safe_finish(
                interaction,
                ErrorUI("**Set a welcome channel first with /welcome config.**"),
            )
            return

        view, file = self._build_welcome_ui(values, interaction.user)
        await safe_finish(interaction, view, file=file)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await module_settings.is_enabled(member.guild.id, "welcome"):
            return

        values = await module_config.get_all(member.guild.id, "welcome")
        channel_id = values["channel"]
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return

        view, file = self._build_welcome_ui(values, member)

        try:
            if file is not None:
                await channel.send(view=view, file=file)
            else:
                await channel.send(view=view)
        except discord.Forbidden, discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            await module_config.clear_module(guild.id, "welcome")
        except Exception:
            log.exception(
                "failed to clean up welcome config for departed guild %s",
                guild.id,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
