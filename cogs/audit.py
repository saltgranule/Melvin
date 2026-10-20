import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import DATA_DIR, PRIMARY, SECONDARY, TERTIARY
from module_registry import Module, Setting
from ui import LargeSeparator, open_config

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

MODULE = Module(
    "audit",
    "Audit Logs",
    "Logs member, message, voice, channel, and role changes.",
    settings=(
        Setting(
            "log_channel",
            "Audit channel",
            "Used for any event without its own channel below. Nothing is logged until one is set.",
            "channel",
        ),
        Setting(
            "message_channel",
            "Message channel",
            "Message edits and deletes. Uses the audit channel if not set.",
            "channel",
        ),
        Setting(
            "member_channel",
            "Member channel",
            "Joins, leaves, bans, and member or profile changes. Uses the audit channel if not set.",
            "channel",
        ),
        Setting(
            "server_channel",
            "Server channel",
            "Server, channel, and role changes. Uses the audit channel if not set.",
            "channel",
        ),
        Setting(
            "other_channel",
            "Other channel",
            "Voice channel activity and anything else. Uses the audit channel if not set.",
            "channel",
        ),
    ),
)

LOG_CHANNEL_SETTINGS = {
    "message": "message_channel",
    "member": "member_channel",
    "server": "server_channel",
    "other": "other_channel",
}

log = logging.getLogger(__name__)

HOLOGRAPHIC_VALUES = (11127295, 16759788, 16761760)
NO_CONTENT = "[No content, likely an embed or attachment.]"

UPDATED = discord.Color.from_str(PRIMARY)
ADDED = discord.Color.from_str(SECONDARY)
REMOVED = discord.Color.from_str(TERTIARY)


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


def _role_colours(role: discord.Role) -> str:
    colours = (role.colour, role.secondary_colour, role.tertiary_colour)
    return " / ".join(str(colour) for colour in colours if colour)


def _clean(text: str, length: int = 500) -> str:
    return discord.utils.escape_markdown(
        text[: length - 3] + "..." if len(text) > length else text,
    )


def _attachments(attachments: list[discord.Attachment]) -> str:
    return "### Attachments\n" + "\n".join(
        f"- {discord.utils.escape_markdown(f'{attachment.filename} | {attachment.url}')}"
        for attachment in attachments
    )


def _changes(changes: list[str]) -> list[list[str]]:
    return [["### Changes\n" + "\n".join(changes)]]


def _channel_display(
    channel: discord.abc.Messageable | discord.abc.GuildChannel,
) -> str:
    if isinstance(channel, discord.Thread):
        parent = channel.parent
        if parent is None:
            return channel.mention
        return f"{parent.mention} -> {channel.mention} | {parent.id} -> {channel.id}"
    if isinstance(channel, discord.abc.GuildChannel):
        return f"{channel.mention} | {channel.id}"
    return "Unknown Channel"


