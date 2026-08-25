import logging

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from globals import ERROR_MESSAGE
from ui import ErrorUI, ExceptionUI, GalleryWithItem, PositiveUI, ResponseUI

log = logging.getLogger(__name__)


class ConfigModal(discord.ui.Modal, title="Welcome Configuration"):
    def __init__(
        self,
        bot: commands.Bot,
        db_path: str,
        text: str,
        current_config: dict | None,
    ) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = db_path
        self.text = text

        # Retrieve existing settings for defaults
        b1_url_def = (current_config.get("b1_url") if current_config else None) or ""
        b1_label_def = (current_config.get("b1_label") if current_config else None) or ""
        b2_url_def = (current_config.get("b2_url") if current_config else None) or ""
        b2_label_def = (current_config.get("b2_label") if current_config else None) or ""

        self._attachment_image = discord.ui.FileUpload()
        self.attachment_image = discord.ui.Label(
            text="Welcome Image",
            description="Optional image to attach to the welcome message.",
            component=self._attachment_image,
        )

        self._button1_url = discord.ui.TextInput(default=b1_url_def, required=False)
        self.button1_url = discord.ui.Label(
            text="Button 1 URL",
            description="Optional first button URL.",
            component=self._button1_url,
        )
        self._button1_text = discord.ui.TextInput(
            default=b1_label_def,
            placeholder="Defaults to 'Link 1'.",
            required=False,
        )
        self.button1_text = discord.ui.Label(
            text="Button 1 Label",
            description="Label for the first button.",
            component=self._button1_text,
        )

        self._button2_url = discord.ui.TextInput(default=b2_url_def, required=False)
        self.button2_url = discord.ui.Label(
            text="Button 2 URL",
            description="Optional second button URL.",
            component=self._button2_url,
        )
        self._button2_text = discord.ui.TextInput(
            default=b2_label_def,
            placeholder="Defaults to 'Link 2'.",
            required=False,
        )
        self.button2_text = discord.ui.Label(
            text="Button 2 Label",
            description="Label for the second button.",
            component=self._button2_text,
        )

        for item in [
            self.attachment_image,
            self.button1_url,
            self.button1_text,
            self.button2_url,
            self.button2_text,
        ]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        await interaction.response.defer()

        # Extract values from components
        b1_url = str(self._button1_url.value).strip() or None
        b1_label = str(self._button1_text.value).strip() or "Link 1"
        b2_url = str(self._button2_url.value).strip() or None
        b2_label = str(self._button2_text.value).strip() or "Link 2"

        # Handle attachment file upload if provided
        attachment_url = None
        if self._attachment_image.values:
            uploaded_file = self._attachment_image.values[0]
            attachment_url = getattr(uploaded_file, "url", None)

        # URL Validation
        for url in (b1_url, b2_url):
            if url and not url.startswith(("http://", "https://")):
                await interaction.edit_original_response(
                    view=ErrorUI("All button URLs must be valid HTTP or HTTPS links."),
                )
                return

        try:
            async with (
                aiosqlite.connect(self.db_path) as conn,
                conn.execute(
                    "SELECT channel_id FROM welcome_channels WHERE guild_id = ?",
                    (str(interaction.guild.id),),
                ) as cursor,
            ):
                row = await cursor.fetchone()
            existing_channel_id = row[0] if row else None
        except Exception:
            log.exception("Database error while fetching channel")
            await interaction.edit_original_response(view=ExceptionUI())
            return

        if existing_channel_id is None:
            await interaction.edit_original_response(
                view=ErrorUI(
                    "**Set a welcome channel first using `/welcome channel`.**",
                ),
            )
            return

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO welcome_channels
                    (guild_id, channel_id, message, attachment_url, b1_url, b1_label, b2_url, b2_label)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(interaction.guild.id),
                        existing_channel_id,
                        self.text,
                        attachment_url,
                        b1_url,
                        b1_label,
                        b2_url,
                        b2_label,
                    ),
                )
                await conn.commit()
        except Exception:
            log.exception("Database error")
            await interaction.followup.send(view=ExceptionUI())
            return

        view = PositiveUI(title="Welcome Config Set", subtitle="Welcome message updated.")
        await interaction.edit_original_response(view=view)


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

    async def _ensure_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS welcome_channels (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    message TEXT,
                    attachment_url TEXT,
                    b1_url TEXT,
                    b1_label TEXT,
                    b2_url TEXT,
                    b2_label TEXT
                )
            """)
            await conn.commit()

    async def cog_load(self) -> None:
        await self._ensure_db()

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

        error_ui = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=error_ui)
        else:
            await interaction.response.send_message(view=error_ui, ephemeral=False)

    async def get_log_channel(self, guild_id: int) -> discord.abc.GuildChannel | discord.Thread | discord.abc.PrivateChannel | None:
        try:
            async with (
                aiosqlite.connect(self.db_path) as conn,
                conn.execute(
                    "SELECT channel_id FROM welcome_channels WHERE guild_id = ?",
                    (str(guild_id),),
                ) as cursor,
            ):
                row = await cursor.fetchone()
        except Exception:
            return None

        if row is None:
            return None

        return self.bot.get_channel(int(row[0]))

    async def get_welcome_config(self, guild_id: int) -> dict | None:
        try:
            async with (
                aiosqlite.connect(self.db_path) as conn,
                conn.execute(
                    "SELECT channel_id, message, attachment_url, b1_url, b1_label, b2_url, b2_label "
                    "FROM welcome_channels WHERE guild_id = ?",
                    (str(guild_id),),
                ) as cursor,
            ):
                row = await cursor.fetchone()
        except Exception:
            return None

        if row is None:
            return None

        channel_id, message, attachment_url, b1_url, b1_label, b2_url, b2_label = row
        return {
            "channel": self.bot.get_channel(int(channel_id)) if channel_id else None,
            "message": message,
            "attachment_url": attachment_url,
            "b1_url": b1_url,
            "b1_label": b1_label,
            "b2_url": b2_url,
            "b2_label": b2_label,
        }

    def _build_welcome_ui(self, config: dict[str, str], target_member: discord.Member | discord.User) -> ResponseUI:
        text = config["message"] or f"Welcome, {target_member.mention}!"
        text = text.replace("{member}", target_member.mention)

        view = ResponseUI(text)

        if config["attachment_url"]:
            view.container.add_item(GalleryWithItem(config["attachment_url"]))

        buttons = []
        if config["b1_url"]:
            buttons.append(
                discord.ui.Button(
                    label=config["b1_label"],
                    style=discord.ButtonStyle.link,
                    url=config["b1_url"],
                ),
            )
        if config["b2_url"]:
            buttons.append(
                discord.ui.Button(
                    label=config["b2_label"],
                    style=discord.ButtonStyle.link,
                    url=config["b2_url"],
                ),
            )

        if buttons:
            view.container.add_item(discord.ui.ActionRow(*buttons))

        return view

    @app_commands.command(
        name="config",
        description="Set the welcome message and optional attachments or buttons via modal.",
    )
    @app_commands.describe(
        text="The welcome message to send (use {member} to mention the new member).",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(
        self,
        interaction: discord.Interaction,
        text: str,
    ) -> None:
        if not interaction.guild:
            return

        await self._ensure_db()
        current_config = await self.get_welcome_config(interaction.guild.id)

        modal = ConfigModal(
            bot=self.bot,
            db_path=self.db_path,
            text=text,
            current_config=current_config,
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="preview",
        description="Preview what the configured welcome notification looks like.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def preview(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        await interaction.response.defer()

        config = await self.get_welcome_config(interaction.guild.id)
        if config is None or config["channel"] is None:
            await interaction.edit_original_response(
                view=ErrorUI("**No welcome configuration found. Use `/welcome channel` and `/welcome config` first.**"),
            )
            return

        view = self._build_welcome_ui(config, interaction.user)
        await interaction.edit_original_response(view=view)

    @app_commands.command(
        name="channel",
        description="Set or reset the channel for member join events.",
    )
    @app_commands.describe(channel="The channel to send welcome messages to. Leave empty to reset.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer()

        if channel is None:
            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(
                        "DELETE FROM welcome_channels WHERE guild_id = ?",
                        (str(interaction.guild.id),),
                    )
                    await conn.commit()
            except Exception:
                log.exception("failed to reset welcome channel in guild %s", interaction.guild.id)
                await interaction.followup.send(view=ExceptionUI())
                return
            view = PositiveUI(title="Welcome Channel Reset", subtitle="**Welcome channel settings have been reset.**")
            await interaction.followup.send(view=view)
            return

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    """
                    INSERT INTO welcome_channels (guild_id, channel_id)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
                    """,
                    (str(interaction.guild.id), str(channel.id)),
                )
                await conn.commit()
        except Exception:
            log.exception("failed to set welcome channel in guild %s", interaction.guild.id)
            await interaction.followup.send(view=ExceptionUI())
            return
        view = PositiveUI(title="Welcome Channel Set", subtitle=f"**Welcome channel set to {channel.mention}.**")
        await interaction.followup.send(view=view)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        config = await self.get_welcome_config(member.guild.id)
        if config is None or config["channel"] is None:
            return

        view = self._build_welcome_ui(config, member)

        try:
            await config["channel"].send(view=view)
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
