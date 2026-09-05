import logging

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from globals import ERROR_MESSAGE, PRIMARY, SECONDARY, TERTIARY
from ui import (
    ErrorUI,
    InfoUI,
    LargeSeparator,
)

log = logging.getLogger(__name__)
HOLOGRAPHIC_VALUES = (11127295, 16759788, 16761760)


# gradient role func
def _describe_style(role: discord.Role) -> str:
    if (
        role.colour.value,
        role.secondary_colour.value if role.secondary_colour else None,
        role.tertiary_colour.value if role.tertiary_colour else None,
    ) == HOLOGRAPHIC_VALUES:
        return "Holographic"
    if role.secondary_colour is not None:
        return "Gradient"
    return "Solid"


@app_commands.guild_only
class AuditCog(
    commands.GroupCog,
    name="audit",
    description="Audit logging configuration and handling.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = "data/logging.db"

    def clean_and_truncate(self, text: str, length: int = 500) -> str:
        return discord.utils.escape_markdown(
            (text)[: length - 3] + "..." if len(text) > length else text,
        )

    def format_attachments(self, attachments: list[discord.Attachment]) -> str:
        return "\n".join(
            f"- {discord.utils.escape_markdown(f'{attachment.filename} | {attachment.url}')}"
            for attachment in attachments
        )

    def channel_display(
        self,
        channel: discord.abc.Messageable | discord.abc.GuildChannel,
    ) -> str:
        if isinstance(channel, discord.Thread):
            parent = channel.parent

            if isinstance(parent, discord.ForumChannel):
                return f"{parent.mention} -> {channel.mention} | {parent.id} -> {channel.id}"
            if parent is not None:
                return f"{parent.mention} -> {channel.mention} | {parent.id} -> {channel.id}"

            return channel.mention

        if isinstance(channel, discord.TextChannel):
            return f"{channel.mention} | {channel.id}"

        return "Unknown Channel"

    async def cog_load(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS log_channels (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL
                )
            """)
            await conn.commit()

    @app_commands.command(
        name="channel", description="Set the channel for server logs.",
    )
    @app_commands.describe(channel="The channel to send logs to.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
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
                    INSERT OR REPLACE INTO log_channels (guild_id, channel_id)
                    VALUES (?, ?)
                    """,
                    (str(interaction.guild.id), str(channel.id)),
                )
                await conn.commit()
        except Exception:
            log.exception(
                "Failed to set log channel for guild %s.",
                interaction.guild.id,
            )
            view = ErrorUI(message="**Something went wrong saving that.**")
            await interaction.followup.send(view=view)
            return

        view = InfoUI(title="# Logging", subtitle=f"**Logging channel set to {channel.mention}.**")
        await interaction.followup.send(view=view)

    @channel.error
    async def channel_error(
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

    async def get_log_channel(self, guild_id: int) -> discord.abc.GuildChannel | discord.Thread | discord.abc.PrivateChannel | None:
        try:
            async with (
                aiosqlite.connect(self.db_path) as conn,
                conn.execute(
                    "SELECT channel_id FROM log_channels WHERE guild_id = ?",
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
        name="reset", description="reset the channel set for server logs.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def reset(self, interaction: discord.interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer()
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "DELETE FROM log_channels WHERE guild_id = ?",
                    (str(interaction.guild.id),),
                )
                await conn.commit()
                deleted = cursor.rowcount > 0
        except Exception:
            log.exception(
                "Failed to reset log channel for guild %s.",
                interaction.guild.id,
            )
            view = ErrorUI(message="**Something went wrong resetting this.**")
            await interaction.followup.send(view=view)
            return
        if not deleted:
            view = InfoUI(title="# Logging", subtitle="**No log channel was set.**")
        else:
            view = InfoUI(title="# Logging", subtitle="**Log channel has been reset.**")
        await interaction.followup.send(view=view)

    @reset.error
    async def reset_error(
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


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        log_channel = await self.get_log_channel(member.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.Section(
                f"**{member} joined.**\n**Member #{member.guild.member_count}.**",
                accessory=discord.ui.Thumbnail(media=member.display_avatar.url),
            ),
            accent_color=discord.Color.from_str(SECONDARY),
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

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        log_channel = await self.get_log_channel(member.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.Section(
                f"**{member} left.**\n**Member #{member.guild.member_count}.**",
                accessory=discord.ui.Thumbnail(media=member.display_avatar.url),
            ),
            accent_color=discord.Color.from_str(TERTIARY),
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

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        log_channel = await self.get_log_channel(before.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        changes = []

        if before.nick != after.nick:
            old_nick = before.nick or before.name
            new_nick = after.nick or after.name
            changes.append(f"**Nickname:** {old_nick} | {new_nick}")

        if before.roles != after.roles:
            before_roles = set(before.roles)
            after_roles = set(after.roles)
            added = after_roles - before_roles
            removed = before_roles - after_roles
            if added:
                changes.append(
                    f"**Roles added:** {', '.join(r.mention for r in added)}",
                )
            if removed:
                changes.append(
                    f"**Roles removed:** {', '.join(r.mention for r in removed)}",
                )

        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until is not None:
                changes.append(
                    f"**Timed out until:** {discord.utils.format_dt(after.timed_out_until, style='f')}",
                )
            else:
                changes.append("**Timeout removed.**")

        if not changes:
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Member Updated | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.Section(
                f"**Member:** {after.mention} | {after.id}",
                accessory=discord.ui.Thumbnail(media=after.display_avatar.url),
            ),
            accent_color=discord.Color.from_str(PRIMARY),
        )

        changes_text = "\n".join(changes)
        container.add_item(LargeSeparator())
        container.add_item(
            discord.ui.TextDisplay(
                f"### Changes\n{changes_text}",
            ),
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

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        if (
            before.name == after.name
            and before.global_name == after.global_name
            and before.avatar == after.avatar
        ):
            return

        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is None:
                continue
            log_channel = await self.get_log_channel(guild.id)
            if log_channel is None or not isinstance(log_channel, discord.TextChannel):
                continue

            changes = []
            if before.name != after.name:
                changes.append(f"**Username:** {before.name} | {after.name}")
            if before.global_name != after.global_name:
                changes.append(
                    f"**Display name:** {before.global_name or before.name} | {after.global_name or after.name}",
                )
            if before.avatar != after.avatar:
                changes.append("**Avatar changed.**")

            if not changes:
                continue

            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"# Profile Updated | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
                ),
                discord.ui.Section(
                    f"**User:** {after.mention} | {after.id}",
                    accessory=discord.ui.Thumbnail(media=after.display_avatar.url),
                ),
                accent_color=discord.Color.from_str(PRIMARY),
            )

            changes_text = "\n".join(changes)
            container.add_item(LargeSeparator())
            container.add_item(
                discord.ui.TextDisplay(
                    f"### Changes\n{changes_text}",
                ),
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

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message,
    ) -> None:
        if before.author.bot or before.content == after.content:
            return

        if not before.guild:
            return

        log_channel = await self.get_log_channel(before.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Message Edited | {discord.utils.format_dt(after.edited_at or discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.Section(
                f"**Author:** {before.author.mention} | {before.author.id}\n"
                f"**Channel:** {self.channel_display(after.channel)}",
                accessory=discord.ui.Button(
                    label="Jump to Message",
                    style=discord.ButtonStyle.link,
                    url=after.jump_url,
                ),
            ),
            accent_color=discord.Color.from_str(PRIMARY),
        )

        if after.attachments:
            container.add_item(LargeSeparator())
            container.add_item(
                discord.ui.TextDisplay(
                    f"### Attachments\n{self.format_attachments(after.attachments)}",
                ),
            )

        container.add_item(LargeSeparator())
        container.add_item(
            discord.ui.TextDisplay(
                "### Before\n"
                f"{self.clean_and_truncate(before.content) or '[No content, likely an embed or attachment.]'}",
            ),
        )
        container.add_item(
            discord.ui.TextDisplay(
                "### After\n"
                f"{self.clean_and_truncate(after.content) or '[No content, likely an embed or attachment.]'}",
            ),
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

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message) -> None:
        if msg.author.bot or not msg.guild:
            return
        log_channel = await self.get_log_channel(msg.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Message Deleted | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.TextDisplay(
                f"**Author:** {msg.author.mention} | {msg.author.id}\n"
                f"**Channel:** {self.channel_display(msg.channel)}",
            ),
            accent_color=discord.Color.from_str(TERTIARY),
        )

        if msg.attachments:
            container.add_item(LargeSeparator())
            container.add_item(
                discord.ui.TextDisplay(
                    f"### Attachments\n{self.format_attachments(msg.attachments)}",
                ),
            )

        container.add_item(LargeSeparator())
        container.add_item(
            discord.ui.TextDisplay(
                "### Content\n"
                f"{self.clean_and_truncate((msg.content) or '[No content, likely an embed or attachment.]')}",
            ),
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

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        log_channel = await self.get_log_channel(member.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        if before.channel is None and after.channel is not None:
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"# Voice Channel Joined | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
                ),
                discord.ui.Section(
                    f"**Member:** {member.mention} | {member.id}\n**Channel:** {after.channel.mention}",
                    accessory=discord.ui.Thumbnail(media=member.display_avatar.url),
                ),
                accent_color=discord.Color.from_str(SECONDARY),
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
            return

        if before.channel is not None and after.channel is None:
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"# Voice Channel Left | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
                ),
                discord.ui.Section(
                    f"**Member:** {member.mention} | {member.id}\n**Channel:** {before.channel.mention}",
                    accessory=discord.ui.Thumbnail(media=member.display_avatar.url),
                ),
                accent_color=discord.Color.from_str(TERTIARY),
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
            return

        if (
            before.channel is not None
            and after.channel is not None
            and before.channel.id != after.channel.id
        ):
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"# Voice Channel Moved | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
                ),
                discord.ui.Section(
                    f"**Member:** {member.mention} | {member.id}\n**Moved:** {before.channel.mention} -> {after.channel.mention}",
                    accessory=discord.ui.Thumbnail(media=member.display_avatar.url),
                ),
                accent_color=discord.Color.from_str(PRIMARY),
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

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        log_channel = await self.get_log_channel(channel.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Channel Created | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.TextDisplay(
                f"**Channel:** {channel.mention} | {channel.id}\n**Type:** {channel.type}",
            ),
            accent_color=discord.Color.from_str(SECONDARY),
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

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        log_channel = await self.get_log_channel(channel.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Channel Deleted | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.TextDisplay(
                f"**Name:** #{channel.name} | {channel.id}\n**Type:** {channel.type}",
            ),
            accent_color=discord.Color.from_str(TERTIARY),
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

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        log_channel = await self.get_log_channel(before.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} | {after.name}")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append("**Topic updated.**")

        if not changes:
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Channel Updated | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.TextDisplay(f"**Channel:** {after.mention} | {after.id}"),
            accent_color=discord.Color.from_str(PRIMARY),
        )

        changes_text = "\n".join(changes)
        container.add_item(LargeSeparator())
        container.add_item(
            discord.ui.TextDisplay(
                f"### Changes\n{changes_text}",
            ),
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

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        log_channel = await self.get_log_channel(role.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Role Created | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.TextDisplay(f"**Role:** {role.mention} | {role.id}"),
            accent_color=discord.Color.from_str(SECONDARY),
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

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        log_channel = await self.get_log_channel(role.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Role Deleted | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.TextDisplay(f"**Name:** {role.name} | {role.id}"),
            accent_color=discord.Color.from_str(TERTIARY),
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

    @commands.Cog.listener()
    async def on_guild_role_update(
        self,
        before: discord.Role,
        after: discord.Role,
    ) -> None:
        log_channel = await self.get_log_channel(before.guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** **{before.name}** | **{after.name}**")

        colour_changed = (
            before.colour != after.colour
            or before.secondary_colour != after.secondary_colour
            or before.tertiary_colour != after.tertiary_colour
        )
        if colour_changed:

            def fmt(role: discord.Role) -> str:
                parts = [str(role.colour)]
                if role.secondary_colour:
                    parts.append(str(role.secondary_colour))
                if role.tertiary_colour:
                    parts.append(str(role.tertiary_colour))
                return " / ".join(parts)

            b_style = _describe_style(before)
            a_style = _describe_style(after)
            changes.append(
                f"**Colours:** **{fmt(before)}** ({b_style}) | **{fmt(after)}** ({a_style})",
            )

        if before.permissions != after.permissions:
            changes.append("**Permissions updated.**")

        if not changes:
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Role Updated | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.TextDisplay(f"**Role:** {after.mention} | {after.id}"),
            accent_color=discord.Color.from_str(PRIMARY),
        )
        changes_text = "\n".join(changes)
        container.add_item(LargeSeparator())
        container.add_item(discord.ui.TextDisplay(f"### Changes\n{changes_text}"))

        view = discord.ui.LayoutView()
        view.add_item(container)
        try:
            await log_channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild: discord.Guild,
        user: discord.User | discord.Member,
    ) -> None:
        log_channel = await self.get_log_channel(guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Member Banned | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.Section(
                f"**User:** {user} | {user.id}",
                accessory=discord.ui.Thumbnail(media=user.display_avatar.url),
            ),
            accent_color=discord.Color.from_str(TERTIARY),
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

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        log_channel = await self.get_log_channel(guild.id)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# Member Unbanned | {discord.utils.format_dt(discord.utils.utcnow(), style='F')}",
            ),
            discord.ui.Section(
                f"**User:** {user} | {user.id}",
                accessory=discord.ui.Thumbnail(media=user.display_avatar.url),
            ),
            accent_color=discord.Color.from_str(SECONDARY),
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AuditCog(bot))
