import asyncio
import logging
import time
import weakref

import discord
from discord import app_commands
from discord.ext import commands

import module_settings
from helpers import reactionroles as rr
from helpers.roles import (
    REACTION_ROLE_REASON,
    actor_role_error,
    assignable_error,
    bot_role_error,
)
from helpers.text import truncate
from module_registry import Module
from ui import InfoUI, PositiveUI, send_error
from ui.reactionroles import PanelView, open_editor

log = logging.getLogger(__name__)

KEY = "reactionroles"

MODULE = Module(
    KEY,
    "Reaction Roles",
    "Buttons and dropdowns that members click to get roles.",
)

STALE_PANEL = "This panel has changed. Ask a moderator to republish it."
COG_NAME = KEY

@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class ReactionRolesCog(
    commands.GroupCog,
    name=KEY,
    description="Build and manage role panels.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.store = rr.Store()
        self._panels: dict[int, rr.Panel] = {}
        self._by_message: dict[int, int] = {}
        self._locks = weakref.WeakValueDictionary()

    async def cog_load(self) -> None:
        await self.store.init()
        for panel in await self.store.all_panels():
            self._remember(panel)
            self._register(panel)
        try:
            self.bot.tree.add_command(edit_panel_menu)
        except app_commands.CommandAlreadyRegistered:
            pass

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(edit_panel_menu.name, type=edit_panel_menu.type)

    def _remember(self, panel: rr.Panel) -> None:
        self._forget(panel.id)
        self._panels[panel.id] = panel
        if panel.message_id is not None:
            self._by_message[panel.message_id] = panel.id

    def _forget(self, panel_id: int) -> None:
        old = self._panels.pop(panel_id, None)
        if old is not None and old.message_id is not None:
            self._by_message.pop(old.message_id, None)

    async def _get(self, panel_id: int) -> rr.Panel | None:
        panel = self._panels.get(panel_id)
        if panel is None:
            panel = await self.store.panel(panel_id)
            if panel is not None:
                self._remember(panel)
        return panel

    async def reload(self, panel_id: int) -> rr.Panel | None:
        panel = await self.store.panel(panel_id)
        self._forget(panel_id)
        if panel is not None:
            self._remember(panel)
        return panel

    def _lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        key = (guild_id, user_id)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def _server_name(self, guild_id: int) -> str:
        guild = self.bot.get_guild(guild_id)
        return guild.name if guild else "this server"

    def _view(self, panel: rr.Panel) -> PanelView:
        return PanelView(self, panel, self._server_name(panel.guild_id))

    def _register(self, panel: rr.Panel) -> None:
        if panel.message_id is None or not panel.options:
            return
        try:
            self.bot.add_view(self._view(panel), message_id=panel.message_id)
        except ValueError:
            log.exception("Couldn't register reaction role panel %s", panel.id)

    async def _channel(self, channel_id: int) -> discord.TextChannel | discord.Thread | None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return None
        return channel if isinstance(channel, (discord.TextChannel, discord.Thread)) else None

    async def _sync(self, panel: rr.Panel) -> str | None:
        if panel.message_id is None or panel.channel_id is None:
            return None
        channel = await self._channel(panel.channel_id)
        if channel is None:
            return "I can't reach that panel's channel, so its message wasn't updated."
        try:
            await channel.get_partial_message(panel.message_id).edit(
                view=self._view(panel),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.NotFound:
            return "That panel's message was deleted, so it wasn't updated."
        except discord.HTTPException:
            log.exception("Couldn't update reaction role panel %s", panel.id)
            return "I couldn't update the panel message."
        self._register(panel)
        return None

    def check_role(self, guild: discord.Guild, actor: discord.Member, role: discord.Role) -> str | None:
        return assignable_error(role) or actor_role_error(guild, actor, role) or bot_role_error(guild, role)

    async def save_panel(self, panel: rr.Panel) -> tuple[rr.Panel, str | None]:
        await self.store.save_panel(panel)
        saved = await self.reload(panel.id)
        if saved is None:
            raise ValueError("That panel was deleted while you were editing it.")
        problem = await self._sync(saved) if saved.published else None
        return saved, problem

    async def publish_panel(self, panel: rr.Panel, channel: discord.TextChannel) -> discord.Message:
        if panel.published:
            raise ValueError(
                f"Panel #{panel.id} is already live. Use `/reactionroles edit` to change it.",
            )
        if not panel.options:
            raise ValueError("Add at least one role to the panel before publishing it.")
        me = channel.guild.me
        perms = channel.permissions_for(me)
        if not (perms.view_channel and perms.send_messages):
            raise ValueError(f"I can't send messages in {channel.mention}.")

        message = await channel.send(
            view=self._view(panel),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self.store.update_panel(panel.id, channel_id=channel.id, message_id=message.id)
        fresh = await self.reload(panel.id)
        if fresh is not None:
            self._register(fresh)
        return message

    @app_commands.command(name="new", description="Start a reaction role panel and open the editor.")
    @app_commands.describe(title="The heading. You can change it in the editor.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def new(self, interaction: discord.Interaction, title: str = "New panel") -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            return
        title = title.strip() or "New panel"

        error = rr.text_error(title, None, None)
        if error is None and await self.store.count_in_guild(guild.id) >= rr.MAX_PANELS:
            error = f"This server can have {rr.MAX_PANELS} panels at most. Delete one first."
        if error:
            await send_error(interaction, error)
            return

        panel_id = await self.store.create_panel(
            guild_id=guild.id,
            created_by=interaction.user.id,
            title=title,
            body="",
            footer=None,
            color=None,
            image_url=None,
            created_at=int(time.time()),
        )
        panel = await self.reload(panel_id)
        if panel is None:
            await send_error(interaction, "Something went wrong creating that panel.")
            return
        await open_editor(self, interaction, panel)

    @app_commands.command(name="edit", description="Open the editor for a panel.")
    @app_commands.describe(
        panel="The panel ID from /reactionroles list.",
        message="Or the message ID or link of a live panel.",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def edit(
        self,
        interaction: discord.Interaction,
        panel: int | None = None,
        message: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if (panel is None) == (message is None):
            await send_error(interaction, "Give a panel ID or a message, not both.")
            return
        if message is not None:
            message_id = rr.parse_message_id(message)
            target = await self.store.panel_by_message(message_id) if message_id else None
        else:
            target = await self._get(panel)
        if target is None or target.guild_id != interaction.guild_id:
            await send_error(interaction, "There's no reaction role panel with that ID or message.")
            return
        await open_editor(self, interaction, target)

    async def open_editor_for_message(self, interaction: discord.Interaction, message_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        if not isinstance(user, discord.Member) or not user.guild_permissions.manage_roles:
            await send_error(interaction, "You need the Manage Roles permission to edit panels.")
            return
        target = await self.store.panel_by_message(message_id)
        if target is None or target.guild_id != interaction.guild_id:
            await send_error(interaction, "There's no reaction role panel on that message.")
            return
        await open_editor(self, interaction, target)

    @app_commands.command(name="publish", description="Post a panel in a channel.")
    @app_commands.describe(panel="The panel ID.", channel="The channel to post it in.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def publish(
        self,
        interaction: discord.Interaction,
        panel: int,
        channel: discord.TextChannel,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        target = await self._get(panel)
        if target is None or target.guild_id != interaction.guild_id:
            await send_error(interaction, "There's no panel with that ID in this server.")
            return
        try:
            message = await self.publish_panel(target, channel)
        except ValueError as exc:
            await send_error(interaction, str(exc))
            return
        except discord.HTTPException:
            await send_error(interaction, f"I couldn't post the panel in {channel.mention}.")
            return
        await interaction.followup.send(
            view=PositiveUI(
                title="Panel Published",
                subtitle=f"Panel **#{target.id}** is live in {channel.mention}.\n{message.jump_url}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="list", description="List this server's reaction role panels.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def list_panels(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            return

        panels = await self.store.panels_in_guild(guild.id)
        if not panels:
            subtitle = "No panels yet. Start one with `/reactionroles new`."
        else:
            lines = []
            for p in panels:
                status = f"live in <#{p.channel_id}>" if p.published else "draft"
                rows = len(p.rows)
                lines.append(f"**#{p.id}** {p.title}: {status}, {rows} row{'s' if rows != 1 else ''}")
            subtitle = truncate("\n".join(lines), 3900)
        await interaction.followup.send(
            view=InfoUI(title="Reaction Role Panels", subtitle=subtitle),
            ephemeral=True,
        )

    @app_commands.command(name="delete", description="Delete a panel and its message.")
    @app_commands.describe(panel="The panel ID.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def delete(self, interaction: discord.Interaction, panel: int) -> None:
        await interaction.response.defer(ephemeral=True)
        target = await self._get(panel)
        if target is None or target.guild_id != interaction.guild_id:
            await send_error(interaction, "There's no panel with that ID in this server.")
            return

        await self.store.delete_panel(target.id)
        self._forget(target.id)
        if target.message_id is not None and target.channel_id is not None:
            channel = await self._channel(target.channel_id)
            if channel is not None:
                try:
                    await channel.get_partial_message(target.message_id).delete()
                except discord.HTTPException:
                    pass
        await interaction.followup.send(
            view=PositiveUI(title="Panel Deleted", subtitle=f"Panel **#{target.id}** was deleted."),
            ephemeral=True,
        )

    async def _panel_choices(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[int]]:
        if interaction.guild is None:
            return []
        needle = current.lower()
        choices: list[app_commands.Choice[int]] = []
        for panel in sorted(self._panels.values(), key=lambda p: p.id):
            if panel.guild_id != interaction.guild.id:
                continue
            label = f"#{panel.id} {panel.title}" + ("" if panel.published else " (draft)")
            if needle in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=panel.id))
            if len(choices) == 25:
                break
        return choices

    edit.autocomplete("panel")(_panel_choices)
    publish.autocomplete("panel")(_panel_choices)
    delete.autocomplete("panel")(_panel_choices)

    async def button_clicked(
        self,
        interaction: discord.Interaction,
        panel_id: int,
        option_id: int,
    ) -> None:
        panel = await self._get(panel_id)
        option = panel.option(option_id) if panel else None
        if panel is None or option is None:
            await send_error(interaction, STALE_PANEL)
            return
        await self._apply(interaction, panel, lambda held: rr.plan_button(panel, option, held))

    async def select_changed(
        self,
        interaction: discord.Interaction,
        panel_id: int,
        row_id: int,
        chosen: frozenset[int],
    ) -> None:
        panel = await self._get(panel_id)
        row = panel.row(row_id) if panel else None
        if panel is None or row is None:
            await send_error(interaction, STALE_PANEL)
            return
        await self._apply(
            interaction,
            panel,
            lambda held: rr.plan_select(panel, row, chosen, held),
        )

    async def _apply(self, interaction: discord.Interaction, panel: rr.Panel, planner) -> None:
        guild = interaction.guild
        if guild is None or guild.id != panel.guild_id:
            await send_error(interaction, STALE_PANEL)
            return

        await interaction.response.defer(ephemeral=True)
        if not await module_settings.is_enabled(guild.id, KEY):
            await send_error(interaction, "Reaction roles are turned off in this server.")
            return

        user = interaction.user
        member = user if isinstance(user, discord.Member) else guild.get_member(user.id)
        if member is None:
            await send_error(interaction, "I couldn't find you in this server.")
            return

        async with self._lock(guild.id, member.id):
            held = frozenset(role.id for role in member.roles)
            plan = planner(held)
            if plan.error:
                await send_error(interaction, plan.error)
                return
            if not plan.changes:
                await interaction.followup.send(
                    view=InfoUI(title="No Change", subtitle=plan.notice or "Nothing changed."),
                    ephemeral=True,
                )
                return

            to_add, to_remove, problem = self._roles_for(guild, plan)
            if problem:
                await send_error(interaction, problem)
                return

            reason = f"{REACTION_ROLE_REASON}: panel #{panel.id}"
            try:
                if to_add:
                    await member.add_roles(*to_add, reason=reason)
                if to_remove:
                    await member.remove_roles(*to_remove, reason=reason)
            except discord.HTTPException:
                log.exception("Reaction role update failed in guild %s", guild.id)
                await send_error(interaction, "I couldn't update your roles. Please try again.")
                return

        lines = []
        if to_add:
            lines.append(f"**Added:** {', '.join(r.mention for r in to_add)}")
        if to_remove:
            lines.append(f"**Removed:** {', '.join(r.mention for r in to_remove)}")
        await interaction.followup.send(
            view=PositiveUI(title="Roles Updated", subtitle="\n".join(lines)),
            ephemeral=True,
        )

    @staticmethod
    def _roles_for(
        guild: discord.Guild,
        plan: rr.Plan,
    ) -> tuple[list[discord.Role], list[discord.Role], str | None]:
        if not guild.me.guild_permissions.manage_roles:
            return [], [], "I need the Manage Roles permission to do this."

        to_add: list[discord.Role] = []
        for role_id in plan.add:
            role = guild.get_role(role_id)
            if role is None:
                return [], [], STALE_PANEL
            if bot_role_error(guild, role) or role.managed:
                return [], [], (
                    f"I can't manage {role.mention} right now. A moderator needs to move "
                    "my role above it."
                )
            to_add.append(role)

        to_remove = [r for r in (guild.get_role(i) for i in plan.remove) if r is not None]
        for role in to_remove:
            if bot_role_error(guild, role):
                return [], [], (
                    f"I can't manage {role.mention} right now. A moderator needs to move "
                    "my role above it."
                )
        return to_add, to_remove, None

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        await self._drop_messages([payload.message_id])

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        await self._drop_messages(payload.message_ids)

    async def _drop_messages(self, message_ids) -> None:
        for message_id in message_ids:
            panel_id = self._by_message.get(message_id)
            if panel_id is None:
                continue
            self._forget(panel_id)
            await self.store.delete_panel(panel_id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        try:
            affected = await self.store.remove_role_from_guild(role.guild.id, role.id)
        except Exception:
            log.exception("Couldn't clean up reaction roles for deleted role %s", role.id)
            return
        for panel_id in affected:
            panel = await self.reload(panel_id)
            if panel is not None and panel.published:
                await self._sync(panel)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            for panel_id in await self.store.delete_guild(guild.id):
                self._forget(panel_id)
        except Exception:
            log.exception("Couldn't clean up reaction roles for guild %s", guild.id)

async def _edit_panel_menu(interaction: discord.Interaction, message: discord.Message) -> None:
    cog = interaction.client.get_cog(COG_NAME)
    if cog is None:
        await send_error(interaction, "Reaction roles isn't available right now.")
        return
    await cog.open_editor_for_message(interaction, message.id)

edit_panel_menu = app_commands.ContextMenu(
    name="Edit reaction panel",
    callback=_edit_panel_menu,
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
    allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReactionRolesCog(bot))
