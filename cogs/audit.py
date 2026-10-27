import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import DATA_DIR, PRIMARY, SECONDARY, TERTIARY
from module_registry import Module, Setting
from ui import LargeSeparator, open_config

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
            "Joins, leaves, and member or profile changes. Uses the audit channel if not set.",
            "channel",
        ),
        Setting(
            "moderation_channel",
            "Moderation channel",
            "Bans, kicks, unbans, and timeouts. Uses the audit channel if not set.",
            "channel",
        ),
        Setting(
            "server_channel",
            "Server channel",
            "Server, channel, and role changes. Uses the audit channel if not set.",
            "channel",
        ),
        Setting(
            "voice_channel",
            "Voice channel",
            "Voice channel activity. Uses the audit channel if not set.",
            "channel",
        ),
    ),
)

LOG_CHANNEL_SETTINGS = {
    "message": "message_channel",
    "member": "member_channel",
    "moderation": "moderation_channel",
    "server": "server_channel",
    "voice": "voice_channel",
}

log = logging.getLogger(__name__)

WEBHOOK_TABLE = """
    CREATE TABLE IF NOT EXISTS audit_webhooks (
        guild_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        channel_id INTEGER NOT NULL,
        webhook_id INTEGER NOT NULL,
        token TEXT NOT NULL,
        PRIMARY KEY (guild_id, category)
    )
"""

HOLOGRAPHIC_VALUES = (11127295, 16759788, 16761760)
NO_CONTENT = "[No content, likely an embed or attachment.]"

UPDATED = discord.Color.from_str(PRIMARY)
ADDED = discord.Color.from_str(SECONDARY)
REMOVED = discord.Color.from_str(TERTIARY)

MOD_ACTIONS = {
    "warn": ("Member Warned", UPDATED),
    "kick": ("Member Kicked", REMOVED),
    "ban": ("Member Banned", REMOVED),
    "unban": ("Member Unbanned", ADDED),
    "mute": ("Member Muted", UPDATED),
    "unmute": ("Member Unmuted", ADDED),
    "lock": ("Channel Locked", UPDATED),
    "unlock": ("Channel Unlocked", ADDED),
    "role_add": ("Role Added", ADDED),
    "role_remove": ("Role Removed", REMOVED),
    "case_remove": ("Case Removed", UPDATED),
}
AUTO_ROLE_REASON = "/mod config auto-role"


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


def _moderator_line(entry: discord.AuditLogEntry | None) -> str:
    if entry is None or entry.user is None:
        return ""
    return f"\n**Moderator:** {entry.user.mention} | {entry.user.id}"


