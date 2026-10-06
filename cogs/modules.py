import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import module_settings
from globals import ERROR_MESSAGE, MELVIN_CHECK_EMOJI, MELVIN_CROSS_EMOJI, MELVIN_EMOJI
from ui import ErrorUI, SmallSeparator

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)


def _has_manage_guild(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.manage_guild)


class ModulesView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, disabled: set[str]) -> None:
        super().__init__(timeout=300)
        self.guild_id = guild_id

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# {MELVIN_EMOJI} Modules\n"
                "-# **Turn Melvin's features on or off for this server.**",
            ),
            SmallSeparator(),
        )

        for module, (label, description) in module_settings.MODULES.items():
            enabled = module not in disabled
            button = discord.ui.Button(
                label="On" if enabled else "Off",
                emoji=MELVIN_CHECK_EMOJI if enabled else MELVIN_CROSS_EMOJI,
                style=discord.ButtonStyle.secondary,
            )
            button.callback = self._toggle_callback(module, enabled=enabled)
            container.add_item(
                discord.ui.Section(f"**{label}**\n-# {description}", accessory=button),
            )

        self.add_item(container)

    def _toggle_callback(
        self,
        module: str,
        *,
        enabled: bool,
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def _callback(interaction: discord.Interaction) -> None:
            if not _has_manage_guild(interaction):
                await interaction.response.send_message(
                    view=ErrorUI("**You do not have permission to do this.**"),
                    ephemeral=True,
                )
                return

            try:
                await module_settings.set_enabled(
                    self.guild_id,
                    module,
                    enabled=not enabled,
                )
            except Exception:
                log.exception(
                    "Failed to toggle module %s in guild %s",
                    module,
                    self.guild_id,
                )
                await interaction.response.send_message(
                    view=ErrorUI(ERROR_MESSAGE),
                    ephemeral=True,
                )
                return

            disabled = await module_settings.disabled_modules(self.guild_id)
            await interaction.response.edit_message(
                view=ModulesView(self.guild_id, disabled),
            )

        return _callback


class ModulesCog(
    commands.Cog,
    name="modules",
    description="Turn Melvin's features on or off for a server.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    # cogwide error handling
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "**You do not have permission to do this.**"
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "**This command can only be used in a server.**"
        else:
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(
        name="modules",
        description="Turn Melvin's features on or off for this server.",
    )
    # server only, installed to a server and used in it, never in dms or as a user app
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modules(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return

        disabled = await module_settings.disabled_modules(interaction.guild.id)
        await interaction.response.send_message(
            view=ModulesView(interaction.guild.id, disabled),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModulesCog(bot))
