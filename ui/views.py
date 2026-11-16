from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_registry
import module_settings
from globals import (
    BROWSER,
    ERROR_MESSAGE,
    INVITE_URL,
    MELVIN_CHECK_EMOJI,
    MELVIN_CROSS_EMOJI,
    MELVIN_EMOJI,
    MELVIN_MISC_EMOJI,
    MELVIN_WARN_EMOJI,
    PRIMARY,
    SECONDARY,
    TERTIARY,
    THUMBS_UP,
    WEBSITE_URL,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

HIDDEN_COGS = frozenset({"private"})
CORE_PAGE = "melvin"

PRIMARY_COLOR = discord.Color.from_str(PRIMARY)
SECONDARY_COLOR = discord.Color.from_str(SECONDARY)
TERTIARY_COLOR = discord.Color.from_str(TERTIARY)

CASE_FILTERS = (
    ("All Actions", "all", "View all moderation cases."),
    ("Warns", "warn", "View warning cases."),
    ("Mutes", "mute", "View mute cases."),
    ("Kicks", "kick", "View kick cases."),
    ("Bans", "ban", "View ban cases."),
    ("Role Add", "role_add", "View role addition cases."),
    ("Role Remove", "role_remove", "View role removal cases."),
)


class SmallSeparator(discord.ui.Separator):
    def __init__(self) -> None:
        super().__init__(spacing=discord.SeparatorSpacing.small)


class LargeSeparator(discord.ui.Separator):
    def __init__(self) -> None:
        super().__init__(spacing=discord.SeparatorSpacing.large)


class GalleryWithItem(discord.ui.MediaGallery):
    def __init__(
        self,
        media: str | discord.File | discord.UnfurledMediaItem,
        /,
    ) -> None:
        super().__init__(discord.MediaGalleryItem(media))


def get_cog_commands(cog: commands.Cog) -> list:
    group = getattr(cog, "__cog_app_commands_group__", None)
    return group.commands if group is not None else cog.get_app_commands()


def _flatten(cmd: object) -> Iterator:
    if isinstance(cmd, app_commands.Group):
        for sub in cmd.commands:
            yield from _flatten(sub)
    else:
        yield cmd


def docs_url(page: str, cmd: app_commands.Command | None = None) -> str:
    url = f"{WEBSITE_URL}/docs/{page}"
    if cmd is None:
        return url
    return f"{url}#{cmd.qualified_name.replace(' ', '-')}"


@dataclass(frozen=True)
class HelpPage:
    key: str
    label: str
    description: str
    commands: tuple[app_commands.Command, ...]


def help_pages(
    bot: commands.Bot,
    hidden: set[str] | frozenset[str],
) -> list[HelpPage]:
    pages = []
    for cog in bot.cogs.values():
        key = cog.__cog_group_name__
        if key in hidden or key in HIDDEN_COGS:
            continue
        cmds = tuple(cmd for top in get_cog_commands(cog) for cmd in _flatten(top))
        if not cmds:
            continue
        label, description = module_registry.MODULES.get(
            key,
            (key.title(), cog.__cog_group_description__),
        )
        pages.append(
            HelpPage(key, label, "" if description == "…" else description, cmds),
        )
    pages.sort(key=lambda page: page.label.lower())

    core = tuple(
        cmd
        for cmd in bot.tree.get_commands()
        if isinstance(cmd, app_commands.Command) and cmd.binding is None
    )
    if core:
        pages.insert(
            0,
            HelpPage(CORE_PAGE, "Melvin", "Commands registered outside modules.", core),
        )
    return pages


def help_title(page: HelpPage) -> str:
    title = f"# {MELVIN_EMOJI} {page.label}"
    return f"{title}\n-# **{page.description}**" if page.description else title


def help_commands(page: HelpPage) -> str:
    return "\n".join(
        f"**[/{cmd.qualified_name}]({docs_url(page.key, cmd)})**\n-# **{cmd.description}**"
        for cmd in page.commands
    )


HELP_TIMEOUT = 300


class HelpSelect(discord.ui.Select):
    def __init__(self, pages: list[HelpPage]) -> None:
        super().__init__(
            placeholder="Select a category.",
            options=[
                discord.SelectOption(
                    label=page.label,
                    value=page.key,
                    description=page.description[:100] or None,
                )
                for page in pages
            ],
            custom_id="help_view:cog_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.view, HelpView):
            return
        hidden = (
            await module_settings.disabled_modules(interaction.guild_id)
            if interaction.guild_id is not None
            else set()
        )
        view = HelpView(self.view.bot, hidden)
        key = self.values[0]
        view.show(key if key in view.pages else next(iter(view.pages)))
        await interaction.response.edit_message(view=view)


class HelpView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        hidden: set[str] | frozenset[str] = frozenset(),
        *,
        timeout: float | None = HELP_TIMEOUT,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.pages = {page.key: page for page in help_pages(bot, hidden)}

        if not self.pages:
            self.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay("No commands available."),
                    SmallSeparator(),
                ),
            )
            return

        self.title_text = discord.ui.TextDisplay("")
        self.docs_button = discord.ui.Button(
            label="Docs",
            style=discord.ButtonStyle.link,
            url=WEBSITE_URL,
            emoji=BROWSER,
        )
        self.commands_text = discord.ui.TextDisplay("")
        self.page_select = HelpSelect(list(self.pages.values()))

        self.add_item(
            discord.ui.Container(
                discord.ui.Section(self.title_text, accessory=self.docs_button),
                SmallSeparator(),
                self.commands_text,
                SmallSeparator(),
                discord.ui.ActionRow(self.page_select),
            ),
        )
        self.show(next(iter(self.pages)))

    def show(self, key: str) -> None:
        page = self.pages[key]
        self.title_text.content = help_title(page)
        self.commands_text.content = help_commands(page)
        self.docs_button.url = docs_url(page.key)
        for option in self.page_select.options:
            option.default = option.value == key


