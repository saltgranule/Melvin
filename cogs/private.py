import asyncio
import os
import subprocess
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from globals import (
    LOG_CHANNEL,
    MELVIN_BANNER,
    DisplayNameEffect,
    DisplayNameFont,
)
from main import Melvin
from ui import ErrorUI, GalleryWithItem, GatedUI, PositiveUI

BOT_DIR = Path(__file__).resolve().parent.parent


class PrivateCog(
    commands.GroupCog,
    name="private",
    description="Private administrative and developer utilities.",
):
    def __init__(self, bot: Melvin) -> None:
        super().__init__()
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.bot.set_name_style(
            guild=guild,
            font_id=DisplayNameFont.cherry_bomb,
            effect_id=DisplayNameEffect.gradient,
            colors=["FFFFFF", "000000"],
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

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log_channel = self.bot.get_channel(LOG_CHANNEL)
        if log_channel is None or not isinstance(log_channel, discord.TextChannel):
            return
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"**Melvin was just removed from {guild.name}.**\n"
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

    @app_commands.command(name="sync", description="Sync the application command tree.")
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not await self.bot.is_owner(interaction.user):
            view = GatedUI()
            await interaction.followup.send(view=view, ephemeral=True)
            return
        try:
            synced = await self.bot.tree.sync()
        except discord.HTTPException as e:
            view = ErrorUI(message=f"**{e}**")
            await interaction.followup.send(view=view, ephemeral=True)
            return
        view = PositiveUI(title="Tree Sync Complete", subtitle=f"**Synced {len(synced)} command(s).**")
        await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="update", description="Pull the latest build from master and restart.")
    async def update(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not await self.bot.is_owner(interaction.user):
            view = GatedUI()
            await interaction.followup.send(view=view, ephemeral=True)
            return

        fetch = await asyncio.to_thread(
            subprocess.run,
            ["git", "fetch", "origin", "master"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
        )
        if fetch.returncode != 0:
            view = ErrorUI(message=f"**Fetch failed:**\n```{fetch.stderr.strip()[:1500]}```")
            await interaction.followup.send(view=view, ephemeral=True)
            return

        diff = await asyncio.to_thread(
            subprocess.run,
            ["git", "rev-list", "HEAD..origin/master", "--count"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
        )
        if diff.stdout.strip() == "0":
            view = PositiveUI(title="Already Up To Date", subtitle="**No new commits found on master.**")
            await interaction.followup.send(view=view, ephemeral=True)
            return

        reset = await asyncio.to_thread(
            subprocess.run,
            ["git", "reset", "--hard", "origin/master"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
        )
        if reset.returncode != 0:
            view = ErrorUI(message=f"**Reset failed:**\n```{reset.stderr.strip()[:1500]}```")
            await interaction.followup.send(view=view, ephemeral=True)
            return

        pip = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt",
             "--break-system-packages", "-q"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
        )
        if pip.returncode != 0:
            view = ErrorUI(message=f"**Dependency install failed:**\n```{pip.stderr.strip()[:1500]}```")
            await interaction.followup.send(view=view, ephemeral=True)
            return

        view = PositiveUI(
            title="Pull successful.",
            subtitle=f"**Pulled {diff.stdout.strip()} new commit(s). Restarting...**",
        )
        await interaction.followup.send(view=view, ephemeral=True)

        async def restart_bot():
            await asyncio.sleep(1)
            try:
                await asyncio.wait_for(self.bot.close(), timeout=5)
            except asyncio.TimeoutError:
                pass
            sys.exit(0)

        asyncio.create_task(restart_bot())


async def setup(bot: Melvin) -> None:
    await bot.add_cog(PrivateCog(bot))