import logging

import discord

from globals import PRIMARY, SECONDARY
from helpers import reactionroles as rr

from .views import GalleryWithItem, SmallSeparator, send_error

log = logging.getLogger(__name__)

PRIMARY_COLOR = discord.Color.from_str(PRIMARY)
EDITOR_COLOR = discord.Color.from_str(SECONDARY)
EDITOR_TIMEOUT = 900

BUTTON_STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}
STYLE_CHOICES = [
    ("primary", "Blue"),
    ("secondary", "Grey"),
    ("success", "Green"),
    ("danger", "Red"),
]
MODE_CHOICES = [
    ("toggle", "Toggle (add or remove)"),
    ("add", "Add only"),
    ("remove", "Remove only"),
]
KIND_CHOICES = [
    ("multi", "Multi-select"),
    ("single", "Single-select"),
]
ROW_KIND_LABEL = {
    rr.KIND_BUTTONS: "Buttons",
    rr.KIND_MULTI: "Multi-select",
    rr.KIND_SINGLE: "Single-select",
}
NO_ITEMS = "none"


def _render(text: str, server_name: str) -> str:
    return rr.render_text(text, server_name) or ""


def _choices(pairs, current: str) -> list[discord.SelectOption]:
    return [discord.SelectOption(label=label, value=value, default=value == current) for value, label in pairs]


def panel_items(
    panel: rr.Panel,
    server_name: str,
    *,
    compact: bool,
    make_button,
    make_select,
) -> list[discord.ui.Item]:
    items: list[discord.ui.Item] = []
    header_parts = []
    if panel.title:
        header_parts.append(f"## {_render(panel.title, server_name)}")
    if panel.body:
        header_parts.append(_render(panel.body, server_name))
    if header_parts:
        items.append(discord.ui.TextDisplay("\n".join(header_parts)))
    if panel.image_url:
        items.append(GalleryWithItem(panel.image_url))

    rows = [r for r in panel.rows if r.options]
    if rows and items:
        items.append(SmallSeparator())
    for row in rows:
        if compact or row.kind != rr.KIND_BUTTONS:
            children = [make_select(row)]
        else:
            children = [make_button(row, option) for option in row.options]
        items.append(discord.ui.ActionRow(*children))

    if panel.footer:
        items.append(SmallSeparator())
        items.append(discord.ui.TextDisplay(_render(panel.footer, server_name)))
    return items


def count_components(item) -> int:
    children = getattr(item, "children", None)
    if children is None:
        return 1
    return 1 + sum(count_components(child) for child in children)


class PanelButton(discord.ui.Button):
    def __init__(self, cog, panel_id: int, option: rr.Option) -> None:
        super().__init__(
            label=option.label,
            style=BUTTON_STYLES.get(option.style, discord.ButtonStyle.secondary),
            custom_id=rr.button_id(panel_id, option.id),
            emoji=option.emoji,
        )
        self.cog = cog
        self.panel_id = panel_id
        self.option_id = option.id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.button_clicked(interaction, self.panel_id, self.option_id)


class PanelSelect(discord.ui.Select):
    def __init__(self, cog, panel_id: int, row: rr.Row) -> None:
        options = [
            discord.SelectOption(label=o.label, value=str(o.id), description=o.description, emoji=o.emoji)
            for o in row.options
        ]
        max_values = max(1, min(row.max_values, len(options)))
        super().__init__(
            custom_id=rr.select_id(panel_id, row.id),
            placeholder=row.placeholder,
            min_values=min(row.min_values, max_values),
            max_values=max_values,
            options=options,
        )
        self.cog = cog
        self.panel_id = panel_id
        self.row_id = row.id

    async def callback(self, interaction: discord.Interaction) -> None:
        chosen = frozenset(int(value) for value in self.values)
        await self.cog.select_changed(interaction, self.panel_id, self.row_id, chosen)


