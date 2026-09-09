import re

import discord
from discord import app_commands
from discord.ext import commands

from globals import (
    ERROR_MESSAGE,
    LOG_CHANNEL,
    MELVIN_BANNER,
    QUATERNARY,
    DisplayNameEffect,
    DisplayNameFont,
)
from main import Melvin
from ui import ErrorUI, GalleryWithItem, PositiveUI

COLOR_PATTERN = re.compile(r"^[0-9a-fA-F]{6}(?:-[0-9a-fA-F]{6})?$")


@app_commands.guild_only
@app_commands.allowed_installs(guilds=True, users=False)
class StyleCog(
    commands.GroupCog,
    name="style",
    description="Name style configuration commands.",
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
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=False)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.bot.set_name_style(
            guild=guild,
            font_id=DisplayNameFont.cherry_bomb,
            effect_id=DisplayNameEffect.gradient,
            colors=[QUATERNARY.removeprefix("#"), "FFFFFF"],
        )
        log_channel = self.bot.get_channel(LOG_CHANNEL)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Melvin was just added to {guild.name}.**\n"
                    f"Now in **{len(self.bot.guilds)}** guild(s).",
                ),
                GalleryWithItem(MELVIN_BANNER),
            ),
        )
        try:
            await log_channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(name="set", description="Set Melvin's name style for this guild. Omit all three arguments to reset.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        font="The display name's font. Leave Empty for no change.",
        effect="The display name's effect. Leave Empty for no change.",
        colors="The display name's colors. Leave Empty for no change.",
    )
    @app_commands.choices(
        font=[
            app_commands.Choice(name="Sakura", value="cherry_bomb"),
            app_commands.Choice(name="Jellybean", value="chicle"),
            app_commands.Choice(name="Modern", value="museo_moderno"),
            app_commands.Choice(name="Medieval", value="neo_castel"),
            app_commands.Choice(name="8Bit", value="pixelify"),
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
        ],
    )
    async def set(
        self,
        interaction: discord.Interaction,
        font: str | None = None,
        effect: str | None = None,
        colors: str | None = None,
    ) -> None:
        if interaction.guild is None:
            return

        style = await self.bot.get_name_style(interaction.guild)

        selected_font = DisplayNameFont[font] if font is not None else style["font_id"]
        selected_effect = DisplayNameEffect[effect] if effect is not None else style["effect_id"]

        if colors is not None:
            valid = bool(COLOR_PATTERN.match(colors))
            dashed = "-" in colors
            effect_name = effect if effect is not None else selected_effect.name

            if not valid or (effect_name == "gradient" and not dashed) or (effect_name != "gradient" and dashed):
                msg = (
                    "Gradient must be of the form `ABCDEF-123456`."
                    if effect_name == "gradient" else
                    "Color must be of the form `ABCDEF`."
                )
                await interaction.response.send_message(view=ErrorUI(msg))
                return

            color_list = colors.split("-")
        else:
            color_list = style["colors"]

        if font is None and effect is None and colors is None:
            await self.bot.reset_name_style(guild=interaction.guild)
            view = PositiveUI(title="Style Reset", subtitle="Melvin's display name style has been reset for this server.")
        else:
            await self.bot.set_name_style(
                guild=interaction.guild,
                font_id=selected_font,
                effect_id=selected_effect,
                colors=color_list,
            )
            view = PositiveUI(title="Style Set", subtitle="Melvin's display name style has been set for this server.")

        await interaction.response.send_message(view=view)


async def setup(bot: Melvin) -> None:
    await bot.add_cog(StyleCog(bot))
