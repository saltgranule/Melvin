import asyncio
import json
import logging
import os
import time
from pathlib import Path

import aiodns
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import status
from globals import MELVIN_EMOJI, DisplayNameEffect, DisplayNameFont
from ui import HelpView, ResponseUI

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
log = logging.getLogger(__name__)
STATS_FILE = Path(__file__).parent / "data" / "bot_stats.json"


class Melvin(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="-",
            intents=intents,
            allowed_contexts=discord.app_commands.AppCommandContext(
                guild=True,
                dm_channel=True,
                private_channel=True,
            ),
            allowed_installs=discord.app_commands.AppInstallationType(
                guild=True,
                user=True,
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
            route=discord.http.Route("PATCH", "/guilds/{guild_id}/members/@me", guild_id=guild.id),
            json={
              "display_name_font_id": font_id.value,
              "display_name_effect_id": effect_id.value,
              "display_name_colors": color_integers,
            },
        )

    async def get_name_style(self, guild: discord.Guild, /) -> dict:
        response = await self.http.request(
            route=discord.http.Route(
                "GET", "/guilds/{guild_id}/members/{user_id}",
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
        log.info("Logging started.")

    async def on_ready(self) -> None:
        log.info("Logged in as %s.", self.user)
        await self.tree.sync()
        if not update_stats.is_running():
            update_stats.start()
        if not update_shard_latency.is_running():
            update_shard_latency.start()


bot = Melvin()


@tasks.loop(minutes=5)
async def update_stats() -> None:
    guild_count = len(bot.guilds)
    member_count = sum(guild.member_count or 0 for guild in bot.guilds)
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(
        json.dumps({"guild_count": guild_count, "member_count": member_count}),
    )


async def _measure_api_latency() -> float:
    start = time.perf_counter()
    try:
        await bot.http.request(discord.http.Route("GET", "/users/@me"))
    except Exception:
        log.exception("Failed to measure API latency")
        return 0.0
    return (time.perf_counter() - start) * 1000


@tasks.loop(minutes=5)
async def update_shard_latency() -> None:
    api_latency_ms = await _measure_api_latency()
    latencies = getattr(bot, "latencies", None) or [(0, bot.latency)]
    for shard_id, latency in latencies:
        await status.record_latency(shard_id, latency * 1000, api_latency_ms)


@bot.tree.command(name="help", description="Take a peek at Melvin's commands.")
async def help_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    view = HelpView(bot)
    await interaction.followup.send(view=view)


@bot.tree.command(name="melvin", description="Here's Melvin.")
async def melvin_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    current_guilds = len(bot.guilds)
    goal_guilds = 100

    view = ResponseUI(
        f"{MELVIN_EMOJI} **Melvin**\n-# **a demonstration of community driven consistency towards the discord bot space. Open to contributions. {current_guilds}/{goal_guilds} guilds{"." if goal_guilds > current_guilds else "! 🎉"}**",
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
    status = discord.ui.Button(
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
    row.add_item(status)
    row.add_item(github)
    view.container.add_item(row)

    await interaction.followup.send(view=view)


async def main() -> None:
    load_dotenv()
    token = os.getenv("token")
    if not token:
        raise RuntimeError("Token is not set.")
    async with bot:
        await bot.load_extension("cogs.info")
        await bot.load_extension("cogs.agent")
        await bot.load_extension("cogs.mod")
        await bot.load_extension("cogs.audit")
        await bot.load_extension("cogs.tool")
        await bot.load_extension("cogs.debug")
        await bot.load_extension("cogs.welcome")
        await bot.load_extension("cogs.private")
        await bot.load_extension("cogs.timezone")
        await bot.load_extension("cogs.style")
        await bot.load_extension("cogs.stats")
        await bot.load_extension("cogs.thanks")
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