class PanelView(discord.ui.LayoutView):
    def __init__(self, cog, panel: rr.Panel, server_name: str) -> None:
        super().__init__(timeout=None)
        items = panel_items(
            panel,
            server_name,
            compact=False,
            make_button=lambda row, option: PanelButton(cog, panel.id, option),
            make_select=lambda row: PanelSelect(cog, panel.id, row),
        )
        color = discord.Color(panel.color) if panel.color is not None else PRIMARY_COLOR
        self.add_item(discord.ui.Container(*items, accent_color=color))


class EditorButton(discord.ui.Button):
    def __init__(self, session: "EditorSession", option: rr.Option) -> None:
        super().__init__(
            label=option.label,
            style=BUTTON_STYLES.get(option.style, discord.ButtonStyle.secondary),
            custom_id=f"rre:b:{option.id}",
            emoji=option.emoji,
        )
        self.session = session
        self.option_id = option.id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.session.open_option(interaction, self.option_id)


class EditorSelect(discord.ui.Select):
    def __init__(self, session: "EditorSession", row: rr.Row) -> None:
        options = [
            discord.SelectOption(label=o.label, value=str(o.id), description=o.description, emoji=o.emoji)
            for o in row.options
        ]
        super().__init__(
            custom_id=f"rre:s:{row.id}",
            placeholder="Pick an option to edit it",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.session = session

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.session.open_option(interaction, int(self.values[0]))


class ActionButton(discord.ui.Button):
    def __init__(self, session, name, label, style, handler, *, disabled: bool = False) -> None:
        super().__init__(label=label, style=style, custom_id=f"rre:{name}", disabled=disabled)
        self.session = session
        self.handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.handler(self.session, interaction)


class ActionSelect(discord.ui.Select):
    def __init__(self, session, name, placeholder, options, handler) -> None:
        empty = not options
        super().__init__(
            custom_id=f"rre:{name}",
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options or [discord.SelectOption(label="Nothing here yet", value=NO_ITEMS)],
            disabled=empty,
        )
        self.session = session
        self.handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.handler(self.session, interaction, self.values[0])


class RowRole(discord.ui.RoleSelect):
    def __init__(self, session, row_id: int) -> None:
        super().__init__(
            custom_id="rre:role",
            placeholder="Add a role to this row",
            min_values=1,
            max_values=1,
        )
        self.session = session
        self.row_id = row_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.session.row_pick_role(interaction, self.row_id, self.values[0])


class ClosedView(discord.ui.LayoutView):
    def __init__(self, title: str, subtitle: str, color: discord.Color) -> None:
        super().__init__(timeout=60)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"# {title}\n{subtitle}"),
                accent_color=color,
            ),
        )


