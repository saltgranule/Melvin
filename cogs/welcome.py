import logging
import random
import re

import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import DATA_DIR
from module_registry import Module, Setting
from ui import ErrorUI, GalleryWithItem, ResponseUI, open_config

MODULE = Module(
    "welcome",
    "Welcome",
    "Welcome messages for new members.",
    settings=(
        Setting(
            "channel",
            "Welcome channel",
            "The channel welcome messages are sent in. Nothing is sent until one is set.",
            "channel",
            group="Welcome message",
        ),
        Setting(
            "message",
            "Message",
            "Use {member} to mention the new member, {member_name} for the display name, {member_count} for the member count, {member_no_ping} for a non-pinging mention, {member_created} for the account creation date, {member_username} for the username, {server_name} for the server name, {date_t} for short time (11:20), {date_T} for time with seconds (11:20:30), {date_d} for short date (01/01/2020), {date_D} for long date (January 1, 2020), {date_f} for date and time (January 1, 2020 at 11:30), {date_F} for full date and time (Wednesday, January 1, 2020 at 11:30), {date_s} for short date and time (01/01/2020, 11:30), {date_S} for short date and time with seconds (01/01/2020, 11:30:30) and {date_R} for the relative time (5 minutes ago). "
            "Separate several messages with $ and one is picked at random for each join.",
            "text",
            default="Welcome, {member}!",
            max_length=2000,
            placeholder="Welcome, {member}! We're at {member_count} members now.",
            group="Welcome message",
        ),
        Setting(
            "image",
            "Image",
            "Shown under the message.",
            "image",
            group="Welcome message",
        ),
        Setting(
            "bots",
            "Bot welcomes",
            "Whether bots get the welcome message too.",
            "choice",
            default="off",
            choices=(("off", "Skip bots"), ("on", "Welcome bots")),
            group="Welcome message",
        ),
        Setting(
            "button1_label",
            "First button label",
            "The text on the first link button.",
            "text",
            default="Link 1",
            max_length=80,
            group="Link buttons",
        ),
        Setting(
            "button1_url",
            "First button link",
            "Where the first button goes. Leave empty for no button.",
            "url",
            placeholder="https://",
            group="Link buttons",
        ),
        Setting(
            "button2_label",
            "Second button label",
            "The text on the second link button.",
            "text",
            default="Link 2",
            max_length=80,
            group="Link buttons",
        ),
        Setting(
            "button2_url",
            "Second button link",
            "Where the second button goes. Leave empty for no button.",
            "url",
            placeholder="https://",
            group="Link buttons",
        ),
    ),
)

log = logging.getLogger(__name__)


def split_messages(text: str) -> list[str]:
    parts = [part.strip() for part in text.split("$")]
    return [part for part in parts if part] or [text.strip()]


async def safe_finish(
    interaction: discord.Interaction,
    view: discord.ui.LayoutView,
    file: discord.File | None = None,
) -> None:
    try:
        await interaction.edit_original_response(
            view=view,
            **({"attachments": [file]} if file is not None else {}),
        )
    except discord.NotFound:
        log.warning(
            "Original interaction response missing; falling back to followup.send",
        )
        try:
            await interaction.followup.send(
                view=view,
                **({"file": file} if file is not None else {}),
            )
        except discord.HTTPException:
            log.exception("Followup send also failed")


def _load_image_file(path: str | None) -> discord.File | None:
    file = module_config.image_file(path)
    return discord.File(file, filename=file.name) if file is not None else None


def _build_welcome_ui(
    message: str,
    values: dict[str, str | None],
    member: discord.Member,
) -> tuple[ResponseUI, discord.File | None]:
    dt = member.joined_at or discord.utils.utcnow()  # fallback

    placeholders = {
        "member": member.mention,
        "member_no_ping": member.mention,
        "member_name": member.display_name,
        "member_username": member.name,
        "member_created": discord.utils.format_dt(member.created_at, "R"),
        "member_count": str(member.guild.member_count or 0),
        "server_name": member.guild.name,
        "date_t": discord.utils.format_dt(dt, style="t"),
        "date_T": discord.utils.format_dt(dt, style="T"),
        "date_d": discord.utils.format_dt(dt, style="d"),
        "date_D": discord.utils.format_dt(dt, style="D"),
        "date_f": discord.utils.format_dt(dt, style="f"),
        "date_F": discord.utils.format_dt(dt, style="F"),
        "date_s": discord.utils.format_dt(dt, style="s"),
        "date_S": discord.utils.format_dt(dt, style="S"),
        "date_R": discord.utils.format_dt(dt, style="R"),
    }
    view = ResponseUI(
        re.sub(
            r"\{(\w+)\}",
            lambda match: placeholders.get(match.group(1), match.group(0)),
            message,
        ),
    )
    file = _load_image_file(values["image"])
    if file is not None:
        view.container.add_item(GalleryWithItem(f"attachment://{file.filename}"))

    buttons = [
        discord.ui.Button(
            label=values[f"button{number}_label"],
            style=discord.ButtonStyle.link,
            url=values[f"button{number}_url"],
        )
        for number in (1, 2)
        if values[f"button{number}_url"]
    ]
    if buttons:
        view.container.add_item(discord.ui.ActionRow(*buttons))

    return view, file


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class WelcomeCog(
    commands.GroupCog,
    name="welcome",
    description="Configure welcome messages and settings for new members.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = DATA_DIR / "welcome.db"

    async def cog_load(self) -> None:
        await module_config.migrate_legacy(
            self.db_path,
            "welcome_channels",
            "welcome",
            lambda row: (
                int(row[0]),
                {
                    "channel": row[1],
                    "message": row[2],
                    "image": row[3],
                    "button1_url": row[4],
                    "button1_label": row[5],
                    "button2_url": row[6],
                    "button2_label": row[7],
                },
            ),
        )

    @app_commands.command(
        name="config",
        description="Change welcome message settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "welcome")

    @app_commands.command(
        name="preview",
        description="Preview what the configured welcome notification looks like.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def preview(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        await interaction.response.defer()
        values = await module_config.get_all(interaction.guild.id, "welcome")
        if not values["channel"]:
            await safe_finish(
                interaction,
                ErrorUI("**Set a welcome channel first with /welcome config.**"),
            )
            return

        message = random.choice(split_messages(values["message"] or ""))
        view, file = _build_welcome_ui(message, values, interaction.user)
        await safe_finish(interaction, view, file=file)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await module_settings.is_enabled(member.guild.id, "welcome"):
            return

        values = await module_config.get_all(member.guild.id, "welcome")
        if member.bot and values["bots"] != "on":
            return
        channel_id = values["channel"]
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return

        message = random.choice(split_messages(values["message"] or ""))
        view, file = _build_welcome_ui(message, values, member)
        try:
            await channel.send(
                view=view,
                allowed_mentions=discord.AllowedMentions(users="{member}" in message),
                **({"file": file} if file is not None else {}),
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            await module_config.clear_module(guild.id, "welcome")
        except Exception:
            log.exception(
                "failed to clean up welcome config for departed guild %s",
                guild.id,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
