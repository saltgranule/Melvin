import re

import discord
from discord import app_commands
from discord.ext import commands

from globals import (
    INVITE_URL,
    DisplayNameEffect,
    DisplayNameFont,
)
from main import Melvin
from ui import ErrorUI, PositiveUI

COLOR_PATTERN = re.compile(r"^[0-9a-fA-F]{6}(?:-[0-9a-fA-F]{6})?$")


@app_commands.guild_only
class StyleCog(
    commands.GroupCog,
    name="style",
    description="Name style configuration commmands.",
):
    def __init__(self, bot: Melvin) -> None:
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
            msg = f"Something went wrong: **{error}. Please [join the support server]({INVITE_URL}) to report this issue.**"

        error_ui = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=error_ui)
        else:
            await interaction.response.send_message(view=error_ui, ephemeral=False)

    @app_commands.command(name="reset", description="Reset Melvin's name style for this guild.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return

        await self.bot.reset_name_style(guild=interaction.guild)
        view = PositiveUI(title="Style Reset", subtitle="Melvin's display name style has been reset for this server.")
        await interaction.response.send_message(view=view)

    @app_commands.command(name="set", description="Set Melvin's name style for this guild.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        font="The display name's font.",
        effect="The display name's effect.",
        colors="The display name's colors.",
    )
    @app_commands.choices(
        font=[
            # app_commands.Choice(name="Bangers", value="bangers"),
            # app_commands.Choice(name="Bio Rhyme", value="bio_rhyme"),
            app_commands.Choice(name="Sakura", value="cherry_bomb"),
            app_commands.Choice(name="Jellybean", value="chicle"),
            # app_commands.Choice(name="Compagnon", value="compagnon"),
            app_commands.Choice(name="Modern", value="museo_moderno"),
            app_commands.Choice(name="Medieval", value="neo_castel"),
            app_commands.Choice(name="8Bit", value="pixelify"),
            # app_commands.Choice(name="Ribes", value="ribes"),
            app_commands.Choice(name="Vampyre", value="sinistre"),
            app_commands.Choice(name="GG Sans (Default)", value="default"),
            app_commands.Choice(name="Tempo", value="zilla_slab"),
        ],
        effect=[
            app_commands.Choice(name="Solid", value="solid"),
            app_commands.Choice(name="Gradient", value="gradient"),
            app_commands.Choice(name="Neon", value="neon"),
            app_commands.Choice(name="Toon", value="toon"),
            app_commands.Choice(name="Pop", value="pop"),
            # app_commands.Choice(name="Glow", value="glow"),
        ],
    )
    async def set(
        self,
        interaction: discord.Interaction,
        font: str,
        effect: str,
        colors: str,
    ) -> None:
        if interaction.guild is None:
            return

        is_valid = bool(COLOR_PATTERN.match(colors))
        has_dash = "-" in colors

        if not is_valid or (effect == "gradient" and not has_dash) or (effect != "gradient" and has_dash):
            error = (
                "Gradient must be of the form `ABCDEF-123456`."
                if effect == "gradient" else
                "Color must be of the form `ABCDEF`."
            )

            view = ErrorUI(error)
            await interaction.response.send_message(view=view)
            return

        color_list = colors.split("-")

        await self.bot.set_name_style(
            guild=interaction.guild,
            font_id=DisplayNameFont[font],
            effect_id=DisplayNameEffect[effect],
            colors=color_list,
        )
        view = PositiveUI(title="Style Set", subtitle="Melvin's display name style has been set for this server.")
        await interaction.response.send_message(view=view)


async def setup(bot: Melvin) -> None:
    await bot.add_cog(StyleCog(bot))