class EditorSession:
    def __init__(self, service, panel: rr.Panel, owner_id: int) -> None:
        self.service = service
        self.owner_id = owner_id
        self.guild_id = panel.guild_id
        self.original = panel
        self.panel = panel
        self.notice: str | None = None
        self.interaction: discord.Interaction | None = None
        self.view: EditorView | None = None
        self.row_id: int | None = None
        self.row_interaction: discord.Interaction | None = None
        self.row_view: RowEditorView | None = None

    @property
    def dirty(self) -> bool:
        return self.panel != self.original

    @property
    def is_draft(self) -> bool:
        return not self.panel.published

    def server_name(self) -> str:
        guild = self.service.bot.get_guild(self.guild_id)
        return guild.name if guild else "this server"

    def is_owner(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        perms = getattr(user, "guild_permissions", None)
        return user.id == self.owner_id and bool(perms and perms.manage_roles)

    def is_dropdown(self, option_id: int) -> bool:
        for row in self.panel.rows:
            if any(o.id == option_id for o in row.options):
                return row.kind != rr.KIND_BUTTONS
        return False

    def _change(self, fn, *args, **kwargs) -> bool:
        try:
            self.panel = fn(self.panel, *args, **kwargs)
        except ValueError as exc:
            self.notice = str(exc)
            return False
        self.notice = None
        return True

    def _fresh_main(self) -> "EditorView":
        old = self.view
        self.view = EditorView(self)
        if old is not None:
            old.stop()
        return self.view

    def _fresh_row(self) -> "RowEditorView | None":
        if self.row_id is None or self.panel.row(self.row_id) is None:
            return None
        old = self.row_view
        self.row_view = RowEditorView(self, self.row_id)
        if old is not None:
            old.stop()
        return self.row_view

    def _forget_row(self) -> None:
        if self.row_view is not None:
            self.row_view.stop()
        self.row_id = None
        self.row_view = None
        self.row_interaction = None

    async def _refresh_main(self) -> None:
        if self.interaction is None:
            return
        try:
            await self.interaction.edit_original_response(view=self._fresh_main())
        except discord.HTTPException:
            log.warning("Couldn't refresh the reaction role editor", exc_info=True)

    async def _refresh_row(self) -> None:
        if self.row_interaction is None:
            return
        view = self._fresh_row()
        if view is None:
            closed = ClosedView("Row closed", "That row no longer exists.", discord.Color.red())
            self._forget_row()
            try:
                await self.row_interaction.edit_original_response(view=closed)
            except discord.HTTPException:
                log.warning("Couldn't close a reaction role row editor", exc_info=True)
            return
        try:
            await self.row_interaction.edit_original_response(view=view)
        except discord.HTTPException:
            log.warning("Couldn't refresh a reaction role row editor", exc_info=True)

    async def refresh(self) -> None:
        await self._refresh_main()
        await self._refresh_row()

    async def _respond_main(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=self._fresh_main())
        await self._refresh_row()

    async def _respond_row(self, interaction: discord.Interaction) -> None:
        view = self._fresh_row()
        if view is None:
            self._forget_row()
            await interaction.response.edit_message(
                view=ClosedView("Row closed", "That row no longer exists.", discord.Color.red()),
            )
        else:
            await interaction.response.edit_message(view=view)
        await self._refresh_main()

    async def commit(self, interaction: discord.Interaction, fn, *args, **kwargs) -> None:
        if not self._change(fn, *args, **kwargs):
            await send_error(interaction, self.notice or "That didn't work.")
            self.notice = None
            return
        await interaction.response.defer()
        await self.refresh()

    async def open_text(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TextModal(self))

    async def open_option(self, interaction: discord.Interaction, option_id: int) -> None:
        option = self.panel.option(option_id)
        if option is None:
            self.notice = "That option is gone."
            await self._respond_main(interaction)
            return
        await interaction.response.send_modal(OptionModal(self, option, dropdown=self.is_dropdown(option_id)))

    async def open_add_row(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddRowModal(self))

    async def open_row(self, interaction: discord.Interaction, row_id: int) -> None:
        if self.panel.row(row_id) is None:
            self.notice = "That row is gone."
            await self._respond_main(interaction)
            return
        self._forget_row()
        self.row_id = row_id
        self.row_interaction = interaction
        self.row_view = RowEditorView(self, row_id)
        await interaction.response.send_message(view=self.row_view, ephemeral=True)

    async def close_row(self, interaction: discord.Interaction) -> None:
        self._forget_row()
        await interaction.response.edit_message(
            view=ClosedView("Row closed", "Your changes stay in the editor until you apply them.", EDITOR_COLOR),
        )
        await self._refresh_main()

    async def row_pick_role(self, interaction: discord.Interaction, row_id: int, role: discord.Role) -> None:
        error = self.service.check_role(interaction.guild, interaction.user, role)
        if error:
            self.notice = error
            await self._respond_row(interaction)
            return
        row = self.panel.row(row_id)
        await interaction.response.send_modal(NewOptionModal(self, row_id, role, dropdown=row.kind != rr.KIND_BUTTONS))

    async def row_remove_option(self, interaction: discord.Interaction, row_id: int, option_id: int) -> None:
        self._change(rr.remove_option, option_id)
        await self._respond_row(interaction)

    async def row_open_rules(self, interaction: discord.Interaction, option_id: int) -> None:
        option = self.panel.option(option_id)
        if option is None:
            self.notice = "That option is gone."
            await self._respond_row(interaction)
            return
        await interaction.response.send_modal(RulesModal(self, option))

    async def row_settings(self, interaction: discord.Interaction, row_id: int) -> None:
        row = self.panel.row(row_id)
        if row is None:
            self.notice = "That row is gone."
            await self._respond_row(interaction)
            return
        if row.kind == rr.KIND_BUTTONS:
            self.notice = "Button rows don't have settings. Their buttons are edited in the preview."
            await self._respond_row(interaction)
            return
        await interaction.response.send_modal(RowModal(self, row))

    async def row_remove(self, interaction: discord.Interaction, row_id: int) -> None:
        if self._change(rr.remove_row, row_id):
            self._forget_row()
            await interaction.response.edit_message(
                view=ClosedView("Row removed", "Apply to keep the change.", EDITOR_COLOR),
            )
            await self._refresh_main()
            return
        await self._respond_row(interaction)

    async def apply(self, interaction: discord.Interaction) -> None:
        try:
            saved, problem = await self.service.save_panel(self.panel)
        except ValueError as exc:
            self.notice = str(exc)
            await self._respond_main(interaction)
            return
        self.panel = self.original = saved
        self.notice = problem or "Changes applied."
        await self._respond_main(interaction)

    async def discard(self, interaction: discord.Interaction) -> None:
        self.panel = self.original
        self.notice = "Changes discarded."
        await self._respond_main(interaction)

    async def open_publish(self, interaction: discord.Interaction) -> None:
        if self.dirty:
            self.notice = "Apply your changes before publishing."
            await self._respond_main(interaction)
            return
        if not self.panel.options:
            self.notice = "Add at least one role before publishing."
            await self._respond_main(interaction)
            return
        await interaction.response.send_modal(PublishModal(self))

    async def publish_from_modal(self, interaction: discord.Interaction, channel) -> None:
        if not isinstance(channel, discord.TextChannel):
            await send_error(interaction, "Pick a text channel.")
            return
        if self.dirty:
            await send_error(interaction, "Apply your changes before publishing.")
            return
        try:
            message = await self.service.publish_panel(self.panel, channel)
        except ValueError as exc:
            await send_error(interaction, str(exc))
            return
        except discord.HTTPException:
            await send_error(interaction, f"I couldn't post the panel in {channel.mention}.")
            return
        fresh = await self.service.reload(self.panel.id)
        self.panel = self.original = fresh or self.panel
        await interaction.response.defer()
        await self._end(
            "Published",
            f"The panel is live in {channel.mention}.\n{message.jump_url}",
            discord.Color.green(),
        )

    async def close(self, interaction: discord.Interaction) -> None:
        was_dirty = self.dirty
        self.panel = self.original
        self._stop_main()
        await self._close_row_editor()
        subtitle = "Unapplied changes were discarded." if was_dirty else "Your saved panel is unchanged."
        await interaction.response.edit_message(
            view=ClosedView("Editor closed", subtitle, EDITOR_COLOR),
        )

    def _stop_main(self) -> None:
        if self.view is not None:
            self.view.stop()
        self.view = None

    async def _close_row_editor(self) -> None:
        if self.row_interaction is not None:
            try:
                await self.row_interaction.edit_original_response(
                    view=ClosedView("Editor closed", "This row editor was closed with the panel editor.", EDITOR_COLOR),
                )
            except discord.HTTPException:
                log.warning("Couldn't close a reaction role row editor", exc_info=True)
        self._forget_row()

    async def _end(self, title: str, subtitle: str, color: discord.Color) -> None:
        self._stop_main()
        await self._close_row_editor()
        if self.interaction is None:
            return
        try:
            await self.interaction.edit_original_response(view=ClosedView(title, subtitle, color))
        except discord.HTTPException:
            log.warning("Couldn't close the reaction role editor", exc_info=True)


async def open_editor(service, interaction: discord.Interaction, panel: rr.Panel) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    session = EditorSession(service, panel, interaction.user.id)
    session.interaction = interaction
    await interaction.edit_original_response(view=session._fresh_main())


class OwnedView(discord.ui.LayoutView):
    session: EditorSession

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.session.is_owner(interaction):
            return True
        await send_error(interaction, "Only the person who opened this editor can use it.")
        return False


class EditorView(OwnedView):
    def __init__(self, session: EditorSession) -> None:
        super().__init__(timeout=EDITOR_TIMEOUT)
        self.session = session
        panel = session.panel
        server = session.server_name()

        def preview(compact: bool) -> discord.ui.Container:
            items = panel_items(
                panel,
                server,
                compact=compact,
                make_button=lambda row, option: EditorButton(session, option),
                make_select=lambda row: EditorSelect(session, row),
            )
            color = discord.Color(panel.color) if panel.color is not None else PRIMARY_COLOR
            return discord.ui.Container(*items, accent_color=color)

        controls_size = count_components(discord.ui.Container(*_main_controls(session, compact=False)))
        full = preview(compact=False)
        compact = count_components(full) + controls_size > rr.MAX_COMPONENTS
        if compact:
            full = preview(compact=True)

        self.add_item(full)
        self.add_item(discord.ui.Container(*_main_controls(session, compact=compact), accent_color=EDITOR_COLOR))


def _main_controls(session: EditorSession, *, compact: bool) -> list[discord.ui.Item]:
    panel = session.panel
    lines = ["### Editing"]
    if not panel.rows:
        lines.append("Add a row to start adding roles.")
    if compact:
        lines.append("-# This panel is too big to show in full here, so the preview uses dropdowns.")
    if session.dirty:
        lines.append("-# Unsaved changes.")
    if session.notice:
        lines.append(f"**{session.notice}**")

    full = len(panel.rows) >= rr.MAX_ROWS
    row_options = [
        discord.SelectOption(
            label=f"Row {i} · {ROW_KIND_LABEL[r.kind]} · {len(r.options)}",
            value=str(r.id),
        )
        for i, r in enumerate(panel.rows, 1)
    ]

    if session.dirty:
        state = [
            ActionButton(session, "apply", "Apply", discord.ButtonStyle.success, lambda s, i: s.apply(i)),
            ActionButton(session, "discard", "Discard", discord.ButtonStyle.danger, lambda s, i: s.discard(i)),
        ]
    else:
        state = []
        if session.is_draft:
            state.append(
                ActionButton(session, "publish", "Publish", discord.ButtonStyle.success, lambda s, i: s.open_publish(i)),
            )
        state.append(ActionButton(session, "close", "Close", discord.ButtonStyle.secondary, lambda s, i: s.close(i)))

    return [
        discord.ui.TextDisplay("\n".join(lines)),
        SmallSeparator(),
        discord.ui.ActionRow(
            ActionButton(session, "text", "Edit text", discord.ButtonStyle.secondary, lambda s, i: s.open_text(i)),
            ActionButton(
                session,
                "addrow",
                "Add row",
                discord.ButtonStyle.secondary,
                lambda s, i: s.open_add_row(i),
                disabled=full,
            ),
            *state,
        ),
        discord.ui.ActionRow(
            ActionSelect(session, "row", "Edit a row", row_options, lambda s, i, v: s.open_row(i, int(v))),
        ),
    ]


class RowEditorView(OwnedView):
    def __init__(self, session: EditorSession, row_id: int) -> None:
        super().__init__(timeout=EDITOR_TIMEOUT)
        self.session = session
        self.row_id = row_id
        row = session.panel.row(row_id)
        number = next(i for i, r in enumerate(session.panel.rows, 1) if r.id == row_id)

        lines = [f"### Row {number} · {ROW_KIND_LABEL[row.kind]}"]
        if not row.options:
            lines.append("No roles yet. Add one below.")
        for option in row.options:
            detail = [f"<@&{option.role_id}>"]
            if option.mode != rr.MODE_TOGGLE:
                detail.append("add only" if option.mode == rr.MODE_ADD else "remove only")
            if option.group:
                detail.append(f"group `{option.group}`")
            if option.required_role_id:
                detail.append(f"needs <@&{option.required_role_id}>")
            lines.append(f"- **{option.label}**: " + ", ".join(detail))
        if session.notice:
            lines.append(f"**{session.notice}**")

        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay("\n".join(lines)),
            SmallSeparator(),
            discord.ui.ActionRow(RowRole(session, row_id)),
            discord.ui.ActionRow(
                ActionSelect(
                    session,
                    "rowremove",
                    "Remove a role from this row",
                    [discord.SelectOption(label=o.label[:100], value=str(o.id)) for o in row.options],
                    lambda s, i, v: s.row_remove_option(i, row_id, int(v)),
                ),
            ),
            discord.ui.ActionRow(
                ActionSelect(
                    session,
                    "rules",
                    "Set the group or required role for a role",
                    [discord.SelectOption(label=o.label[:100], value=str(o.id)) for o in row.options],
                    lambda s, i, v: s.row_open_rules(i, int(v)),
                ),
            ),
            discord.ui.ActionRow(
                ActionButton(
                    session,
                    "rowsettings",
                    "Row settings",
                    discord.ButtonStyle.secondary,
                    lambda s, i: s.row_settings(i, row_id),
                    disabled=row.kind == rr.KIND_BUTTONS,
                ),
                ActionButton(
                    session,
                    "removerow",
                    "Remove row",
                    discord.ButtonStyle.danger,
                    lambda s, i: s.row_remove(i, row_id),
                ),
                ActionButton(
                    session,
                    "closerow",
                    "Close",
                    discord.ButtonStyle.secondary,
                    lambda s, i: s.close_row(i),
                ),
            ),
        ]
        self.add_item(discord.ui.Container(*items, accent_color=EDITOR_COLOR))


