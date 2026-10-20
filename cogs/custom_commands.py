import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

import command_store
import module_config
import module_settings
from command_engine import (
    Run,
    build,
    check_command,
    render,
    sample_args,
    send_kwargs,
    tag_kind,
)
from command_store import (
    COMMAND_LIMIT,
    Command,
    CommandExists,
    CommandLimit,
    CommandMissing,
    clean_name,
)
from globals import MELVIN_EMOJI
from helpers.commands import (
    CommandError,
    access_error,
    bind_args,
    clean_args,
    clean_permission,
    describe_permission,
    parse_args,
    snowflake,
    split_args,
)
from module_registry import Module, Setting
from ui import ErrorUI, InfoUI, Paginator, PositiveUI, open_config

MODULE = Module(
    "tags",
    "Custom Commands",
    "Saved messages with arguments, logic, and role changes.",
    settings=(
        Setting(
            "prefix",
            "Chat prefix",
            "Posts a command from chat, like ?rules. Up to 3 characters.",
            "text",
            default="?",
            max_length=3,
            placeholder="?",
        ),
        Setting(
            "chat",
            "Chat posts",
            "Post commands from chat. Slash commands always work.",
            "choice",
            default="on",
            choices=(("on", "On"), ("off", "Off")),
        ),
    ),
)

log = logging.getLogger(__name__)

NO_MENTIONS = discord.AllowedMentions.none()
DEFAULT_PREFIX = "?"
PREFIX_LENGTH = 3
CONTENT_LENGTH = 4000
AUTOCOMPLETE_LIMIT = 25
PER_PAGE = 15
NAME_ERROR = (
    "**Names use letters, numbers, hyphens, and underscores, up to 32 characters.**"
)
LIMIT_ERROR = f"**A server can have up to {COMMAND_LIMIT} commands.**"


def _can_manage(interaction: discord.Interaction) -> bool:
    member = interaction.user
    return (
        isinstance(member, discord.Member) and member.guild_permissions.manage_messages
    )


def _may_change_roles(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator or member.guild_permissions.manage_roles
    )


async def _respond(
    interaction: discord.Interaction, view: discord.ui.LayoutView
) -> None:
    await interaction.response.send_message(view=view, ephemeral=True)


async def _deny(interaction: discord.Interaction) -> None:
    await _respond(
        interaction, ErrorUI("**You need Manage Messages to edit commands.**")
    )


def _not_found(name: str) -> ErrorUI:
    return ErrorUI(f"**There is no command called `{name}`.**")


def _run_for(guild: discord.Guild, member: discord.Member, values: list[str]) -> Run:
    return Run(
        args=values,
        now=int(time.time()),
        user=member.mention,
        user_id=str(member.id),
        user_name=member.display_name,
        server=guild.name,
        server_id=str(guild.id),
        members=guild.member_count,
    )


def _describe_effect(verb: str, target: str, role: str) -> str:
    if verb == "addrole":
        return f"Give the {role} role to {target}"
    return f"Take the {role} role from {target}"


