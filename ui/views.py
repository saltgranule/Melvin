from dataclasses import dataclass

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_registry
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

# people dont need to see this
HIDDEN_COGS = frozenset({"private"})


def get_cog_commands(cog: commands.Cog) -> list:
    group = getattr(cog, "__cog_app_commands_group__", None)
    if group is not None:
        return group.commands
    return cog.get_app_commands()


def flatten_commands(cmd: object) -> list:
    if isinstance(cmd, discord.app_commands.Group):
        result = []
        for sub in cmd.commands:
            result.extend(flatten_commands(sub))
        return result
    return [cmd]


CORE_PAGE = "melvin"


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
        cmds = tuple(
            cmd
            for top_cmd in get_cog_commands(cog)
            for cmd in flatten_commands(top_cmd)
        )
        if not cmds or key in hidden or key in HIDDEN_COGS:
            continue
        label, description = module_registry.MODULES.get(
            key,
            (key.title(), cog.__cog_group_description__),
        )
        if description == "…":
            description = ""
        pages.append(HelpPage(key, label, description, cmds))
    pages.sort(key=lambda page: page.label.lower())

    core = tuple(
        cmd
        for cmd in bot.tree.get_commands()
        if isinstance(cmd, app_commands.Command) and cmd.binding is None
    )
    if core:
        pages.insert(
            0,
            # finally showing core cmds
            HelpPage(CORE_PAGE, "Melvin", "Commands registered outside modules.", core),
        )
    return pages


def help_title(page: HelpPage) -> str:
    lines = [f"# {MELVIN_EMOJI} {page.label}"]
    if page.description:
        lines.append(f"-# **{page.description}**")
    return "\n".join(lines)


def help_commands(page: HelpPage) -> str:
    return "\n".join(
        f"**[/{cmd.qualified_name}]({docs_url(page.key, cmd)})**\n-# **{cmd.description}**"
        for cmd in page.commands
    )