class PublishModal(discord.ui.Modal, title="Publish panel"):
    def __init__(self, session: EditorSession) -> None:
        super().__init__()
        self.session = session
        self.channel_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(text="Channel to post the panel in", component=self.channel_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.session.publish_from_modal(interaction, self.channel_select.values[0])


class TextModal(discord.ui.Modal, title="Panel text"):
    def __init__(self, session: EditorSession) -> None:
        super().__init__()
        self.session = session
        p = session.panel
        self.title_box = discord.ui.TextInput(label="Title", default=p.title, max_length=rr.MAX_TITLE)
        self.body_box = discord.ui.TextInput(
            label="Body ({server} becomes the server name)",
            default=p.body or None,
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=rr.MAX_BODY,
        )
        self.footer_box = discord.ui.TextInput(
            label="Footer (leave empty for none)",
            default=p.footer or None,
            required=False,
            max_length=rr.MAX_FOOTER,
        )
        self.color_box = discord.ui.TextInput(
            label="Color, like #f4a261 (leave empty for default)",
            default=f"#{p.color:06x}" if p.color is not None else None,
            required=False,
            max_length=7,
        )
        self.image_box = discord.ui.TextInput(
            label="Image link (https, leave empty for none)",
            default=p.image_url or None,
            required=False,
            max_length=rr.MAX_IMAGE_URL,
        )
        for box in (self.title_box, self.body_box, self.footer_box, self.color_box, self.image_box):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        color_text = self.color_box.value.strip()
        try:
            color = rr.parse_color(color_text) if color_text else None
        except ValueError:
            await send_error(interaction, "Colors look like `#f4a261`.")
            return
        await self.session.commit(
            interaction,
            rr.set_text,
            title=self.title_box.value.strip(),
            body=self.body_box.value or "",
            footer=self.footer_box.value.strip(),
            color=color,
            image_url=self.image_box.value.strip(),
        )


class OptionModal(discord.ui.Modal, title="Edit option"):
    def __init__(self, session: EditorSession, option: rr.Option, *, dropdown: bool) -> None:
        super().__init__()
        self.session = session
        self.option_id = option.id
        self.dropdown = dropdown
        self.original = option
        self.label_box = discord.ui.TextInput(label="Label", default=option.label, max_length=rr.MAX_LABEL)
        self.emoji_box = discord.ui.TextInput(
            label="Emoji (leave empty for none)",
            default=option.emoji or None,
            required=False,
            max_length=64,
        )
        self.add_item(self.label_box)
        self.add_item(self.emoji_box)
        if dropdown:
            self.description_box = discord.ui.TextInput(
                label="Description",
                default=option.description or None,
                required=False,
                max_length=rr.MAX_DESCRIPTION,
            )
            self.add_item(self.description_box)
        else:
            self.style_select = discord.ui.Select(
                options=_choices(STYLE_CHOICES, option.style),
                min_values=1,
                max_values=1,
            )
            self.add_item(discord.ui.Label(text="Button color", component=self.style_select))
        self.mode_select = discord.ui.Select(
            options=_choices(MODE_CHOICES, option.mode),
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(text="Mode", component=self.mode_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.dropdown:
            description = self.description_box.value or None
            style = self.original.style
        else:
            description = self.original.description
            style = self.style_select.values[0]
        await self.session.commit(
            interaction,
            rr.update_option,
            self.option_id,
            label=self.label_box.value,
            emoji=self.emoji_box.value or None,
            description=description,
            style=style,
            mode=self.mode_select.values[0],
        )


class NewOptionModal(discord.ui.Modal, title="Add role"):
    def __init__(self, session: EditorSession, row_id: int, role: discord.Role, *, dropdown: bool) -> None:
        super().__init__()
        self.session = session
        self.row_id = row_id
        self.role_id = role.id
        self.dropdown = dropdown
        self.label_box = discord.ui.TextInput(label="Label", default=role.name[:rr.MAX_LABEL], max_length=rr.MAX_LABEL)
        self.emoji_box = discord.ui.TextInput(label="Emoji (leave empty for none)", required=False, max_length=64)
        self.add_item(self.label_box)
        self.add_item(self.emoji_box)
        if dropdown:
            self.description_box = discord.ui.TextInput(
                label="Description",
                required=False,
                max_length=rr.MAX_DESCRIPTION,
            )
            self.add_item(self.description_box)
        else:
            self.style_select = discord.ui.Select(
                options=_choices(STYLE_CHOICES, rr.DEFAULT_STYLE),
                min_values=1,
                max_values=1,
            )
            self.add_item(discord.ui.Label(text="Button color", component=self.style_select))
        self.mode_select = discord.ui.Select(
            options=_choices(MODE_CHOICES, rr.MODE_TOGGLE),
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(text="Mode", component=self.mode_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.session.commit(
            interaction,
            rr.add_option,
            self.row_id,
            role_id=self.role_id,
            label=self.label_box.value,
            emoji=self.emoji_box.value or None,
            description=(self.description_box.value or None) if self.dropdown else None,
            style=rr.DEFAULT_STYLE if self.dropdown else self.style_select.values[0],
            mode=self.mode_select.values[0],
            group=None,
            required_role_id=None,
        )


class RulesModal(discord.ui.Modal, title="Option rules"):
    def __init__(self, session: EditorSession, option: rr.Option) -> None:
        super().__init__()
        self.session = session
        self.option_id = option.id
        self.group_box = discord.ui.TextInput(
            label="Group (options sharing a group swap)",
            default=option.group or None,
            required=False,
            max_length=rr.MAX_GROUP,
        )
        current = f"Currently <@&{option.required_role_id}>" if option.required_role_id else "No requirement"
        self.required_select = discord.ui.RoleSelect(min_values=0, max_values=1, required=False)
        self.add_item(self.group_box)
        self.add_item(
            discord.ui.Label(
                text="Required role (members must already have it)",
                description=current,
                component=self.required_select,
            ),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        roles = list(self.required_select.values)
        if roles and roles[0].is_default():
            await send_error(interaction, "The @everyone role can't be a requirement.")
            return
        await self.session.commit(
            interaction,
            rr.set_rules,
            self.option_id,
            group=self.group_box.value or None,
            required_role_id=roles[0].id if roles else None,
        )


class AddRowModal(discord.ui.Modal, title="Add row"):
    def __init__(self, session: EditorSession) -> None:
        super().__init__()
        self.session = session
        self.kind_select = discord.ui.Select(
            options=[
                discord.SelectOption(label="Buttons", value=rr.KIND_BUTTONS, description="Up to 5 buttons"),
                discord.SelectOption(label="Multi-select dropdown", value=rr.KIND_MULTI, description="Members pick several"),
                discord.SelectOption(label="Single-select dropdown", value=rr.KIND_SINGLE, description="Members pick one"),
            ],
            min_values=1,
            max_values=1,
        )
        self.placeholder_box = discord.ui.TextInput(
            label="Placeholder (dropdowns only)",
            required=False,
            max_length=rr.MAX_PLACEHOLDER,
        )
        self.min_box = discord.ui.TextInput(
            label="Fewest picks allowed (dropdowns, 0 to 25)",
            default="0",
            required=False,
            max_length=2,
        )
        self.max_box = discord.ui.TextInput(
            label="Most picks allowed (dropdowns, 1 to 25)",
            default=str(rr.MAX_SELECT_OPTIONS),
            required=False,
            max_length=2,
        )
        self.add_item(discord.ui.Label(text="Row type", component=self.kind_select))
        self.add_item(self.placeholder_box)
        self.add_item(self.min_box)
        self.add_item(self.max_box)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        kind = self.kind_select.values[0]
        placeholder = self.placeholder_box.value or None
        if kind == rr.KIND_BUTTONS:
            await self.session.commit(interaction, rr.add_row, kind=kind, placeholder=None, lo=0, hi=1)
            return
        try:
            lo = int(self.min_box.value or 0)
            hi = int(self.max_box.value or rr.MAX_SELECT_OPTIONS)
        except ValueError:
            await send_error(interaction, "Min and max choices must be whole numbers.")
            return
        await self.session.commit(interaction, rr.add_row, kind=kind, placeholder=placeholder, lo=lo, hi=hi)


class RowModal(discord.ui.Modal, title="Dropdown row"):
    def __init__(self, session: EditorSession, row: rr.Row) -> None:
        super().__init__()
        self.session = session
        self.row = row
        self.placeholder_box = discord.ui.TextInput(
            label="Placeholder (shown before anything is picked)",
            default=row.placeholder or None,
            required=False,
            max_length=rr.MAX_PLACEHOLDER,
        )
        self.add_item(self.placeholder_box)
        self.multi = row.kind == rr.KIND_MULTI
        if self.multi:
            self.min_box = discord.ui.TextInput(
                label="Fewest picks allowed (0 to 25)",
                default=str(row.min_values),
                max_length=2,
            )
            self.max_box = discord.ui.TextInput(
                label="Most picks allowed (1 to 25)",
                default=str(row.max_values),
                max_length=2,
            )
            self.add_item(self.min_box)
            self.add_item(self.max_box)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lo, hi = 0, 1
        if self.multi:
            try:
                lo = int(self.min_box.value or 0)
                hi = int(self.max_box.value or rr.MAX_SELECT_OPTIONS)
            except ValueError:
                await send_error(interaction, "Min and max choices must be whole numbers.")
                return
        await self.session.commit(
            interaction,
            rr.update_row,
            self.row.id,
            kind=self.row.kind,
            placeholder=self.placeholder_box.value or None,
            lo=lo,
            hi=hi,
        )