class CommandEditModal(discord.ui.Modal):
    def __init__(self, cog: CustomCommandsCog, name: str, raw: str) -> None:
        super().__init__(title=f"Edit {name}"[:45])
        self.cog = cog
        self.command = name
        self.body_input = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            default=raw,
            max_length=CONTENT_LENGTH,
            required=False,
        )
        self.add_item(
            discord.ui.Label(
                text="Content",
                description="Empty it and tick Delete to remove.",
                component=self.body_input,
            ),
        )
        self.delete_box = discord.ui.Checkbox()
        self.add_item(
            discord.ui.Label(text="Delete this command", component=self.delete_box)
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not _can_manage(interaction):
            await _deny(interaction)
            return

        if self.delete_box.value:
            if not await command_store.delete(interaction.guild_id, self.command):
                await _respond(interaction, _not_found(self.command))
                return
            await _respond(
                interaction,
                PositiveUI(
                    title="Command deleted",
                    subtitle=f"**`{self.command}`** has been removed.",
                ),
            )
            return

        raw = self.body_input.value.strip()
        existing = await command_store.fetch(interaction.guild_id, self.command)
        error = (
            check_command(raw, existing.args if existing else "")
            if raw
            else "A command needs some text. Tick Delete to remove it."
        )
        if error:
            await _respond(interaction, ErrorUI(f"**{error}**"))
            return

        try:
            await command_store.update(
                interaction.guild_id, self.command, {"content": raw}
            )
        except CommandMissing:
            await _respond(
                interaction, ErrorUI(f"**`{self.command}` no longer exists.**")
            )
            return
        await _respond(
            interaction,
            PositiveUI(
                title="Command updated", subtitle=f"**`{self.command}`** has new text."
            ),
        )


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class CustomCommandsCog(
    commands.GroupCog,
    name="command",
    description="Custom commands for this server.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def cog_load(self) -> None:
        await command_store.init_db()

    async def _prefix(self, guild_id: int) -> str:
        value = await module_config.get(guild_id, "tags", "prefix") or DEFAULT_PREFIX
        if 1 <= len(value) <= PREFIX_LENGTH and not any(c.isspace() for c in value):
            return value
        return DEFAULT_PREFIX

    async def _name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild_id is None:
            return []
        names = await command_store.autocomplete_names(
            interaction.guild_id,
            current,
            AUTOCOMPLETE_LIMIT,
        )
        return [app_commands.Choice(name=name, value=name) for name in names]

    async def _bind(
        self, guild: discord.Guild, command: Command, raw: str
    ) -> list[str]:
        if command.args:
            return await bind_args(guild, parse_args(command.args), raw)
        return split_args(raw) if raw.strip() else []

    async def _apply(
        self,
        guild: discord.Guild,
        invoker: discord.Member,
        effects: list[tuple[str, str, str]],
    ) -> None:
        for verb, target_token, role_token in effects:
            target_id = snowflake(target_token)
            role_id = snowflake(role_token)
            if target_id is None or role_id is None:
                continue

            role = guild.get_role(role_id)
            if role is None or role.managed or role.is_default():
                continue
            if role >= guild.me.top_role:
                continue
            if invoker.id != guild.owner_id and role >= invoker.top_role:
                continue

            target = guild.get_member(target_id)
            if target is None:
                try:
                    target = await guild.fetch_member(target_id)
                except discord.HTTPException:
                    continue

            reason = f"Custom command run by {invoker}"
            try:
                if verb == "addrole":
                    await target.add_roles(role, reason=reason)
                else:
                    await target.remove_roles(role, reason=reason)
            except discord.HTTPException:
                log.warning("Couldn't %s %s for %s", verb, role.id, target.id)

    async def _execute(
        self,
        guild: discord.Guild | None,
        member: discord.abc.User,
        command: Command,
        raw: str,
        send: Callable[..., Awaitable[object]],
    ) -> None:
        if guild is None or not isinstance(member, discord.Member):
            msg = "Custom commands only work in servers."
            raise CommandError(msg)

        if error := access_error(member, command.permission):
            raise CommandError(error)

        run = _run_for(guild, member, await self._bind(guild, command, raw))
        rendered = render(build(command.content, run), run)

        if run.effects and not _may_change_roles(member):
            msg = "You need Manage Roles to use this."
            raise CommandError(msg)

        await send(**send_kwargs(rendered))

        if run.effects:
            await self._apply(guild, member, run.effects)

    @app_commands.command(name="run", description="Post a custom command.")
    @app_commands.describe(
        name="The command to post.",
        args="Values for its arguments.",
    )
    async def run(
        self, interaction: discord.Interaction, name: str, args: str = ""
    ) -> None:
        tag = clean_name(name)
        command = await command_store.fetch(interaction.guild_id, tag) if tag else None
        if command is None:
            await _respond(interaction, _not_found(name))
            return

        async def send(**kwargs: object) -> None:
            await interaction.response.send_message(
                **kwargs, allowed_mentions=NO_MENTIONS
            )

        try:
            await self._execute(
                interaction.guild, interaction.user, command, args, send
            )
        except CommandError as error:
            await _respond(interaction, ErrorUI(f"**{error}**"))

    @run.autocomplete("name")
    async def run_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current)

    @app_commands.command(name="create", description="Save a new custom command.")
    @app_commands.describe(
        name="Letters, numbers, - or _, up to 32 characters.",
        content="What it says. Roles: $addrole{member|role}",
        args="Like amount:number:1-100 reason?:text",
        permission="none, manage_messages, a role, etc.",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def create(
        self,
        interaction: discord.Interaction,
        name: str,
        content: app_commands.Range[str, 1, CONTENT_LENGTH],
        args: str = "",
        permission: str = "none",
    ) -> None:
        command = clean_name(name)
        if command is None:
            await _respond(interaction, ErrorUI(NAME_ERROR))
            return

        try:
            cleaned_args = clean_args(args)
            if error := check_command(content, cleaned_args):
                raise CommandError(error)
            cleaned_permission = clean_permission(permission)
        except CommandError as error:
            await _respond(interaction, ErrorUI(f"**{error}**"))
            return

        try:
            await command_store.create(
                interaction.guild_id,
                command,
                content.strip(),
                interaction.user.id,
                args=cleaned_args,
                permission=cleaned_permission,
            )
        except CommandExists:
            await _respond(
                interaction,
                ErrorUI(
                    f"**`{command}` already exists. Use /command edit to change it.**"
                ),
            )
            return
        except CommandLimit:
            await _respond(interaction, ErrorUI(LIMIT_ERROR))
            return

        await _respond(
            interaction,
            PositiveUI(
                title="Command created",
                subtitle=f"**`{command}`** can now be used with /command run.",
            ),
        )

    @app_commands.command(
        name="edit",
        description="Change a command. No options opens its text.",
    )
    @app_commands.describe(
        name="The command to change.",
        content="New text for the command.",
        args="New arguments. Empty removes them.",
        permission="New permission. none for everyone.",
        new_name="A new name for the command.",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit(
        self,
        interaction: discord.Interaction,
        name: str,
        content: str | None = None,
        args: str | None = None,
        permission: str | None = None,
        new_name: str | None = None,
    ) -> None:
        command = clean_name(name)
        if command is None:
            await _respond(interaction, ErrorUI(NAME_ERROR))
            return

        existing = await command_store.fetch(interaction.guild_id, command)
        if existing is None:
            await _respond(interaction, _not_found(name))
            return

        if all(option is None for option in (content, args, permission, new_name)):
            await interaction.response.send_modal(
                CommandEditModal(self, command, existing.content)
            )
            return

        changes: dict[str, str] = {}
        target = None
        try:
            if args is not None:
                changes["args"] = clean_args(args)
            if content is not None:
                changes["content"] = content.strip()
            if "content" in changes or "args" in changes:
                error = check_command(
                    changes.get("content", existing.content),
                    changes.get("args", existing.args),
                )
                if error:
                    raise CommandError(error)
            if permission is not None:
                changes["permission"] = clean_permission(permission)
            if new_name is not None:
                target = clean_name(new_name)
                if target is None:
                    raise CommandError(NAME_ERROR.strip("*"))
                if target == command:
                    target = None
                elif await command_store.fetch(interaction.guild_id, target):
                    msg = f"`{target}` already exists."
                    raise CommandError(msg)
        except CommandError as error:
            await _respond(interaction, ErrorUI(f"**{error}**"))
            return

        try:
            if changes:
                await command_store.update(interaction.guild_id, command, changes)
            if target is not None:
                await command_store.rename(interaction.guild_id, command, target)
                command = target
        except CommandMissing:
            await _respond(interaction, _not_found(name))
            return
        except CommandExists:
            await _respond(interaction, ErrorUI(f"**`{target}` already exists.**"))
            return

        await _respond(
            interaction,
            PositiveUI(
                title="Command updated", subtitle=f"**`{command}`** was changed."
            ),
        )

    @edit.autocomplete("name")
    async def edit_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current)

    @app_commands.command(
        name="view",
        description="See a command's setup and a preview.",
    )
    @app_commands.describe(
        name="The command to look at.",
        args="Values to preview with. Empty uses sample values.",
    )
    async def view(
        self, interaction: discord.Interaction, name: str, args: str = ""
    ) -> None:
        tag = clean_name(name)
        command = await command_store.fetch(interaction.guild_id, tag) if tag else None
        if command is None:
            await _respond(interaction, _not_found(name))
            return

        if not _can_manage(interaction) and (
            problem := access_error(interaction.user, command.permission)
        ):
            await _respond(interaction, ErrorUI(f"**{problem}**"))
            return

        try:
            if not args.strip() and command.args:
                values = sample_args(command.args)
            else:
                values = await self._bind(interaction.guild, command, args)
            run = _run_for(interaction.guild, interaction.user, values)
            rendered = render(build(command.content, run), run)
        except CommandError as error:
            await _respond(interaction, ErrorUI(f"**{error}**"))
            return

        created = discord.utils.format_dt(
            datetime.fromtimestamp(command.created_at, UTC), style="F"
        )
        changed = discord.utils.format_dt(
            datetime.fromtimestamp(command.updated_at, UTC), style="R"
        )
        await _respond(
            interaction,
            InfoUI(
                title=f"Command {command.name}",
                subtitle=(
                    f"**Author:** <@{command.author_id}>\n"
                    f"**Created:** {created}\n"
                    f"**Last changed:** {changed}\n"
                    f"**Type:** {tag_kind(command.content).title()}\n"
                    f"**Length:** {len(command.content):,} characters\n"
                    f"**Arguments:** {command.args or 'None'}\n"
                    f"**Who can use it:** {describe_permission(command.permission)}"
                ),
            ),
        )
        await interaction.followup.send(
            **send_kwargs(rendered),
            ephemeral=True,
            allowed_mentions=NO_MENTIONS,
        )
        if run.effects:
            changes = "; ".join(_describe_effect(*effect) for effect in run.effects)
            await interaction.followup.send(
                f"-# Preview only. Running this would: {changes}.",
                ephemeral=True,
            )

    @view.autocomplete("name")
    async def view_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current)

    @app_commands.command(name="delete", description="Delete a custom command.")
    @app_commands.describe(name="The command to delete.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        command = clean_name(name)
        if command is None or not await command_store.delete(
            interaction.guild_id, command
        ):
            await _respond(interaction, _not_found(name))
            return
        await _respond(
            interaction,
            PositiveUI(
                title="Command deleted", subtitle=f"**`{command}`** has been removed."
            ),
        )

    @delete.autocomplete("name")
    async def delete_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current)

    @app_commands.command(
        name="copy", description="Make a copy of a command under a new name."
    )
    @app_commands.describe(
        name="The command to copy.", new_name="The name for the copy."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def copy(
        self, interaction: discord.Interaction, name: str, new_name: str
    ) -> None:
        source = clean_name(name)
        target = clean_name(new_name)
        if target is None:
            await _respond(interaction, ErrorUI(NAME_ERROR))
            return
        if source is None:
            await _respond(interaction, _not_found(name))
            return

        try:
            await command_store.copy(
                interaction.guild_id, source, target, interaction.user.id
            )
        except CommandMissing:
            await _respond(interaction, _not_found(name))
            return
        except CommandExists:
            await _respond(interaction, ErrorUI(f"**`{target}` already exists.**"))
            return
        except CommandLimit:
            await _respond(interaction, ErrorUI(LIMIT_ERROR))
            return

        await _respond(
            interaction,
            PositiveUI(
                title="Command copied",
                subtitle=f"**`{source}`** is now also **`{target}`**.",
            ),
        )

    @copy.autocomplete("name")
    async def copy_name(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current)

    @app_commands.command(
        name="list", description="List or search this server's commands."
    )
    @app_commands.describe(query="Part of a name.")
    async def list_commands(
        self,
        interaction: discord.Interaction,
        query: app_commands.Range[str, 0, 32] = "",
    ) -> None:
        commands_found = await command_store.list_commands(interaction.guild_id, query)
        names = [command.name for command in commands_found]

        if not names:
            subtitle = (
                f"**No commands match `{discord.utils.escape_markdown(query)}`.**"
                if query.strip()
                else "**This server has no commands yet.**"
            )
            await _respond(interaction, InfoUI(title="Commands", subtitle=subtitle))
            return

        title = f"### {MELVIN_EMOJI} Commands"
        if query.strip():
            title += f" matching `{discord.utils.escape_markdown(query)}`"
        title += "\n-# /command view or /command edit shows one."
        view = Paginator(
            title,
            names,
            data_name="Commands",
            per_page=PER_PAGE,
            container=True,
            timeout=300,
        )
        await interaction.response.send_message(view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @app_commands.command(name="config", description="Open the settings.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "tags")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.author.bot
            or message.guild is None
            or not isinstance(message.author, discord.Member)
        ):
            return

        prefix = await self._prefix(message.guild.id)
        if not message.content.startswith(prefix):
            return
        if not await module_settings.is_enabled(message.guild.id, "tags"):
            return
        if await module_config.get(message.guild.id, "tags", "chat") == "off":
            return

        parts = message.content[len(prefix) :].split(maxsplit=1)
        name = clean_name(parts[0]) if parts else None
        if name is None:
            return
        command = await command_store.fetch(message.guild.id, name)
        if command is None:
            return

        async def send(**kwargs: object) -> None:
            await message.reply(
                **kwargs, mention_author=False, allowed_mentions=NO_MENTIONS
            )

        try:
            await self._execute(
                message.guild,
                message.author,
                command,
                parts[1] if len(parts) > 1 else "",
                send,
            )
        except CommandError as error:
            await message.reply(
                view=ErrorUI(f"**{error}**"),
                mention_author=False,
                allowed_mentions=NO_MENTIONS,
            )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            await command_store.delete_guild(guild.id)
            await module_config.clear_module(guild.id, "tags")
        except Exception:
            log.exception(
                "failed to clean up custom commands for departed guild %s", guild.id
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CustomCommandsCog(bot))