class CaseRemoveButton(discord.ui.Button):
    def __init__(
        self,
        case_id: int,
        target_user: discord.User | discord.Member,
        db_path: str,
    ) -> None:
        super().__init__(
            label="Remove",
            style=discord.ButtonStyle.secondary,
            custom_id=f"cases_view:remove:{case_id}",
        )
        self.case_id = case_id
        self.target_user = target_user
        self.db_path = db_path

    async def callback(self, interaction: discord.Interaction) -> None:
        if (
            isinstance(interaction.user, discord.Member)
            and not interaction.user.guild_permissions.moderate_members
        ):
            await interaction.response.send_message(
                "**You lack permissions to remove cases.**",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "DELETE FROM mod_cases WHERE guild_id = ? AND case_id = ?",
                (interaction.guild_id, self.case_id),
            )
            await conn.commit()

        if isinstance(self.view, CasesView):
            await self.view.refresh(interaction)


class CaseActionSelect(discord.ui.Select):
    def __init__(
        self,
        target_user: discord.User | discord.Member,
        db_path: str,
    ) -> None:
        self.target_user = target_user
        self.db_path = db_path
        super().__init__(
            placeholder="Select an action type.",
            options=[
                discord.SelectOption(label=label, value=value, description=description)
                for label, value, description in CASE_FILTERS
            ],
            custom_id="cases_view:action_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if isinstance(self.view, CasesView):
            self.view.current_action = self.values[0]
            await self.view.refresh(interaction)


class CasesView(discord.ui.LayoutView):
    def __init__(
        self,
        target_user: discord.User | discord.Member,
        db_path: str,
        current_action: str = "all",
    ) -> None:
        super().__init__(timeout=300)
        self.target_user = target_user
        self.db_path = db_path
        self.current_action = current_action
        self.container = discord.ui.Container()
        self.add_item(self.container)

    async def build_components(
        self,
        guild_id: int,
        viewer: discord.User | discord.Member,
        bot_user: discord.ClientUser,
    ) -> None:
        target = self.target_user
        if target.id == bot_user.id:
            possessive, who = "My", "me"
        elif target.id == viewer.id:
            possessive, who = "Your", "you"
        else:
            possessive, who = f"{target.mention}'s", target.mention

        async with (
            aiosqlite.connect(self.db_path) as conn,
            conn.execute(
                """
                SELECT case_id, action_type, reason, mod_id
                FROM mod_cases
                WHERE guild_id = ? AND user_id = ? AND (? = 'all' OR action_type = ?)
                ORDER BY case_id DESC LIMIT 5
                """,
                (guild_id, target.id, self.current_action, self.current_action),
            ) as cursor,
        ):
            rows = await cursor.fetchall()

        self.container.clear_items()
        self.container.add_item(
            discord.ui.TextDisplay(f"### {MELVIN_EMOJI} {possessive} Cases"),
        )
        self.container.add_item(SmallSeparator())

        if not rows:
            suffix = (
                ""
                if self.current_action == "all"
                else f" under filter {self.current_action}"
            )
            self.container.add_item(
                discord.ui.TextDisplay(f"**No cases found for {who}{suffix}.**"),
            )
        for case_id, action_type, reason, mod_id in rows:
            self.container.add_item(
                discord.ui.Section(
                    f"**#{case_id} {action_type} by <@{mod_id}>**\n-# **{reason}**",
                    accessory=CaseRemoveButton(case_id, target, self.db_path),
                ),
            )

        self.container.add_item(SmallSeparator())
        self.container.add_item(
            discord.ui.ActionRow(CaseActionSelect(target, self.db_path)),
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id or not interaction.client.user:
            return
        await self.build_components(
            interaction.guild_id,
            interaction.user,
            interaction.client.user,
        )
        await interaction.edit_original_response(view=self)


class _Card(discord.ui.LayoutView):
    def __init__(
        self,
        text: str,
        color: discord.Color | None = None,
    ) -> None:
        super().__init__()
        self.text_display = discord.ui.TextDisplay(text)
        self.container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
            accent_color=color,
        )
        self.add_item(self.container)


class GatedUI(_Card):
    def __init__(self) -> None:
        super().__init__(
            f"# {MELVIN_WARN_EMOJI} Gated\n"
            f"This command is gated. Please read our documentation in our [support server]({INVITE_URL}).",
            PRIMARY_COLOR,
        )


class ResponseUI(_Card):
    def __init__(self, subtitle: str, /) -> None:
        super().__init__(subtitle)


class InfoUI(_Card):
    def __init__(self, *, title: str, subtitle: str) -> None:
        super().__init__(f"# {MELVIN_MISC_EMOJI} {title}\n{subtitle}")


class PositiveUI(_Card):
    def __init__(self, *, title: str, subtitle: str) -> None:
        super().__init__(f"# {MELVIN_CHECK_EMOJI} {title}\n{subtitle}", SECONDARY_COLOR)


class ThankUI(_Card):
    def __init__(self, *, title: str, subtitle: str) -> None:
        super().__init__(f"# {THUMBS_UP} {title}\n{subtitle}", SECONDARY_COLOR)


class ErrorUI(_Card):
    def __init__(self, message: str) -> None:
        super().__init__(f"# {MELVIN_CROSS_EMOJI} Error\n\n{message}", TERTIARY_COLOR)


class ExceptionUI(ErrorUI):
    def __init__(self) -> None:
        super().__init__(ERROR_MESSAGE)


async def send_error(interaction: discord.Interaction, message: str) -> None:
    # an ephemeral error, whether or not the interaction was answered already
    view = ErrorUI(message)
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)
