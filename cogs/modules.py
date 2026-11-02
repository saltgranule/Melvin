import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import module_settings
from globals import ERROR_MESSAGE, MELVIN_CHECK_EMOJI, MELVIN_CROSS_EMOJI, MELVIN_EMOJI
from ui import ErrorUI, Paginator

if TYPE_CHECKING:
    import re

log = logging.getLogger(__name__)

PAGE_SIZE = 8
TITLE = f"# {MELVIN_EMOJI} Modules\n-# **Turn Melvin's features on or off for this server.**"
FILTERS = (
    ("all", "All modules", "Every module."),
    ("on", "Enabled", "Only modules that are on."),
    ("off", "Disabled", "Only modules that are off."),
)
FILTER_ID = "modules:filter"
TOGGLE_TEMPLATE = (
    r"modules:toggle:(?P<guild>\d+):(?P<module>[a-z0-9_]+):(?P<state>[01]):"
    r"(?P<filter>all|on|off)"
)


async def _reply_error(interaction: discord.Interaction, message: str) -> None:
    view = ErrorUI(message)
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


def _order(filter_by: str, disabled: set[str]) -> list[str]:
    keys = list(module_settings.MODULES)
    if filter_by == "on":
        keys = [key for key in keys if key not in disabled]
    elif filter_by == "off":
        keys = [key for key in keys if key in disabled]
    return sorted(keys, key=lambda key: key in disabled)


def _toggle_id(guild_id: int, module: str, enabled: bool, filter_by: str) -> str:
    return f"modules:toggle:{guild_id}:{module}:{int(enabled)}:{filter_by}"


def _toggle_look(enabled: bool) -> dict:
    return {
        "label": "On" if enabled else "Off",
        "emoji": MELVIN_CHECK_EMOJI if enabled else MELVIN_CROSS_EMOJI,
        "style": discord.ButtonStyle.secondary,
    }


async def _set_module(
    interaction: discord.Interaction,
    guild_id: int,
    module: str,
    enabled: bool,
) -> bool:
    if interaction.guild_id != guild_id:
        await _reply_error(interaction, "**This button belongs to another server.**")
        return False

    permissions = getattr(interaction.user, "guild_permissions", None)
    if not (permissions and permissions.manage_guild):
        await _reply_error(interaction, "**You do not have permission to do this.**")
        return False
    if module not in module_settings.MODULES:
        await _reply_error(interaction, ERROR_MESSAGE)
        return False

    try:
        await module_settings.set_enabled(guild_id, module, enabled=not enabled)
    except Exception:
        log.exception("Failed to toggle module %s in guild %s", module, guild_id)
        await _reply_error(interaction, ERROR_MESSAGE)
        return False
    return True


async def _show_filter(interaction: discord.Interaction, filter_by: str) -> None:
    if interaction.guild_id is None:
        return
    disabled = await module_settings.disabled_modules(interaction.guild_id)
    await interaction.response.edit_message(
        view=ModulesView(interaction.guild_id, disabled, filter_by=filter_by),
    )


class ToggleButton(discord.ui.Button["ModulesView"]):
    def __init__(
        self,
        guild_id: int,
        module: str,
        *,
        enabled: bool,
        filter_by: str,
    ) -> None:
        super().__init__(
            **_toggle_look(enabled),
            custom_id=_toggle_id(guild_id, module, enabled, filter_by),
        )
        self.guild_id = guild_id
        self.module = module
        self.enabled = enabled

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _set_module(interaction, self.guild_id, self.module, self.enabled):
            return

        view = self.view
        if not isinstance(view, ModulesView):
            return
        await view.refresh(reorder=False)
        await interaction.response.edit_message(view=view)


class ToggleDynamic(
    discord.ui.DynamicItem[discord.ui.Button],
    template=TOGGLE_TEMPLATE,
):
    def __init__(
        self,
        *,
        guild_id: int,
        module: str,
        enabled: bool,
        filter_by: str,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                **_toggle_look(enabled),
                custom_id=_toggle_id(guild_id, module, enabled, filter_by),
            ),
        )
        self.guild_id = guild_id
        self.module = module
        self.enabled = enabled
        self.filter_by = filter_by

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match: re.Match[str],
        /,
    ) -> ToggleDynamic:
        return cls(
            guild_id=int(match["guild"]),
            module=match["module"],
            enabled=match["state"] == "1",
            filter_by=match["filter"],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _set_module(interaction, self.guild_id, self.module, self.enabled):
            return

        disabled = await module_settings.disabled_modules(self.guild_id)
        await interaction.response.edit_message(
            view=ModulesView(self.guild_id, disabled, filter_by=self.filter_by),
        )


class FilterSelect(discord.ui.Select["ModulesView"]):
    def __init__(self, current: str) -> None:
        super().__init__(
            placeholder="Show modules",
            options=[
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    default=value == current,
                )
                for value, label, description in FILTERS
            ],
            custom_id=FILTER_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await _show_filter(interaction, self.values[0])


class FilterView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(FilterSelect("all"))


class ModulesView(Paginator):
    def __init__(
        self,
        guild_id: int,
        disabled: set[str],
        *,
        filter_by: str = "all",
        page: int = 0,
        order: list[str] | None = None,
    ) -> None:
        self.guild_id = guild_id
        self.filter_by = filter_by
        self.order = order if order is not None else _order(filter_by, disabled)
        super().__init__(
            TITLE,
            self._sections(disabled),
            data_name="modules",
            per_page=PAGE_SIZE,
            container=True,
            timeout=300,
        )
        self.add_over(discord.ui.ActionRow(FilterSelect(filter_by)))
        self.current_page = page
        self.update_data(TITLE, self._sections(disabled), keep_page=True)

    def _sections(self, disabled: set[str]) -> list[discord.ui.Section]:
        sections: list[discord.ui.Section] = []
        for key in self.order:
            label, description = module_settings.MODULES[key]
            sections.append(
                discord.ui.Section(
                    f"**{label}**\n-# {description}",
                    accessory=ToggleButton(
                        self.guild_id,
                        key,
                        enabled=key not in disabled,
                        filter_by=self.filter_by,
                    ),
                ),
            )
        return sections

    async def refresh(self, *, reorder: bool) -> None:
        disabled = await module_settings.disabled_modules(self.guild_id)
        if reorder:
            self.order = _order(self.filter_by, disabled)
        self.update_data(TITLE, self._sections(disabled), keep_page=not reorder)

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if isinstance(item, discord.ui.Button) and not isinstance(
                item,
                ToggleButton,
            ):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                with contextlib.suppress(discord.HTTPException):
                    await self.message.delete()

    @classmethod
    async def build(cls, guild_id: int) -> ModulesView:
        return cls(guild_id, await module_settings.disabled_modules(guild_id))


class ModulesCog(
    commands.Cog,
    name="modules",
    description="Turn Melvin's features on or off for a server.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(ToggleDynamic)
        self.bot.add_view(FilterView())

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(ToggleDynamic)

    @app_commands.command(
        name="modules",
        description="Turn Melvin's features on or off for this server.",
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modules(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        view = await ModulesView.build(interaction.guild.id)
        await interaction.response.send_message(view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModulesCog(bot))
