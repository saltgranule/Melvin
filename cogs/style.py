import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

import module_config
import module_settings
from globals import (
    DisplayNameEffect,
    DisplayNameFont,
)
from module_registry import Module, Setting
from ui import GalleryWithItem, open_config

FONTS = (
    ("cherry_bomb", "Sakura"),
    ("chicle", "Jellybean"),
    ("museo_moderno", "Modern"),
    ("neo_castel", "Medieval"),
    ("pixelify", "8Bit"),
    ("sinistre", "Vampyre"),
    ("default", "GG Sans"),
    ("zilla_slab", "Tempo"),
    ("playpen_sans", "Monkey Bars"),
    ("orbitron", "Mainframe"),
    ("new_rocker", "Headbang"),
    ("kalam", "Journal"),
)
EFFECTS = (
    ("solid", "Solid"),
    ("gradient", "Gradient"),
    ("neon", "Neon"),
    ("toon", "Toon"),
    ("pop", "Pop"),
    ("prism", "Prism"),
    ("gummy", "Gummy"),
)

MODULE = Module(
    "style",
    "Style",
    "Melvin's display name style.",
    settings=(
        Setting(
            "font",
            "Font",
            "The font of Melvin's name in this server.",
            "choice",
            default="zilla_slab",
            choices=FONTS,
            group="Appearance",
            inline=True,
        ),
        Setting(
            "effect",
            "Effect",
            "The effect on Melvin's name in this server.",
            "choice",
            default="solid",
            choices=EFFECTS,
            group="Appearance",
            inline=True,
        ),
        Setting(
            "colors",
            "Colors",
            "One hex color, or up to five joined by dashes for Prism, Gradient, and Gummy, eg. F4A261-FFFFFF.",
            "color",
            default="F4A261",
            placeholder="F4A261-FFFFFF",
            group="Appearance",
        ),
    ),
)

if TYPE_CHECKING:
    from main import Melvin

log = logging.getLogger(__name__)


# server only, installed to a server and used in it, never in dms or as a user app
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class StyleCog(
    commands.GroupCog,
    name="style",
    description="Name style configuration commands.",
):
    def __init__(self, bot: Melvin) -> None:
        super().__init__()
        self.bot = bot
        # what was last sent to discord per guild, so unchanged styles aren't resent
        self._applied: dict[int, tuple[str | None, ...]] = {}
        self._synced_at = time.time()

    async def cog_load(self) -> None:
        self.sync_styles.start()

    async def cog_unload(self) -> None:
        self.sync_styles.cancel()

    async def apply_style(self, guild: discord.Guild) -> None:
        values = await module_config.get_all(guild.id, "style")
        key = (values["font"], values["effect"], values["colors"])
        if self._applied.get(guild.id) == key:
            return

        colors = (values["colors"] or "F4A261").split("-")
        effect = DisplayNameEffect[values["effect"]]

        # Prism, Gradient, and Gummy accept up to 5 colors; everything else uses 1
        if effect in {
            DisplayNameEffect.prism,
            DisplayNameEffect.gradient,
            DisplayNameEffect.gummy,
        }:
            colors = colors[:5]
        else:
            colors = colors[:1]

        await self.bot.set_name_style(
            guild=guild,
            font_id=DisplayNameFont[values["font"]],
            effect_id=effect,
            colors=colors,
        )
        self._applied[guild.id] = key

    # picks up changes made on the dashboard, which can't reach the bot directly
    @tasks.loop(seconds=15)
    async def sync_styles(self) -> None:
        since = self._synced_at
        started = time.time()
        changed = await module_config.changed_since("style", since)
        self._synced_at = started

        for guild_id in changed:
            guild = self.bot.get_guild(guild_id)
            if guild is None or not await module_settings.is_enabled(guild_id, "style"):
                continue
            try:
                await self.apply_style(guild)
            except discord.HTTPException:
                log.exception("Failed to apply the name style in guild %s", guild_id)
                # look from the same point next time, so this guild is retried
                self._synced_at = since

    @sync_styles.before_loop
    async def before_sync_styles(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        if await module_settings.is_enabled(guild.id, "style"):
            try:
                await self.apply_style(guild)
            except discord.HTTPException:
                log.exception("Failed to apply the name style in guild %s", guild.id)

    @app_commands.command(
        name="config",
        description="Change Melvin's name style for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "style", on_change=self.apply_style)


async def setup(bot: Melvin) -> None:
    await bot.add_cog(StyleCog(bot))
