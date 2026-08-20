import logging

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from ui import ErrorUI, ExceptionUI, PositiveUI, ResponseUI

log = logging.getLogger(__name__)


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
            msg = ERROR_MESSAGE

        error_ui = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=error_ui)
        else:
            await interaction.response.send_message(view=error_ui, ephemeral=False)

    @app_commands.command(
        name="channel",
        description="Set the channel for member join events.",
    )
    @app_commands.describe(channel="The channel to send welcome messages to.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO welcome_channels (guild_id, channel_id)
                    VALUES (?, ?)
                    """,
                    (str(interaction.guild.id), str(channel.id)),
                )
                await conn.commit()
        except Exception:
            log.exception("failed to set welcome channel", interaction.guild.id)
            await interaction.followup.send(view=ExceptionUI())
            return
        view = PositiveUI(title="Welcome Channel Set", subtitle=f"**Welcome channel set to {channel.mention}.**")
        await interaction.followup.send(view=view)

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

    @app_commands.command(
        name="config",
        description="Set the welcome message and optional attachments or buttons.",
    )
    @app_commands.describe(
        text="The welcome message to send (use {member} to mention the new member).",
        attachment_url="Optional image URL to attach to the welcome message.",
        b1_url="Optional first button URL.",
        b1_label="Label for the first button (defaults to 'Link').",
        b2_url="Optional second button URL.",
        b2_label="Label for the second button (defaults to 'Link 2').",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(
        self,
        interaction: discord.Interaction,
        text: str,
        attachment_url: str | None = None,
        b1_url: str | None = None,
        b1_label: str | None = None,
        b2_url: str | None = None,
        b2_label: str | None = None,
    ) -> None:
        if not interaction.guild:
            return

        await interaction.response.defer()

        for url in (attachment_url, b1_url, b2_url):
            if url and not url.startswith(("http://", "https://")):
                await interaction.edit_original_response(
                    view=ErrorUI("All URLs must be valid HTTP or HTTPS links."),
                )
                return

        try:
            # Make sure the table exists even if cog_load did not run.
            await self._ensure_db()
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
            log.exception("Database error")
            await interaction.edit_original_response(view=ExceptionUI())
            return

        # Config requires a channel, but the database may legitimately have no row yet.
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
                        text,
                        attachment_url,
                        b1_url,
                        b1_label or "Link",
                        b2_url,
                        b2_label or "Link 2",
                    ),
                )
                await conn.commit()
        except Exception:
            log.exception("Database error")
            await interaction.followup.send(view=ExceptionUI())
            return

        view = PositiveUI(title="Updated", subtitle="**Welcome message updated.**")
        await interaction.edit_original_response(view=view)

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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        config = await self.get_welcome_config(member.guild.id)
        if config is None or config["channel"] is None:
            return

        text = config["message"] or f"Welcome, {member.mention}!"
        text = text.replace("{member}", member.mention)

        view = ResponseUI(text)

        if config["attachment_url"]:
            view.container.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=config["attachment_url"]),
                ),
            )

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

        try:
            await config["channel"].send(view=view)
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