class HelpSelect(discord.ui.Select):
    def __init__(self, pages: list[HelpPage]) -> None:
        super().__init__(
            placeholder="Select a category.",
            min_values=1,
            max_values=1,
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
        if isinstance(self.view, HelpView):
            self.view.show(self.values[0])
            await interaction.response.edit_message(view=self.view)


class HelpView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        hidden: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(timeout=None)
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

        options = [
            discord.SelectOption(
                label="All Actions",
                value="all",
                description="View all moderation cases.",
            ),
            discord.SelectOption(
                label="Warns",
                value="warn",
                description="View warning cases.",
            ),
            discord.SelectOption(
                label="Mutes",
                value="mute",
                description="View mute cases.",
            ),
            discord.SelectOption(
                label="Kicks",
                value="kick",
                description="View kick cases.",
            ),
            discord.SelectOption(
                label="Bans",
                value="ban",
                description="View ban cases.",
            ),
            discord.SelectOption(
                label="Role Add",
                value="role_add",
                description="View role addition cases.",
            ),
            discord.SelectOption(
                label="Role Remove",
                value="role_remove",
                description="View role removal cases.",
            ),
        ]

        super().__init__(
            placeholder="Select an action type.",
            min_values=1,
            max_values=1,
            options=options,
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
        super().__init__(timeout=None)
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
        self.container.clear_items()

        if self.target_user.id == bot_user.id:
            possessive = "My"
        elif self.target_user.id == viewer.id:
            possessive = "Your"
        else:
            possessive = f"{self.target_user.mention}'s"

        header_text = f"### {MELVIN_EMOJI} {possessive} Cases"
        self.container.add_item(discord.ui.TextDisplay(header_text))
        self.container.add_item(
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )

        async with aiosqlite.connect(self.db_path) as conn:
            if self.current_action == "all":
                query = """
                    SELECT case_id, action_type, reason, mod_id
                    FROM mod_cases
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY case_id DESC LIMIT 5
                """
                params = (guild_id, self.target_user.id)
            else:
                query = """
                    SELECT case_id, action_type, reason, mod_id
                    FROM mod_cases
                    WHERE guild_id = ? AND user_id = ? AND action_type = ?
                    ORDER BY case_id DESC LIMIT 5
                """
                params = (guild_id, self.target_user.id, self.current_action)

            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            if self.target_user.id == bot_user.id:
                who = "me"
            elif self.target_user.id == viewer.id:
                who = "you"
            else:
                who = self.target_user.mention

            if self.current_action == "all":
                msg = f"**No cases found for {who}.**"
            else:
                msg = (
                    f"**No cases found for {who} under filter {self.current_action}.**"
                )
            self.container.add_item(discord.ui.TextDisplay(msg))
        else:
            for case_id, action_type, reason, mod_id in rows:
                content = (
                    f"**#{case_id} {action_type} by <@{mod_id}>**\n-# **{reason}**"
                )
                btn = CaseRemoveButton(case_id, self.target_user, self.db_path)
                section = discord.ui.Section(content, accessory=btn)
                self.container.add_item(section)

        self.container.add_item(
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )
        self.container.add_item(
            discord.ui.ActionRow(CaseActionSelect(self.target_user, self.db_path)),
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return

        if not interaction.client.user:
            return

        await self.build_components(
            interaction.guild_id,
            interaction.user,
            interaction.client.user,
        )
        await interaction.edit_original_response(view=self)


class ThinkingText(discord.ui.TextDisplay):
    def __init__(self) -> None:
        super().__init__(f"{MELVIN_EMOJI} **Thinking...**")


class SmallSeparator(discord.ui.Separator):
    def __init__(self) -> None:
        super().__init__(
            visible=True,
            spacing=discord.SeparatorSpacing.small,
        )


class LargeSeparator(discord.ui.Separator):
    def __init__(self) -> None:
        super().__init__(
            visible=True,
            spacing=discord.SeparatorSpacing.large,
        )


class GalleryWithItem(discord.ui.MediaGallery):
    def __init__(
        self,
        media: str | discord.File | discord.UnfurledMediaItem,
        /,
    ) -> None:
        super().__init__(discord.MediaGalleryItem(media))


class GatedUI(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__()
        self.text_display = discord.ui.TextDisplay(
            f"# {MELVIN_WARN_EMOJI} Gated\n"
            f"This command is gated. Please read our documentation in our [support server]({INVITE_URL}).",
        )

        container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
            accent_color=discord.Color.from_str(PRIMARY),
        )
        self.container = container
        self.add_item(container)


class ResponseUI(discord.ui.LayoutView):
    def __init__(self, subtitle: str, /) -> None:
        super().__init__()
        self.text_display = discord.ui.TextDisplay(subtitle)

        container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
        )
        self.container = container
        self.add_item(container)


class InfoUI(discord.ui.LayoutView):
    def __init__(self, *, title: str, subtitle: str) -> None:
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {MELVIN_MISC_EMOJI} {title}\n{subtitle}"),
            SmallSeparator(),
        )
        self.container = container
        self.add_item(container)


class PositiveUI(discord.ui.LayoutView):
    def __init__(self, *, title: str, subtitle: str) -> None:
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {MELVIN_CHECK_EMOJI} {title}\n{subtitle}"),
            SmallSeparator(),
            accent_color=discord.Color.from_str(SECONDARY),
        )
        self.container = container
        self.add_item(container)


# PositiveUI with a different emoji, since PositiveUI's emoji is hardcoded
class ThankUI(discord.ui.LayoutView):
    def __init__(self, *, title: str, subtitle: str) -> None:
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {THUMBS_UP} {title}\n{subtitle}"),
            SmallSeparator(),
            accent_color=discord.Color.from_str(SECONDARY),
        )
        self.container = container
        self.add_item(container)


class ErrorUI(discord.ui.LayoutView):
    def __init__(self, message: str) -> None:
        super().__init__()

        text_display = discord.ui.TextDisplay(
            f"# {MELVIN_CROSS_EMOJI} Error\n\n{message}",
        )

        container = discord.ui.Container(
            text_display,
            SmallSeparator(),
            accent_color=discord.Color.from_str(TERTIARY),
        )

        self.container = container
        self.add_item(container)


class ExceptionUI(ErrorUI):
    def __init__(self) -> None:
        super().__init__(ERROR_MESSAGE)


class ActionUI(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__()

        self.text_display = ThinkingText()

        container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
            accent_color=discord.Color.from_str(PRIMARY),
        )

        self.container = container
        self.add_item(container)

    def update_text(self, new_content: str) -> None:
        self.text_display.content = new_content


class MiscLoggingClass(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__()

        self.text_display = ThinkingText()

        container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
            accent_color=discord.Color.from_str(PRIMARY),
        )

        self.container = container
        self.add_item(container)


class NegativeLoggingClass(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__()

        self.text_display = ThinkingText()

        container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
            accent_color=discord.Color.from_str(TERTIARY),
        )

        self.container = container
        self.add_item(container)


class PositiveLoggingClass(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__()

        self.text_display = ThinkingText()

        container = discord.ui.Container(
            self.text_display,
            SmallSeparator(),
            accent_color=discord.Color.from_str(SECONDARY),
        )

        self.container = container
        self.add_item(container)
