import asyncio
import json
import logging
import math
import os
import time

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
    DATA_DIR,
    ERROR_MESSAGE,
    MELVIN_EMOJI,
    SHARD_ICON,
    WEBSITE_URL,
    DisplayNameEffect,
    DisplayNameFont,
)
from ui import ErrorUI, GalleryWithItem, HelpView, InfoUI, SmallSeparator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

STATS_FILE = DATA_DIR / "bot_stats.json"
GUILDS_FILE = DATA_DIR / "bot_guilds.json"

LINK_BUTTONS = (
    (
        "Add Me",
        "https://discord.com/oauth2/authorize?client_id=1468362201197973756",
        "<:pluscircleduotone:1548410107484835942>",
    ),
    (
        "Support",
        "https://discord.gg/PfyKM7dyx4",
        "<:questionduotone:1548410071195844668>",
    ),
    ("Website", WEBSITE_URL, "<:browsersduotone:1548410087037477066>"),
    ("Status", f"{WEBSITE_URL}/status", "<:browsersduotone:1548410087037477066>"),
    (
        "Github",
        "https://github.com/saltgranule/melvin",
        "<:githublogoduotone:1548410053382643723>",
    ),
)


class MelvinTree(app_commands.CommandTree):
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

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "**You do not have permission to do this.**"
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(
                perm.replace("_", " ").title() for perm in error.missing_permissions
            )
            msg = f"**I need {missing} to do this.**"
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "**This command can only be used in a server.**"
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = "**You are being rate limited.**"
        else:
            name = (
                interaction.command.qualified_name if interaction.command else "unknown"
            )
            log.error("Unhandled error in /%s", name, exc_info=error)
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)


class Melvin(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="-",
            intents=intents,
            tree_cls=MelvinTree,
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
            allowed_contexts=app_commands.AppCommandContext(
                guild=True,
                dm_channel=True,
                private_channel=True,
            ),
        )

    async def get_bio(self, *, guild: discord.Guild) -> None:
        result = await self.http.request(
            route=discord.http.Route(
                "PATCH",
                "/guilds/{guild_id}/members/@me",
                guild_id=guild.id,
            ),
            json={},
        )
        return result["bio"]

    async def set_name_style(
        self,
        *,
        guild: discord.Guild,
        font_id: DisplayNameFont,
        effect_id: DisplayNameEffect,
        colors: list[str],
    ) -> None:
        await self.http.request(
            route=discord.http.Route(
                "PATCH",
                "/guilds/{guild_id}/members/@me",
                guild_id=guild.id,
            ),
            json={
                "display_name_font_id": font_id.value,
                "display_name_effect_id": effect_id.value,
                "display_name_colors": [int(hex_code, 16) for hex_code in colors],
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
        try:
            resolver = aiodns.DNSResolver(nameservers=["1.1.1.1", "8.8.8.8"])
            self.http._HTTPClient__session._connector._resolver._resolver = resolver  # ruff: ignore[private-member-access]  # pyright: ignore[ reportAttributeAccessIssue]
            log.info("DNS resolver successfully configured.")
        except Exception:
            log.exception("Could not configure DNS resolver")
        self.add_view(HelpView(self, timeout=None))
        status.set_start_time()
        log.info("Logging started.")

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
            await asyncio.gather(update_stats(), update_shard_latency())
        except Exception:
            log.exception("Failed to record initial startup metrics")

        for loop in (update_stats, update_shard_latency):
            if not loop.is_running():
                loop.start()


bot = Melvin()


def _latencies() -> list[tuple[int, float]]:
    return getattr(bot, "latencies", None) or [(0, bot.latency)]


@tasks.loop(minutes=30)
async def update_stats() -> None:
    guild_count = len(bot.guilds)
    member_count = sum(guild.member_count or 0 for guild in bot.guilds)
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
    return f"{round(value)}ms" if math.isfinite(value) else "N/A"


@tasks.loop(minutes=1)
async def update_shard_latency() -> None:
    api_latency_ms = await _measure_api_latency() or 0.0
    for shard_id, latency in _latencies():
        if math.isfinite(latency):
            await status.record_latency(shard_id, latency * 1000, api_latency_ms)


@bot.tree.command(name="latency", description="View the bot's latency.")
async def latency_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()

    lines = [
        f"**{SHARD_ICON} Shard {shard_id}, {_format_ms(latency * 1000)}**"
        for shard_id, latency in _latencies()
    ]
    api_latency = await _measure_api_latency()
    lines.append(
        f"**{API_ICON} API, {_format_ms(api_latency)}**"
        if api_latency is not None
        else "**API, unavailable**",
    )

    await interaction.followup.send(
        view=InfoUI(title="Latency", subtitle="\n".join(lines)),
    )


@bot.tree.command(name="help", description="Take a peek at Melvin's commands.")
async def help_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    hidden = (
        await module_settings.disabled_modules(interaction.guild_id)
        if interaction.guild_id is not None
        else set()
    )
    await interaction.followup.send(view=HelpView(bot, hidden))


@bot.tree.command(name="melvin", description="Here's Melvin.")
async def melvin_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()

    row = discord.ui.ActionRow(
        *(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.link,
                url=url,
                emoji=emoji,
            )
            for label, url, emoji in LINK_BUTTONS
        ),
    )
    view = discord.ui.LayoutView()
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(
                f"{MELVIN_EMOJI} **Melvin**\n-# **an open source, community managed discord bot, stable and paywall free.**",
            ),
            GalleryWithItem(f"{WEBSITE_URL}/static/media/OG.png"),
            SmallSeparator(),
            row,
        ),
    )
    await interaction.followup.send(view=view)


async def main() -> None:
    load_dotenv()
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("Token is not set.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    await module_settings.init_db()
    async with bot:
        for name in module_registry.cog_names():
            try:
                await bot.load_extension(name)
            except commands.NoEntryPointError:
                log.info("Skipped %s, it has no setup function", name)
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
