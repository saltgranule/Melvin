import datetime
import logging

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import DATA_DIR
from helpers import durations
from module_registry import Module, Setting
from ui import CasesView, ErrorUI, InfoUI, PositiveUI, open_config

MODULE = Module(
    "mod",
    "Moderation",
    "Warnings, kicks, bans, mutes, cases, and the auto-role.",
    settings=(
        Setting(
            "auto_role",
            "Auto-role",
            "Given to members when they join. Leave empty for none.",
            "role",
            permission="manage_roles",
        ),
    ),
)

log = logging.getLogger(__name__)

NO_PINGS = discord.AllowedMentions(users=False, roles=False)
REASON_MAX_LENGTH = 300
Reason = app_commands.Range[str, 1, REASON_MAX_LENGTH]
BOT_PERMISSION_LABELS = {"kick_members": "Kick Members", "ban_members": "Ban Members"}
MAX_MUTE_SECONDS = 28 * 86400
Lockable = discord.TextChannel | discord.VoiceChannel | discord.Thread


async def _error(interaction: discord.Interaction, message: str) -> None:
    await interaction.followup.send(view=ErrorUI(f"**{message}**"))


async def _success(
    interaction: discord.Interaction,
    title: str,
    subtitle: str,
    mentions: discord.AllowedMentions = NO_PINGS,
) -> None:
    await interaction.followup.send(
        view=PositiveUI(title=title, subtitle=f"**{subtitle}**"),
        allowed_mentions=mentions,
    )


def _target_error(
    interaction: discord.Interaction,
    member: discord.Member,
    verb: str,
    *,
    check_bot: bool = True,
) -> str | None:
    guild, user = interaction.guild, interaction.user
    if member.bot:
        return f"You tried to {verb} an app."
    if member.id == user.id:
        return f"You tried to {verb} yourself."
    if member.id == guild.owner_id:
        return f"You tried to {verb} the guild owner."
    if member.top_role >= user.top_role and user.id != guild.owner_id:
        return f"You tried to {verb} someone equal to or above you."
    if check_bot and member.top_role >= guild.me.top_role:
        return f"I tried to {verb} someone equal to or above me."
    return None


def _action_error(
    interaction: discord.Interaction,
    member: discord.Member,
    verb: str,
    permission: str,
) -> str | None:
    perms = interaction.guild.me.guild_permissions
    if not (perms.administrator or getattr(perms, permission)):
        label = BOT_PERMISSION_LABELS[permission]
        return f"I lack the {label} permission required to {verb} members."
    if error := _target_error(interaction, member, verb):
        return error
    can_act = member.kickable if verb == "kick" else member.bannable
    if not can_act:
        return f"I tried to {verb} someone I don't have permission to act on."
    return None