def _thumbnail(user: discord.abc.User) -> discord.ui.Thumbnail:
    return discord.ui.Thumbnail(media=user.display_avatar.url)


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class AuditCog(
    commands.GroupCog,
    name="audit",
    description="Audit logging configuration and handling.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = DATA_DIR / "logging.db"

    async def cog_load(self) -> None:
        await module_config.migrate_legacy(
            self.db_path,
            "log_channels",
            "audit",
            lambda row: (int(row[0]), {"log_channel": row[1]}),
        )

    @app_commands.command(
        name="config",
        description="Change audit log settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "audit")

    async def get_log_channel(
        self,
        guild_id: int,
        category: str,
    ) -> discord.TextChannel | None:
        if not await module_settings.is_enabled(guild_id, "audit"):
            return None
        values = await module_config.get_all(guild_id, "audit")
        channel_id = values[LOG_CHANNEL_SETTINGS[category]] or values["log_channel"]
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _log(
        self,
        guild_id: int,
        color: discord.Color,
        title: str | None,
        info: str,
        *,
        category: str,
        accessory: discord.ui.Item | None = None,
        sections: Sequence[Sequence[str]] = (),
        when: datetime | None = None,
    ) -> None:
        channel = await self.get_log_channel(guild_id, category)
        if channel is None:
            return

        items: list[discord.ui.Item] = []
        if title is not None:
            stamp = discord.utils.format_dt(when or discord.utils.utcnow(), style="F")
            items.append(discord.ui.TextDisplay(f"# {title} | {stamp}"))
        items.append(
            discord.ui.Section(info, accessory=accessory)
            if accessory is not None
            else discord.ui.TextDisplay(info),
        )
        for section in sections:
            items.append(LargeSeparator())
            items.extend(discord.ui.TextDisplay(text) for text in section)

        view = discord.ui.LayoutView()
        view.add_item(discord.ui.Container(*items, accent_color=color))
        try:
            await channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._log(
            member.guild.id,
            ADDED,
            None,
            f"**{member} joined.**\n**Member #{member.guild.member_count}.**",
            accessory=_thumbnail(member),
            category="member",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self._log(
            member.guild.id,
            REMOVED,
            None,
            f"**{member} left.**\n**Member #{member.guild.member_count}.**",
            accessory=_thumbnail(member),
            category="member",
        )

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        changes = []
        if before.nick != after.nick:
            changes.append(
                f"**Nickname:** {before.nick or before.name} | {after.nick or after.name}",
            )

        if before.roles != after.roles:
            before_roles, after_roles = set(before.roles), set(after.roles)
            if added := after_roles - before_roles:
                changes.append(
                    f"**Roles added:** {', '.join(r.mention for r in added)}",
                )
            if removed := before_roles - after_roles:
                changes.append(
                    f"**Roles removed:** {', '.join(r.mention for r in removed)}",
                )

        if before.timed_out_until != after.timed_out_until:
            changes.append(
                f"**Timed out until:** {discord.utils.format_dt(after.timed_out_until, style='f')}"
                if after.timed_out_until is not None
                else "**Timeout removed.**",
            )

        if changes:
            await self._log(
                after.guild.id,
                UPDATED,
                "Member Updated",
                f"**Member:** {after.mention} | {after.id}",
                accessory=_thumbnail(after),
                sections=_changes(changes),
                category="member",
            )

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
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
            return

        for guild in after.mutual_guilds:
            await self._log(
                guild.id,
                UPDATED,
                "Profile Updated",
                f"**User:** {after.mention} | {after.id}",
                accessory=_thumbnail(after),
                sections=_changes(changes),
                category="member",
            )

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message,
    ) -> None:
        if before.author.bot or not before.guild or before.content == after.content:
            return

        sections = [[_attachments(after.attachments)]] if after.attachments else []
        sections.append(
            [
                f"### Before\n{_clean(before.content) or NO_CONTENT}",
                f"### After\n{_clean(after.content) or NO_CONTENT}",
            ],
        )
        await self._log(
            before.guild.id,
            UPDATED,
            "Message Edited",
            f"**Author:** {before.author.mention} | {before.author.id}\n"
            f"**Channel:** {_channel_display(after.channel)}",
            accessory=discord.ui.Button(
                label="Jump to Message",
                style=discord.ButtonStyle.link,
                url=after.jump_url,
            ),
            sections=sections,
            when=after.edited_at,
            category="message",
        )

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message) -> None:
        if msg.author.bot or not msg.guild:
            return

        sections = [[_attachments(msg.attachments)]] if msg.attachments else []
        sections.append([f"### Content\n{_clean(msg.content or NO_CONTENT)}"])
        await self._log(
            msg.guild.id,
            REMOVED,
            "Message Deleted",
            f"**Author:** {msg.author.mention} | {msg.author.id}\n"
            f"**Channel:** {_channel_display(msg.channel)}",
            sections=sections,
            category="message",
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        old, new = before.channel, after.channel
        if old == new:
            return

        if old is None:
            color, title, line = (
                ADDED,
                "Voice Channel Joined",
                f"**Channel:** {new.mention}",
            )
        elif new is None:
            color, title, line = (
                REMOVED,
                "Voice Channel Left",
                f"**Channel:** {old.mention}",
            )
        else:
            color, title, line = (
                UPDATED,
                "Voice Channel Moved",
                f"**Moved:** {old.mention} -> {new.mention}",
            )

        await self._log(
            member.guild.id,
            color,
            title,
            f"**Member:** {member.mention} | {member.id}\n{line}",
            accessory=_thumbnail(member),
            category="other",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._log(
            channel.guild.id,
            ADDED,
            "Channel Created",
            f"**Channel:** {channel.mention} | {channel.id}\n**Type:** {channel.type}",
            category="server",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._log(
            channel.guild.id,
            REMOVED,
            "Channel Deleted",
            f"**Name:** #{channel.name} | {channel.id}\n**Type:** {channel.type}",
            category="server",
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} | {after.name}")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append("**Topic updated.**")

        if changes:
            await self._log(
                after.guild.id,
                UPDATED,
                "Channel Updated",
                f"**Channel:** {after.mention} | {after.id}",
                sections=_changes(changes),
                category="server",
            )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._log(
            role.guild.id,
            ADDED,
            "Role Created",
            f"**Role:** {role.mention} | {role.id}",
            category="server",
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._log(
            role.guild.id,
            REMOVED,
            "Role Deleted",
            f"**Name:** {role.name} | {role.id}",
            category="server",
        )

    @commands.Cog.listener()
    async def on_guild_role_update(
        self,
        before: discord.Role,
        after: discord.Role,
    ) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** **{before.name}** | **{after.name}**")
        if (
            before.colour != after.colour
            or before.secondary_colour != after.secondary_colour
            or before.tertiary_colour != after.tertiary_colour
        ):
            changes.append(
                f"**Colours:** **{_role_colours(before)}** ({_describe_style(before)}) | "
                f"**{_role_colours(after)}** ({_describe_style(after)})",
            )
        if before.permissions != after.permissions:
            changes.append("**Permissions updated.**")

        if changes:
            await self._log(
                after.guild.id,
                UPDATED,
                "Role Updated",
                f"**Role:** {after.mention} | {after.id}",
                sections=_changes(changes),
                category="server",
            )

    @commands.Cog.listener()
    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} | {after.name}")
        if before.icon != after.icon:
            changes.append("**Icon changed.**")
        if before.owner_id != after.owner_id:
            changes.append(f"**Owner:** <@{before.owner_id}> | <@{after.owner_id}>")

        if changes:
            await self._log(
                after.id,
                UPDATED,
                "Server Updated",
                f"**Server:** {after.name} | {after.id}",
                sections=_changes(changes),
                category="server",
            )

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild: discord.Guild,
        user: discord.User | discord.Member,
    ) -> None:
        await self._log(
            guild.id,
            REMOVED,
            "Member Banned",
            f"**User:** {user} | {user.id}",
            accessory=_thumbnail(user),
            category="member",
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._log(
            guild.id,
            ADDED,
            "Member Unbanned",
            f"**User:** {user} | {user.id}",
            accessory=_thumbnail(user),
            category="member",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AuditCog(bot))
