from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from globals import CLICK, ERROR_MESSAGE, IMAGE, TEXT
from ui import ErrorUI, ExceptionUI, GalleryWithItem, PositiveUI, ResponseUI

log = logging.getLogger(__name__)


imagedir = "data/welcome_images"

_UPDATABLE_FIELDS = {"message", "attachment_path", "b1_url", "b1_label", "b2_url", "b2_label"}


async def safe_finish(interaction: discord.Interaction, view: discord.ui.LayoutView, file: discord.File | None = None) -> None:
    try:
        if file is not None:
            await interaction.edit_original_response(view=view, attachments=[file])
        else:
            await interaction.edit_original_response(view=view)
    except discord.NotFound:
        log.warning("Original interaction response missing; falling back to followup.send")
        try:
            if file is not None:
                await interaction.followup.send(view=view, file=file)
            else:
                await interaction.followup.send(view=view)
        except (discord.NotFound, discord.HTTPException):
            log.exception("Followup send also failed")


def _delete_stored_image(guild_id: int) -> None:
    for path in Path(imagedir).glob(f"{guild_id}.*"):
        try:
            path.unlink()
        except OSError:
            log.exception("Failed to delete a stale welcome image at %s", path)


async def _save_uploaded_image(guild_id: int, uploaded_file: discord.Attachment) -> str:
    await asyncio.to_thread(Path(imagedir).mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(_delete_stored_image, guild_id)
    ext = Path(uploaded_file.filename).suffix or ".png"
    path = Path(imagedir) / f"{guild_id}{ext}"
    data = await uploaded_file.read()
    await asyncio.to_thread(path.write_bytes, data)
    return str(path)


def _load_attachment_file(attachment_path: str | None) -> discord.File | None:
    if not attachment_path:
        return None
    path = Path(attachment_path)
    if not path.is_file():
        return None
    return discord.File(path, filename=path.name)


def _has_manage_guild(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.manage_guild)


class MediaConfigModal(discord.ui.Modal, title="Welcome Media"):
    def __init__(
        self,
        cog: WelcomeCog,
        guild_id: int,
        message: discord.Message,
        current_config: dict | None,
    ) -> None:
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.message = message
        self.current_config = current_config

        self._attachment_image = discord.ui.FileUpload(required=False)
        self.attachment_image = discord.ui.Label(
            text="Welcome Image",
            description="Optional image to attach to welcome message. Leave empty to keep current image."[:100],
            component=self._attachment_image,
        )
        self.add_item(self.attachment_image)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        attachment_path = self.current_config.get("attachment_path") if self.current_config else None
        if self._attachment_image.values:
            uploaded_file = self._attachment_image.values[0]
            try:
                attachment_path = await _save_uploaded_image(self.guild_id, uploaded_file)
            except (discord.HTTPException, OSError):
                log.exception("Failed to download/save uploaded welcome image")
                await safe_finish(interaction, ErrorUI("Couldn't save that image, please try again."))
                return

        try:
            updated = await self.cog.update_config_fields(self.guild_id, attachment_path=attachment_path)
        except Exception:
            log.exception("Database error while updating welcome media")
            await safe_finish(interaction, ExceptionUI())
            return

        if not updated:
            await safe_finish(
                interaction,
                ErrorUI("**Set a welcome channel first using `/welcome channel`.**"),
            )
            return

        await self.cog.refresh_preview(self.message, self.guild_id, interaction.user)


class TextConfigModal(discord.ui.Modal, title="Welcome Text"):
    def __init__(
        self,
        cog: WelcomeCog,
        guild_id: int,
        message: discord.Message,
        current_config: dict | None,
    ) -> None:
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.message = message

        current_text = (current_config.get("message") if current_config else None) or ""

        self._text = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            default=current_text,
            placeholder="Welcome, {member}! We're at {member_count} members now.",
            required=False,
        )
        self.text = discord.ui.Label(
            text="Welcome Message",
            description="Use {member} to mention member and {member_count} for count. Empty for default."[:100],
            component=self._text,
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        text_value = str(self._text.value).strip() or None

        try:
            updated = await self.cog.update_config_fields(self.guild_id, message=text_value)
        except Exception:
            log.exception("Database error while updating welcome text")
            await safe_finish(interaction, ExceptionUI())
            return

        if not updated:
            await safe_finish(
                interaction,
                ErrorUI("**Set a welcome channel first using `/welcome channel`.**"),
            )
            return

        await self.cog.refresh_preview(self.message, self.guild_id, interaction.user)


class ButtonsConfigModal(discord.ui.Modal, title="Welcome Buttons"):
    def __init__(
        self,
        cog: WelcomeCog,
        guild_id: int,
        message: discord.Message,
        current_config: dict | None,
    ) -> None:
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.message = message

        b1_url_def = (current_config.get("b1_url") if current_config else None) or ""
        b1_label_def = (current_config.get("b1_label") if current_config else None) or ""
        b2_url_def = (current_config.get("b2_url") if current_config else None) or ""
        b2_label_def = (current_config.get("b2_label") if current_config else None) or ""

        self._button1_url = discord.ui.TextInput(default=b1_url_def, required=False)
        self.button1_url = discord.ui.Label(
            text="Button 1 URL",
            description="Optional first button URL. Leave empty to remove button 1."[:100],
            component=self._button1_url,
        )
        self._button1_text = discord.ui.TextInput(
            default=b1_label_def,
            placeholder="Defaults to 'Link 1'.",
            required=False,
        )
        self.button1_text = discord.ui.Label(
            text="Button 1 Label",
            description="Label for the first button."[:100],
            component=self._button1_text,
        )

        self._button2_url = discord.ui.TextInput(default=b2_url_def, required=False)
        self.button2_url = discord.ui.Label(
            text="Button 2 URL",
            description="Optional second button URL. Leave empty to remove button 2."[:100],
            component=self._button2_url,
        )
        self._button2_text = discord.ui.TextInput(
            default=b2_label_def,
            placeholder="Defaults to 'Link 2'.",
            required=False,
        )
        self.button2_text = discord.ui.Label(
            text="Button 2 Label",
            description="Label for the second button."[:100],
            component=self._button2_text,
        )

        for item in [
            self.button1_url,
            self.button1_text,
            self.button2_url,
            self.button2_text,
        ]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        b1_url = str(self._button1_url.value).strip() or None
        b1_label = str(self._button1_text.value).strip() or "Link 1"
        b2_url = str(self._button2_url.value).strip() or None
        b2_label = str(self._button2_text.value).strip() or "Link 2"

        for url in (b1_url, b2_url):
            if url and not url.startswith(("http://", "https://")):
                await safe_finish(
                    interaction,
                    ErrorUI("All button URLs must be valid HTTP or HTTPS links."),
                )
                return

        try:
            updated = await self.cog.update_config_fields(
                self.guild_id,
                b1_url=b1_url,
                b1_label=b1_label,
                b2_url=b2_url,
                b2_label=b2_label,
            )
        except Exception:
            log.exception("Database error while updating welcome buttons")
            await safe_finish(interaction, ExceptionUI())
            return

        if not updated:
            await safe_finish(
                interaction,
                ErrorUI("**Set a welcome channel first using `/welcome channel`.**"),
            )
            return

        await self.cog.refresh_preview(self.message, self.guild_id, interaction.user)


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
                    attachment_path TEXT,
                    b1_url TEXT,
                    b1_label TEXT,
                    b2_url TEXT,
                    b2_label TEXT
                )
            """)
            await conn.commit()

            async with conn.execute("PRAGMA table_info(welcome_channels)") as cursor:
                columns = {row[1] async for row in cursor}

            if "attachment_url" in columns and "attachment_path" not in columns:
                await conn.execute(
                    "ALTER TABLE welcome_channels RENAME COLUMN attachment_url TO attachment_path",
                )
                await conn.execute(
                    "UPDATE welcome_channels SET attachment_path = NULL WHERE attachment_path IS NOT NULL",
                )
                await conn.commit()
                log.info("Migrated welcome_channels.attachment_url -> attachment_path")

    async def cog_load(self) -> None:
        await self._ensure_db()

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
            await safe_finish(interaction, error_ui)
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
                    "SELECT channel_id, message, attachment_path, b1_url, b1_label, b2_url, b2_label "
                    "FROM welcome_channels WHERE guild_id = ?",
                    (str(guild_id),),
                ) as cursor,
            ):
                row = await cursor.fetchone()
        except Exception:
            return None

        if row is None:
            return None

        channel_id, message, attachment_path, b1_url, b1_label, b2_url, b2_label = row
        return {
            "channel": self.bot.get_channel(int(channel_id)) if channel_id else None,
            "message": message,
            "attachment_path": attachment_path,
            "b1_url": b1_url,
            "b1_label": b1_label,
            "b2_url": b2_url,
            "b2_label": b2_label,
        }

    async def update_config_fields(self, guild_id: int, **fields: str | None) -> bool:
        unknown = set(fields) - _UPDATABLE_FIELDS
        if unknown:
            msg = f"not working, can't update unknown welcome_channels columns: {unknown}"
            raise ValueError(msg)

        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT channel_id FROM welcome_channels WHERE guild_id = ?",
                (str(guild_id),),
            ) as cursor:
                row = await cursor.fetchone()

            if row is None:
                return False

            set_clause = ", ".join(f"{column} = ?" for column in fields)
            values = [*fields.values(), str(guild_id)]
            await conn.execute(
                f"UPDATE welcome_channels SET {set_clause} WHERE guild_id = ?",  # ruff: ignore[hardcoded-sql-expression]
                values,
            )
            await conn.commit()

        return True

    def _build_welcome_ui(
        self,
        config: dict[str, str],
        target_member: discord.Member | discord.User,
    ) -> tuple[ResponseUI, discord.File | None]:
        text = config["message"] or f"Welcome, {target_member.mention}!"
        text = text.replace("{member}", target_member.mention)

        guild = getattr(target_member, "guild", None)
        if guild is not None:
            text = text.replace("{member_count}", str(guild.member_count))

        view = ResponseUI(text)

        file = _load_attachment_file(config.get("attachment_path"))
        if file is not None:
            view.container.add_item(GalleryWithItem(f"attachment://{file.filename}"))

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

        return view, file

    def _build_config_select(self, guild_id: int) -> discord.ui.Select:
        select = discord.ui.Select(
            placeholder="Customize the welcome message...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Media",
                    value="media",
                    description="Set or replace the welcome image."[:100],
                    emoji=f"{IMAGE}",
                ),
                discord.SelectOption(
                    label="Text",
                    value="text",
                    description="Edit the welcome message text."[:100],
                    emoji=f"{TEXT}",
                ),
                discord.SelectOption(
                    label="Buttons",
                    value="buttons",
                    description="Configure button 1 and button 2."[:100],
                    emoji=f"{CLICK}",
                ),
            ],
        )

        async def _callback(interaction: discord.Interaction) -> None:
            if not _has_manage_guild(interaction):
                await interaction.response.send_message(
                    view=ErrorUI("**You do not have permission to do this.**"),
                    ephemeral=True,
                )
                return

            current_config = await self.get_welcome_config(guild_id)
            message = interaction.message
            value = select.values[0]

            if value == "media":
                modal = MediaConfigModal(self, guild_id, message, current_config)
            elif value == "text":
                modal = TextConfigModal(self, guild_id, message, current_config)
            else:
                modal = ButtonsConfigModal(self, guild_id, message, current_config)

            await interaction.response.send_modal(modal)

        select.callback = _callback
        return select

    def _build_config_preview(
        self,
        config: dict[str, str],
        guild_id: int,
        target_member: discord.Member | discord.User,
    ) -> tuple[ResponseUI, discord.File | None]:
        view, file = self._build_welcome_ui(config, target_member)
        view.container.add_item(discord.ui.ActionRow(self._build_config_select(guild_id)))
        return view, file

    async def refresh_preview(
        self,
        message: discord.Message,
        guild_id: int,
        target_member: discord.Member | discord.User,
    ) -> None:
        current_config = await self.get_welcome_config(guild_id)
        if current_config is None:
            return

        view, file = self._build_config_preview(current_config, guild_id, target_member)
        try:
            if file is not None:
                await message.edit(view=view, attachments=[file])
            else:
                await message.edit(view=view)
        except (discord.NotFound, discord.HTTPException):
            log.exception("Failed to refresh welcome config preview")

    @app_commands.command(
        name="config",
        description="Preview and customize the welcome message.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        await self._ensure_db()
        current_config = await self.get_welcome_config(interaction.guild.id)

        if current_config is None or current_config["channel"] is None:
            await interaction.response.send_message(
                view=ErrorUI("**Set a welcome channel first using /welcome channel.**"),
                ephemeral=False,
            )
            return

        await interaction.response.defer()

        view, file = self._build_config_preview(current_config, interaction.guild.id, interaction.user)
        if file is not None:
            await interaction.edit_original_response(view=view, attachments=[file])
        else:
            await interaction.edit_original_response(view=view)

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
            await safe_finish(
                interaction,
                ErrorUI("**No welcome configuration found. Use /welcome channel and /welcome config first.**"),
            )
            return

        view, file = self._build_welcome_ui(config, interaction.user)
        await safe_finish(interaction, view, file=file)

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
            _delete_stored_image(interaction.guild.id)
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

        view, file = self._build_welcome_ui(config, member)

        try:
            if file is not None:
                await config["channel"].send(view=view, file=file)
            else:
                await config["channel"].send(view=view)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    "DELETE FROM welcome_channels WHERE guild_id = ?",
                    (str(guild.id),),
                )
                await conn.commit()
        except Exception:
            log.exception("failed to clean up welcome config for departed guild %s", guild.id)

        _delete_stored_image(guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
