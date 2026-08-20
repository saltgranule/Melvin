import aiosqlite
import discord
from discord.ext import commands

from globals import (
    INVITE_URL,
    MELVIN_CHECK_EMOJI,
    MELVIN_CROSS_EMOJI,
    MELVIN_EMOJI,
    MELVIN_HELP_BANNER,
    MELVIN_MISC_EMOJI,
    MELVIN_WARN_EMOJI,
    PRIMARY,
    SECONDARY,
    TERTIARY,
    QUATERNARY,
)

message = f"**Something went wrong with that. Please [join the support server]({INVITE_URL}) to report this issue.**"


# HelpView functions to grasp command group details
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


def help_page(cog: commands.Cog) -> str:
    lines = [f"# {MELVIN_EMOJI} {cog.__cog_group_name__} Commands"]
    if (
        hasattr(cog, "__cog_group_description__")
        and cog.__cog_group_description__ != "…"
    ):
        lines.append(f"-# **{cog.__cog_group_description__}**")

    lines.extend(
        f"**\n/{cmd.qualified_name}**\n-# **{cmd.description}**"
        for top_cmd in get_cog_commands(cog)
        for cmd in flatten_commands(top_cmd)
    )

    return "\n".join(lines)


# select menu
class CogSelect(discord.ui.Select):
    def __init__(self, cogs: list[commands.Cog]) -> None:
        self.cogs_map = {cog.__cog_group_name__: cog for cog in cogs}

        options = [
            discord.SelectOption(
                label=cog.__cog_group_name__,
                value=cog.__cog_group_name__,
                description=(
                    cog.__cog_group_description__[:100]
                    if hasattr(cog, "__cog_group_description__")
                    and cog.__cog_group_description__ != "…"
                    else None
                ),
            )
            for cog in cogs
        ]

        super().__init__(
            placeholder="Select a cog category.",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="help_view:cog_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_cog_name = self.values[0]
        selected_cog = self.cogs_map.get(selected_cog_name)

        if selected_cog and self.view:
            self.view.text_display.content = help_page(selected_cog)
            await interaction.response.edit_message(view=self.view)


class HelpView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        banner_gallery = discord.ui.MediaGallery(
            discord.MediaGalleryItem(f"{MELVIN_HELP_BANNER}"),
        )
        banner_container = discord.ui.Container(banner_gallery)

        cogs = self.get_cogs()
        initial_content = help_page(cogs[0]) if cogs else "No commands available."
        self.text_display = discord.ui.TextDisplay(initial_content)
        separator = discord.ui.Separator(
            visible=True,
            spacing=discord.SeparatorSpacing.small,
        )

        if cogs:
            self.cog_select = CogSelect(cogs)
            select_row = discord.ui.ActionRow(self.cog_select)
            content_container = discord.ui.Container(
                self.text_display, separator, select_row,
            )
        else:
            content_container = discord.ui.Container(self.text_display, separator)

        self.add_item(banner_container)
        self.add_item(content_container)

    def get_cogs(self) -> list[commands.Cog]:
        return [c for c in self.bot.cogs.values() if get_cog_commands(c)]

    async def on_select_cog(self, interaction: discord.Interaction) -> None:
        selected_cog_name = interaction.data["values"][0]

        cogs_map = {
            getattr(c, "__cog_group_name__", c.qualified_name): c
            for c in self.get_cogs()
        }
        selected_cog = cogs_map.get(selected_cog_name)

        if selected_cog:
            self.text_display.content = help_page(selected_cog)
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()


# case ui
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
            await interaction.response.send_message("**You lack permissions to remove cases.**", ephemeral=True)
            return

        await interaction.response.defer()

        # remove the case
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
        self, target_user: discord.User | discord.Member, db_path: str,
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
                msg = f"**No cases found for {who} under filter {self.current_action}.**"
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
        await self.build_components(
            interaction.guild_id, interaction.user, interaction.client.user,
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


# GatedUI
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


# ResponseUI
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


# InfoUI
class InfoUI(discord.ui.LayoutView):
    def __init__(self, *, title: str, subtitle: str) -> None:
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {MELVIN_MISC_EMOJI} {title}\n{subtitle}"),
            SmallSeparator(),
            accent_color=discord.Color.from_str(QUATERNARY),
        )
        self.container = container
        self.add_item(container)


# PositiveUI
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


# ErrorUI
class ErrorUI(discord.ui.LayoutView):
    def __init__(self, message: str) -> None:
        super().__init__()

        text_display = discord.ui.TextDisplay(f"# {MELVIN_CROSS_EMOJI} Error\n\n{message}")

        container = discord.ui.Container(
            text_display,
            SmallSeparator(),
            accent_color=discord.Color.from_str(TERTIARY),
        )

        self.container = container
        self.add_item(container)


# ActionUI
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


# LoggingClassUI
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