def _reason_sections(entry: discord.AuditLogEntry | None) -> Sequence[Sequence[str]]:
    if entry is None or not entry.reason:
        return ()
    return _changes([f"**Reason:** {_clean(entry.reason, 300)}"])


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
        self.session: aiohttp.ClientSession | None = None
        self._webhook_locks: dict[tuple[int, str], asyncio.Lock] = {}
        self._webhook_cache: dict[tuple[int, str], tuple[int, discord.Webhook]] = {}

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()
        await module_config.migrate_legacy(
            self.db_path,
            "log_channels",
            "audit",
            lambda row: (int(row[0]), {"log_channel": row[1]}),
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(WEBHOOK_TABLE)
            await db.commit()
        await module_config.init_db()
        async with aiosqlite.connect(module_config.DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, value FROM guild_settings "
                "WHERE module = 'audit' AND key = 'other_channel'",
            ) as cursor:
                legacy = await cursor.fetchall()
        for guild_id, value in legacy:
            if value and not await module_config.get(
                guild_id, "audit", "voice_channel"
            ):
                await module_config.set_values(
                    guild_id, "audit", {"voice_channel": value}
                )
        if legacy:
            async with aiosqlite.connect(module_config.DB_PATH) as db:
                await db.execute(
                    "DELETE FROM guild_settings WHERE module = 'audit' AND key = 'other_channel'",
                )
                await db.commit()

    async def cog_unload(self) -> None:
        if self.session is not None:
            await self.session.close()

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

    def _webhook_lock(self, guild_id: int, category: str) -> asyncio.Lock:
        return self._webhook_locks.setdefault((guild_id, category), asyncio.Lock())

    async def _get_webhook_row(
        self,
        guild_id: int,
        category: str,
    ) -> tuple[int, int, str] | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT channel_id, webhook_id, token FROM audit_webhooks "
                "WHERE guild_id = ? AND category = ?",
                (guild_id, category),
            )
            row = await cursor.fetchone()
        return (int(row[0]), int(row[1]), str(row[2])) if row else None

    async def _set_webhook_row(
        self,
        guild_id: int,
        category: str,
        channel_id: int,
        webhook_id: int,
        token: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO audit_webhooks "
                "(guild_id, category, channel_id, webhook_id, token) "
                "VALUES (?, ?, ?, ?, ?)",
                (guild_id, category, channel_id, webhook_id, token),
            )
            await db.commit()

    async def _clear_webhook_row(self, guild_id: int, category: str) -> None:
        self._webhook_cache.pop((guild_id, category), None)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM audit_webhooks WHERE guild_id = ? AND category = ?",
                (guild_id, category),
            )
            await db.commit()

    def _partial_webhook(self, webhook_id: int, token: str) -> discord.Webhook:
        if self.session is None:
            msg = "AuditCog session used before cog_load."
            raise RuntimeError(msg)
        return discord.Webhook.partial(webhook_id, token, session=self.session)

    async def _delete_remote_webhook(self, webhook_id: int, token: str) -> None:
        try:
            await self._partial_webhook(webhook_id, token).delete()
        except discord.NotFound, discord.Forbidden:
            pass
        except discord.HTTPException:
            log.warning("Couldn't delete old audit webhook %s", webhook_id)

    async def new_webhook(
        self,
        channel: discord.TextChannel,
        category: str,
    ) -> discord.Webhook | None:
        guild_id = channel.guild.id
        old = await self._get_webhook_row(guild_id, category)
        if old is not None:
            await self._delete_remote_webhook(old[1], old[2])
            await self._clear_webhook_row(guild_id, category)

        try:
            webhook = await channel.create_webhook(
                name=f"{category.title()} Logs",
                reason="Audit log destination changed or first use.",
            )
        except discord.Forbidden, discord.HTTPException:
            log.warning("Couldn't create audit webhook in channel %s", channel.id)
            return None

        if webhook.token is None:
            return None
        await self._set_webhook_row(
            guild_id,
            category,
            channel.id,
            webhook.id,
            webhook.token,
        )
        self._webhook_cache[(guild_id, category)] = (channel.id, webhook)
        return webhook

    async def _ensure_webhook(
        self,
        channel: discord.TextChannel,
        category: str,
    ) -> discord.Webhook | None:
        key = (channel.guild.id, category)
        cached = self._webhook_cache.get(key)
        if cached is not None and cached[0] == channel.id:
            return cached[1]
        async with self._webhook_lock(channel.guild.id, category):
            cached = self._webhook_cache.get(key)
            if cached is not None and cached[0] == channel.id:
                return cached[1]
            row = await self._get_webhook_row(channel.guild.id, category)
            if row is not None and row[0] == channel.id:
                webhook = self._partial_webhook(row[1], row[2])
                self._webhook_cache[key] = (channel.id, webhook)
                return webhook
            return await self.new_webhook(channel, category)

    async def send_via_webhook(
        self,
        channel: discord.TextChannel,
        category: str,
        view: discord.ui.LayoutView,
    ) -> None:
        for _ in range(2):
            webhook = await self._ensure_webhook(channel, category)
            if webhook is None:
                return
            try:
                await webhook.send(
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            except discord.NotFound:
                async with self._webhook_lock(channel.guild.id, category):
                    await self._clear_webhook_row(channel.guild.id, category)
            except discord.HTTPException:
                log.warning("Couldn't send audit log to channel %s", channel.id)
                return

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
        await self.send_via_webhook(channel, category, view)

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
        kick = await self._recent_entry(
            member.guild,
            discord.AuditLogAction.kick,
            member.id,
        )
        if kick is not None:
            if await self._is_mod_duplicate(member.guild, kick):
                return
            await self._log(
                member.guild.id,
                REMOVED,
                "Member Kicked",
                f"**{member} was kicked.**\n**Member #{member.guild.member_count}.**"
                f"{_moderator_line(kick)}",
                accessory=_thumbnail(member),
                sections=_reason_sections(kick),
                category="moderation",
            )
            return

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
            role_entry = await self._recent_entry(
                after.guild,
                discord.AuditLogAction.member_role_update,
                after.id,
            )
            if not await self._is_mod_duplicate(after.guild, role_entry):
                before_roles, after_roles = set(before.roles), set(after.roles)
                if added := after_roles - before_roles:
                    changes.append(
                        f"**Roles added:** {', '.join(r.mention for r in added)}",
                    )
                if removed := before_roles - after_roles:
                    changes.append(
                        f"**Roles removed:** {', '.join(r.mention for r in removed)}",
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

        if before.timed_out_until != after.timed_out_until:
            await self._log_timeout(after)

    async def _recent_entry(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
        match: Callable[[discord.AuditLogEntry], bool] | None = None,
    ) -> discord.AuditLogEntry | None:
        since = discord.utils.utcnow() - timedelta(seconds=15)
        try:
            async for entry in guild.audit_logs(limit=10, action=action, after=since):
                if getattr(entry.target, "id", None) != target_id:
                    continue
                if match is not None and not match(entry):
                    continue
                return entry
        except discord.HTTPException:
            return None
        return None

    async def _is_mod_duplicate(
        self,
        guild: discord.Guild,
        entry: discord.AuditLogEntry | None,
    ) -> bool:
        if entry is None or entry.user is None or self.bot.user is None:
            return False
        if entry.user.id != self.bot.user.id or entry.reason == AUTO_ROLE_REASON:
            return False
        return await module_settings.is_enabled(guild.id, "mod")

    async def log_moderation(
        self,
        guild: discord.Guild,
        action: str,
        *,
        moderator: discord.abc.User,
        target: discord.abc.Snowflake,
        reason: str | None = None,
        case_id: int | None = None,
        role: discord.Role | None = None,
        duration: str | None = None,
        removed_action: str | None = None,
    ) -> None:
        title, color = MOD_ACTIONS[action]
        if isinstance(target, (discord.abc.GuildChannel, discord.Thread)):
            target_text = f"{target.mention} | {target.id}"
            thumbnail = None
        else:
            target_text = f"<@{target.id}> | {target.id}"
            thumbnail = (
                target if isinstance(target, (discord.User, discord.Member)) else None
            )

        lines = [
            f"**Target:** {target_text}",
            f"**Moderator:** {moderator.mention} | {moderator.id}",
        ]
        if role is not None:
            lines.append(f"**Role:** {role.mention} | {role.id}")
        if duration is not None:
            lines.append(f"**Duration:** {duration}")
        if removed_action is not None:
            lines.append(f"**Removed action:** {removed_action.upper()}")
        if case_id is not None:
            lines.append(f"**Case:** {case_id}")

        sections = [[f"### Reason\n{_clean(reason, 300)}"]] if reason else []
        await self._log(
            guild.id,
            color,
            title,
            "\n".join(lines),
            accessory=_thumbnail(thumbnail) if thumbnail is not None else None,
            sections=sections,
            category="moderation",
        )

    async def _log_timeout(self, member: discord.Member) -> None:
        if member.timed_out_until is not None:
            title = "Member Timed Out"
            line = f"**Timed out until:** {discord.utils.format_dt(member.timed_out_until, style='f')}"
        else:
            title = "Timeout Removed"
            line = "**Timeout removed.**"

        entry = await self._recent_entry(
            member.guild,
            discord.AuditLogAction.member_update,
            member.id,
            match=lambda e: (
                hasattr(e.after, "timed_out_until")
                and e.after.timed_out_until == member.timed_out_until
            ),
        )
        if await self._is_mod_duplicate(member.guild, entry):
            return

        changes = [line]
        if entry is not None and entry.reason:
            changes.append(f"**Reason:** {_clean(entry.reason, 300)}")

        await self._log(
            member.guild.id,
            UPDATED,
            title,
            f"**Member:** {member.mention} | {member.id}{_moderator_line(entry)}",
            accessory=_thumbnail(member),
            sections=_changes(changes),
            category="moderation",
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
            category="voice",
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
        entry = await self._recent_entry(guild, discord.AuditLogAction.ban, user.id)
        if await self._is_mod_duplicate(guild, entry):
            return
        await self._log(
            guild.id,
            REMOVED,
            "Member Banned",
            f"**User:** {user} | {user.id}{_moderator_line(entry)}",
            accessory=_thumbnail(user),
            sections=_reason_sections(entry),
            category="moderation",
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        entry = await self._recent_entry(guild, discord.AuditLogAction.unban, user.id)
        if await self._is_mod_duplicate(guild, entry):
            return
        await self._log(
            guild.id,
            ADDED,
            "Member Unbanned",
            f"**User:** {user} | {user.id}{_moderator_line(entry)}",
            accessory=_thumbnail(user),
            sections=_reason_sections(entry),
            category="moderation",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AuditCog(bot))
