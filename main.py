import asyncio
import json
import logging
import math
import os
import time
from pathlib import Path

import aiodns
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

import module_registry
import module_settings
import status
from globals import (
    API_ICON,
    MELVIN_EMOJI,
    SHARD_ICON,
    DisplayNameEffect,
    DisplayNameFont,
)
from ui import ErrorUI, HelpView, InfoUI, ResponseUI

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
log = logging.getLogger(__name__)
STATS_FILE = Path(__file__).parent / "data" / "bot_stats.json"
GUILDS_FILE = Path(__file__).parent / "data" / "bot_guilds.json"


class MelvinTree(app_commands.CommandTree):
    # blocks commands from modules a guild has turned off, before they run
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command = interaction.command
        if command is None:
            return True

        if isinstance(command, app_commands.ContextMenu):
            cog = getattr(command.callback, "__self__", None)
            module = getattr(cog, "__cog_group_name__", "")
        else:
            module = (command.root_parent or command).name

        if await module_settings.is_enabled(interaction.guild_id, module):
            return True

        # autocomplete can't be answered with a message, so it just gets nothing
        if interaction.type is discord.InteractionType.application_command:
            label = module_settings.MODULES[module][0]
            await interaction.response.send_message(
                view=ErrorUI(
                    f"**The {label} module is turned off in this server. "
                    "Someone with Manage Server can turn it back on with /modules.**",
                ),
                ephemeral=True,
            )
        return False


class Melvin(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="-",
            intents=intents,
            tree_cls=MelvinTree,
            # every command works as a user app and in dms unless it says otherwise,
            # server only cogs override this with their own allowed_installs and contexts
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
            allowed_contexts=app_commands.AppCommandContext(
                guild=True,
                dm_channel=True,
                private_channel=True,
            ),
        )

    async def set_name_style(
        self,
        *,
        guild: discord.Guild,
        font_id: DisplayNameFont,
        effect_id: DisplayNameEffect,
        colors: list[str],
    ) -> None:
        color_integers = [int(hex_code, 16) for hex_code in colors]
        await self.http.request(
            route=discord.http.Route(
                "PATCH",
                "/guilds/{guild_id}/members/@me",
                guild_id=guild.id,
            ),
            json={
                "display_name_font_id": font_id.value,
                "display_name_effect_id": effect_id.value,
                "display_name_colors": color_integers,
            },
        )

    async def get_name_style(self, guild: discord.Guild, /) -> dict:
        response = await self.http.request(
            route=discord.http.Route(
                "GET",
                "/guilds/{guild_id}/members/{user_id}",
                guild_id=guild.id,
                user_id=self.user.id,
            ),
        )

        styles = response["display_name_styles"]

        return {
            "font_id": DisplayNameFont(styles["font_id"]),
            "effect_id": DisplayNameEffect(styles["effect_id"]),
            "colors": [f"{color:06x}" for color in styles["colors"]],
        }

    async def reset_name_style(self, *, guild: discord.Guild) -> None:
        await self.set_name_style(
            guild=guild,
            font_id=DisplayNameFont.default,
            effect_id=DisplayNameEffect.solid,
            colors=["FFFFFF", "FFFFFF"],
        )

    async def setup_hook(self) -> None:
        loop = asyncio.get_running_loop()
        loop.set_debug(True)
        try:
            resolver = aiodns.DNSResolver(nameservers=["1.1.1.1", "8.8.8.8"])
            self.http._HTTPClient__session._connector._resolver._resolver = resolver  # ruff: ignore[private-member-access]  # pyright: ignore[ reportAttributeAccessIssue]
            log.info("DNS resolver successfully configured.")
        except Exception:
            log.exception("Could not configure DNS resolver")
        status.set_start_time()
        log.info("Logging started.")

    # the dashboard reads this to know which servers melvin is in
    def write_guild_ids(self) -> None:
        temp = GUILDS_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps([str(guild.id) for guild in self.guilds]))
        temp.replace(GUILDS_FILE)

    async def on_guild_join(self, _guild: discord.Guild) -> None:
        self.write_guild_ids()

    async def on_guild_remove(self, _guild: discord.Guild) -> None:
        self.write_guild_ids()

    async def on_ready(self) -> None:
        log.info("Logged in as %s.", self.user)
        self.write_guild_ids()
        await self.tree.sync()

        try:
            await update_stats()
            await update_shard_latency()
        except Exception:
            log.exception("Failed to record initial startup metrics")

        if not update_stats.is_running():
            update_stats.start()
        if not update_shard_latency.is_running():
            update_shard_latency.start()