def _role_error(interaction: discord.Interaction, role: discord.Role) -> str | None:
    guild, user = interaction.guild, interaction.user
    if role.position >= user.top_role.position and user.id != guild.owner_id:
        return "You tried to manage a role equal to or above your top role."
    if role.position >= guild.me.top_role.position:
        return "I tried to manage a role equal to or above my top role."
    return None


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class ModCog(
    commands.GroupCog,
    name="mod",
    description="Guild moderation commands.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = DATA_DIR / "mod.db"

    role = app_commands.Group(name="role", description="Moderation role commands.")
    cases = app_commands.Group(name="case", description="Moderation case commands.")

    async def cog_load(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mod_cases (
                    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    mod_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """,
            )
            await conn.commit()
        await module_config.migrate_legacy(
            self.db_path,
            "auto_roles",
            "mod",
            lambda row: (int(row[0]), {"auto_role": str(row[1])}),
        )

    async def _add_case(
        self,
        interaction: discord.Interaction,
        user_id: int,
        action: str,
        reason: str,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO mod_cases (guild_id, user_id, mod_id, action_type, reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (interaction.guild_id, user_id, interaction.user.id, action, reason),
            )
            await conn.commit()
            return cursor.lastrowid

    async def _delete_case(self, case_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM mod_cases WHERE case_id = ?", (case_id,))
            await conn.commit()

    async def _log_action(
        self,
        interaction: discord.Interaction,
        action: str,
        **details: object,
    ) -> None:
        audit = self.bot.get_cog("audit")
        if audit is None:
            log.warning("Audit cog is not loaded; %s was not logged.", action)
            return
        if interaction.guild is None:
            return
        await audit.log_moderation(
            interaction.guild,
            action,
            moderator=interaction.user,
            **details,
        )

    async def handle_dm(
        self,
        user: discord.User | discord.Member,
        action_type: str,
        case_id: int | None,
        guild_name: str,
        reason: str,
    ) -> None:
        try:
            await user.send(
                view=InfoUI(
                    title=f"You received a {action_type} in {guild_name}.",
                    subtitle=f"Reason: {reason}. Case {case_id}",
                ),
                allowed_mentions=NO_PINGS,
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await module_settings.is_enabled(member.guild.id, "mod"):
            return

        role_id = await module_config.get(member.guild.id, "mod", "auto_role")
        role = member.guild.get_role(int(role_id)) if role_id else None
        if role is None:
            return

        try:
            await member.add_roles(role, reason="/mod config auto-role")
        except discord.HTTPException:
            pass

    @cases.command(
        name="view",
        description="View moderation cases for a user.",
    )
    @app_commands.describe(target="The target user to view cases for.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def cases_view(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member,
    ) -> None:
        await interaction.response.defer()
        if not interaction.client.user or not interaction.guild:
            return
        if target.bot:
            await _error(interaction, "You tried to view the cases of an app.")
            return

        view = CasesView(target_user=target, db_path=self.db_path)
        await view.build_components(
            interaction.guild.id,
            interaction.user,
            interaction.client.user,
        )
        await interaction.followup.send(view=view, allowed_mentions=NO_PINGS)

    @cases.command(
        name="remove",
        description="Remove a mod action from a users account, takes the ID.",
    )
    @app_commands.describe(
        case_id="Takes the CaseID typically DMed to the user, find it by using /mod case view [user]",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def case_remove(self, interaction: discord.Interaction, case_id: int) -> None:
        await interaction.response.defer()

        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "DELETE FROM mod_cases WHERE guild_id = ? AND case_id = ? "
                "RETURNING user_id, action_type",
                (interaction.guild_id, case_id),
            ) as cursor:
                case = await cursor.fetchone()
            await conn.commit()

        if not case:
            await _error(interaction, f"Case #{case_id} was not found in this server.")
            return

        user_id, action_type = case
        await self._log_action(
            interaction,
            "case_remove",
            target=discord.Object(id=user_id),
            removed_action=action_type,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Case Removed",
            f"Removed case #{case_id} ({action_type.upper()}) for <@{user_id}>.",
            discord.AllowedMentions.none(),
        )

    @app_commands.command(name="warn", description="Warn someone.")
    @app_commands.describe(
        member="The member to warn.",
        reason="The reason for the warning.",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason = "No reason provided.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if error := _target_error(interaction, member, "warn", check_bot=False):
            await _error(interaction, error)
            return

        case_id = await self._add_case(interaction, member.id, "warn", reason)
        await self.handle_dm(member, "warning", case_id, interaction.guild.name, reason)
        await self._log_action(
            interaction,
            "warn",
            target=member,
            reason=reason,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Warning",
            f"{member.mention}, you have been warned. Case {case_id}.",
        )

    @app_commands.command(name="kick", description="Kick a member.")
    @app_commands.describe(
        member="The member to kick.",
        reason="The reason for the kick.",
    )
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason = "No reason provided.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if error := _action_error(interaction, member, "kick", "kick_members"):
            await _error(interaction, error)
            return

        case_id = await self._add_case(interaction, member.id, "kick", reason)
        await self.handle_dm(member, "kick", case_id, interaction.guild.name, reason)
        try:
            await member.kick(
                reason=f"Kicked by Melvin using {interaction.user.name} with the reason: {reason}",
            )
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await self._delete_case(case_id)
            await _error(interaction, "Failed to kick that member.")
            return

        await self._log_action(
            interaction,
            "kick",
            target=member,
            reason=reason,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Kicked",
            f"{member.mention} has been kicked. Case {case_id}.",
        )

    @app_commands.command(name="ban", description="Ban a member.")
    @app_commands.describe(
        member="The member to ban.",
        reason="The reason for the ban.",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason = "No reason provided.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if error := _action_error(interaction, member, "ban", "ban_members"):
            await _error(interaction, error)
            return

        case_id = await self._add_case(interaction, member.id, "ban", reason)
        await self.handle_dm(member, "ban", case_id, interaction.guild.name, reason)
        try:
            await member.ban(
                reason=f"Banned by Melvin using {interaction.user.name} with the reason: {reason}",
                delete_message_seconds=7 * 86400,
            )
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await self._delete_case(case_id)
            await _error(interaction, "Failed to ban that member.")
            return

        await self._log_action(
            interaction,
            "ban",
            target=member,
            reason=reason,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Banned",
            f"{member.mention} has been banned. Case {case_id}.",
        )

    @app_commands.command(name="unban", description="Unban a user.")
    @app_commands.describe(
        user="The user to unban.",
        reason="The reason for the unban.",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: Reason = "No reason provided.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        try:
            await interaction.guild.fetch_ban(user)
        except discord.NotFound:
            await _error(interaction, "That user is not banned.")
            return
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await _error(interaction, "Failed to check ban status.")
            return

        try:
            await interaction.guild.unban(
                user,
                reason=f"Unbanned using Melvin by {interaction.user.name} with the reason: {reason}",
            )
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await _error(interaction, "Failed to unban that user.")
            return

        case_id = await self._add_case(interaction, user.id, "unban", reason)
        await self._log_action(
            interaction,
            "unban",
            target=user,
            reason=reason,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Unbanned",
            f"{user.mention} has been unbanned. Case {case_id}.",
        )

    @app_commands.command(name="mute", description="Mute a member.")
    @app_commands.describe(
        member="The member to mute.",
        duration="The duration of the mute (e.g., 10m, 2h, 1d).",
        reason="The reason for the mute.",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: Reason = "No reason provided.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        seconds = durations.parse_duration(duration)
        if not seconds:
            error = "Not a valid duration format."
        elif seconds > MAX_MUTE_SECONDS:
            error = "Duration cannot surpass 28 days."
        else:
            error = _target_error(interaction, member, "mute")
        if error:
            await _error(interaction, error)
            return

        try:
            await member.timeout(
                discord.utils.utcnow() + datetime.timedelta(seconds=seconds),
                reason=f"Muted by Melvin using {interaction.user.name} with the reason: {reason}",
            )
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await _error(interaction, "Failed to mute that member.")
            return

        case_id = await self._add_case(interaction, member.id, "mute", reason)
        await self.handle_dm(member, "mute", case_id, interaction.guild.name, reason)
        await self._log_action(
            interaction,
            "mute",
            target=member,
            reason=reason,
            case_id=case_id,
            duration=duration,
        )
        await _success(
            interaction,
            "Muted",
            f"{member.mention} has been muted. Case {case_id}.",
        )

    @app_commands.command(name="unmute", description="Unmute a member.")
    @app_commands.describe(
        member="The member to unmute.",
        reason="The reason for the unmute.",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason = "No reason given.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not member.is_timed_out():
            await _error(interaction, "Member is not timed out.")
            return
        if (
            member.top_role >= interaction.user.top_role
            and interaction.user.id != interaction.guild.owner_id
        ):
            await _error(
                interaction,
                "You tried to unmute someone equal to or above you.",
            )
            return

        try:
            await member.timeout(
                None,
                reason=f"Unmuted by Melvin using {interaction.user.name} with the reason: {reason}",
            )
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await _error(interaction, "Failed to unmute that member.")
            return

        case_id = await self._add_case(interaction, member.id, "unmute", reason)
        await self.handle_dm(member, "unmute", case_id, interaction.guild.name, reason)
        await self._log_action(
            interaction,
            "unmute",
            target=member,
            reason=reason,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Unmuted",
            f"{member.mention} has been unmuted. Case {case_id}.",
        )

    async def _set_locked(
        self,
        interaction: discord.Interaction,
        channel: Lockable | None,
        audit_reason: str,
        *,
        locked: bool,
    ) -> Lockable | None:
        target = channel or interaction.channel
        if not isinstance(target, Lockable):
            await _error(
                interaction,
                "This can only be used in a text channel, voice channel, or thread."
                if locked
                else "This can only be used in either a text channel, voice channel, or thread.",
            )
            return None

        if isinstance(target, discord.Thread):
            if target.locked == locked:
                await _error(
                    interaction,
                    "This thread is already locked."
                    if locked
                    else "This thread is not locked.",
                )
                return None
            await target.edit(locked=locked, reason=audit_reason)
            return target

        everyone = interaction.guild.default_role
        overwrite = target.overwrites_for(everyone)
        if (overwrite.send_messages is False) == locked:
            await _error(
                interaction,
                "This channel is already locked."
                if locked
                else "This channel is not locked.",
            )
            return None

        overwrite.send_messages = False if locked else None
        await target.set_permissions(everyone, overwrite=overwrite, reason=audit_reason)
        return target

    @app_commands.command(name="lock", description="Lock a channel.")
    @app_commands.describe(
        channel="The channel or thread to lock.",
        reason="The reason for locking.",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: Lockable | None = None,
        reason: Reason = "No reason given.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild:
            return

        target = await self._set_locked(
            interaction,
            channel,
            f"Locked using Melvin by {interaction.user.name} for the reason: {reason}",
            locked=True,
        )
        if target is not None:
            await self._log_action(
                interaction,
                "lock",
                target=target,
                reason=reason,
            )
            await _success(interaction, "Locked", f"{target.mention} has been locked.")

    @app_commands.command(name="unlock", description="Unlock a channel.")
    @app_commands.describe(
        channel="The channel or thread to unlock.",
        reason="The reason for unlocking.",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: Lockable | None = None,
        reason: Reason = "No reason given.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild:
            return

        target = await self._set_locked(
            interaction,
            channel,
            f"Unlocked using Melvin by {interaction.user.name} with the reason: {reason}",
            locked=False,
        )
        if target is not None:
            await self._log_action(
                interaction,
                "unlock",
                target=target,
                reason=reason,
            )
            await _success(
                interaction,
                "Unlocked",
                f"Unlocked {target.mention}.",
                discord.AllowedMentions.none(),
            )

    @role.command(
        name="add",
        description="Add a role to a member.",
    )
    @app_commands.describe(
        member="The member to give the role to.",
        role="The role to add.",
        reason="The reason for adding the role.",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: Reason = "No reason provided.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if role.is_default():
            error = "You cannot modify the @everyone role."
        elif role.is_premium_subscriber():
            error = (
                "You cannot add the server booster role; Discord gives it to boosters."
            )
        elif member.bot:
            error = "You tried to add a role to an app."
        elif role in member.roles:
            error = "That member already has this role."
        else:
            error = _role_error(interaction, role)
        if error:
            await _error(interaction, error)
            return

        case_id = await self._add_case(interaction, member.id, "role_add", reason)
        try:
            await member.add_roles(
                role,
                reason=f"Role added by Melvin using {interaction.user.name} with the reason: {reason}",
            )
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await self._delete_case(case_id)
            await _error(interaction, "Failed to add that role.")
            return

        await self._log_action(
            interaction,
            "role_add",
            target=member,
            role=role,
            reason=reason,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Role Added",
            f"{role.mention} added to {member.mention}. Case {case_id}.",
        )

    @role.command(
        name="remove",
        description="Remove a role from a member.",
    )
    @app_commands.describe(
        member="The member to remove the role from.",
        role="The role to remove.",
        reason="The reason for removing the role.",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: Reason = "No reason provided.",
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if role.is_default():
            error = "You cannot modify the @everyone role."
        elif member.bot:
            error = "You tried to remove a role from an app."
        elif role not in member.roles:
            error = "That member does not have this role."
        else:
            error = _role_error(interaction, role)
        if error:
            await _error(interaction, error)
            return

        case_id = await self._add_case(interaction, member.id, "role_remove", reason)
        try:
            await member.remove_roles(
                role,
                reason=f"Role removed by Melvin using {interaction.user.name} with the reason: {reason}",
            )
        except discord.HTTPException:
            log.exception("Moderation action failed")
            await self._delete_case(case_id)
            await _error(interaction, "Failed to remove that role.")
            return

        await self._log_action(
            interaction,
            "role_remove",
            target=member,
            role=role,
            reason=reason,
            case_id=case_id,
        )
        await _success(
            interaction,
            "Role Removed",
            f"{role.mention} removed from {member.mention}. Case {case_id}.",
        )

    @app_commands.command(
        name="config",
        description="Change moderation settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "mod")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModCog(bot))