bot = Melvin()


@tasks.loop(minutes=30)
async def update_stats() -> None:
    guild_count = len(bot.guilds)
    member_count = sum(guild.member_count or 0 for guild in bot.guilds)
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(
        json.dumps({"guild_count": guild_count, "member_count": member_count}),
    )
    await status.record_metrics(guild_count, member_count)


async def _measure_api_latency() -> float | None:
    start = time.perf_counter()
    try:
        await bot.http.request(discord.http.Route("GET", "/users/@me"))
    except Exception:
        log.exception("Failed to measure API latency")
        return None
    return (time.perf_counter() - start) * 1000


def _format_ms(value: float) -> str:
    # bot.latency is nan/inf when the gateway isn't connected yet
    if not math.isfinite(value):
        return "N/A"
    return f"{round(value)}ms"


@tasks.loop(minutes=1)
async def update_shard_latency() -> None:
    api_latency_ms = await _measure_api_latency() or 0.0
    latencies = getattr(bot, "latencies", None) or [(0, bot.latency)]
    for shard_id, latency in latencies:
        await status.record_latency(shard_id, latency * 1000, api_latency_ms)


@bot.tree.command(name="latency", description="View the bot's latency.")
async def latency_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()

    latencies = getattr(bot, "latencies", None) or [(0, bot.latency)]
    shard_lines = [
        f"**{SHARD_ICON} Shard {shard_id}, {_format_ms(latency * 1000)}**"
        for shard_id, latency in latencies
    ]

    api_latency = await _measure_api_latency()
    api_line = (
        f"**{API_ICON} API, {_format_ms(api_latency)}**"
        if api_latency is not None
        else "**API, unavailable**"
    )

    view = InfoUI(title="Latency", subtitle="\n".join([*shard_lines, api_line]))
    await interaction.followup.send(view=view)


@bot.tree.command(name="help", description="Take a peek at Melvin's commands.")
async def help_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    hidden = (
        await module_settings.disabled_modules(interaction.guild_id)
        if interaction.guild_id is not None
        else set()
    )
    view = HelpView(bot, hidden)
    await interaction.followup.send(view=view)


@bot.tree.command(name="melvin", description="Here's Melvin.")
async def melvin_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    current_guilds = len(bot.guilds)
    goal_guilds = 100

    view = ResponseUI(
        f"{MELVIN_EMOJI} **Melvin**\n-# **a demonstration of community driven consistency towards the discord bot space. Open to contributions. {current_guilds}/{goal_guilds} guilds{'.' if goal_guilds > current_guilds else '! 🎉'}**",
    )
    row = discord.ui.ActionRow()
    invite = discord.ui.Button(
        label="Add Me",
        style=discord.ButtonStyle.link,
        url="https://discord.com/oauth2/authorize?client_id=1468362201197973756",
        emoji="<:pluscircleduotone:1548410107484835942>",
    )
    support = discord.ui.Button(
        label="Support",
        style=discord.ButtonStyle.link,
        url="https://discord.gg/PfyKM7dyx4",
        emoji="<:questionduotone:1548410071195844668>",
    )
    web = discord.ui.Button(
        label="Website",
        style=discord.ButtonStyle.link,
        url="https://justmelvin.site",
        emoji="<:browsersduotone:1548410087037477066>",
    )
    status_btn = discord.ui.Button(
        label="Status",
        style=discord.ButtonStyle.link,
        url="https://justmelvin.site/status",
        emoji="<:browsersduotone:1548410087037477066>",
    )
    github = discord.ui.Button(
        label="Github",
        style=discord.ButtonStyle.link,
        url="https://github.com/saltgranule/melvin",
        emoji="<:githublogoduotone:1548410053382643723>",
    )

    row.add_item(invite)
    row.add_item(support)
    row.add_item(web)
    row.add_item(status_btn)
    row.add_item(github)
    view.container.add_item(row)

    await interaction.followup.send(view=view)


async def main() -> None:
    load_dotenv()
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("Token is not set.")
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    await module_settings.init_db()
    async with bot:
        # loads every file in cogs/ except those starting with an underscore. files without
        # a setup function are skipped
        for name in module_registry.cog_names():
            try:
                await bot.load_extension(name)
            except commands.NoEntryPointError:
                log.info("Skipped %s, it has no setup function", name)
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
