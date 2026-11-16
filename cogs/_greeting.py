import datetime
import logging
import random
import re

import discord

import module_config
from module_registry import Panel, Setting
from ui import ErrorUI, GalleryWithItem, ResponseUI

log = logging.getLogger(__name__)

PLACEHOLDERS = (
    ("{member}", "A mention of the member. Only this one pings them."),
    ("{member_no_ping}", "A mention of the member that doesn't ping them."),
    ("{member_name}", "The member's display name."),
    ("{member_username}", "The member's username."),
    ("{member_created}", "When the member's account was created, eg. 3 years ago."),
    ("{member_count}", "The server's member count."),
    ("{server_name}", "The server's name."),
    ("{date_t}", "Short time, eg. 11:20."),
    ("{date_T}", "Time with seconds, eg. 11:20:30."),
    ("{date_d}", "Short date, eg. 01/01/2020."),
    ("{date_D}", "Long date, eg. January 1, 2020."),
    ("{date_f}", "Date and time, eg. January 1, 2020 at 11:30."),
    ("{date_F}", "Full date and time, eg. Wednesday, January 1, 2020 at 11:30."),
    ("{date_s}", "Short date and time, eg. 01/01/2020, 11:30."),
    ("{date_S}", "Short date and time with seconds, eg. 01/01/2020, 11:30:30."),
    ("{date_R}", "Relative time, eg. 5 minutes ago."),
)
DATE_STYLES = "tTdDfFsSR"


def placeholder_panel(event: str) -> Panel:
    return Panel(
        "Placeholders",
        f"These are swapped into the message when it's sent. The date ones use the "
        f"time the member {event}, shown in each reader's own timezone.",
        PLACEHOLDERS,
    )


def message_settings(
    *,
    channel_label: str,
    noun: str,
    event: str,
    default: str,
    example: str,
    group: str,
) -> tuple[Setting, ...]:
    return (
        Setting(
            "channel",
            channel_label,
            f"The channel {noun} messages are sent in. Nothing is sent until one is set.",
            "channel",
            group=group,
        ),
        Setting(
            "message",
            "Message",
            "Placeholders like {member} and {server_name} are filled in when it's sent. "
            f"Separate several messages with $ and one is picked at random for each {event}.",
            "text",
            default=default,
            max_length=2000,
            placeholder=example,
            group=group,
        ),
        Setting(
            "image",
            "Image",
            "Shown under the message.",
            "image",
            group=group,
        ),
        *(
            setting
            for number, word in ((1, "first"), (2, "second"))
            for setting in (
                Setting(
                    f"button{number}_label",
                    f"{word.title()} button label",
                    f"The text on the {word} link button.",
                    "text",
                    default=f"Link {number}",
                    max_length=80,
                    group="Link buttons",
                    inline=True,
                ),
                Setting(
                    f"button{number}_url",
                    f"{word.title()} button link",
                    "Where it goes. Leave empty for no button.",
                    "url",
                    placeholder="https://",
                    group="Link buttons",
                    inline=True,
                ),
            )
        ),
    )


def pick_message(values: dict[str, str | None]) -> str:
    text = values["message"] or ""
    parts = [part.strip() for part in text.split("$")]
    return random.choice([part for part in parts if part] or [text.strip()])


def build_view(
    message: str,
    values: dict[str, str | None],
    member: discord.Member,
    when: datetime.datetime,
) -> tuple[ResponseUI, discord.File | None]:
    placeholders = {
        "member": member.mention,
        "member_no_ping": member.mention,
        "member_name": member.display_name,
        "member_username": member.name,
        "member_created": discord.utils.format_dt(member.created_at, "R"),
        "member_count": str(member.guild.member_count or 0),
        "server_name": member.guild.name,
        **{
            f"date_{style}": discord.utils.format_dt(when, style=style)
            for style in DATE_STYLES
        },
    }
    view = ResponseUI(
        re.sub(
            r"\{(\w+)\}",
            lambda match: placeholders.get(match.group(1), match.group(0)),
            message,
        ),
    )

    image = module_config.image_file(values["image"])
    file = discord.File(image, filename=image.name) if image is not None else None
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


async def send(
    bot: discord.Client,
    values: dict[str, str | None],
    member: discord.Member,
    when: datetime.datetime,
) -> None:
    channel_id = values["channel"]
    channel = bot.get_channel(int(channel_id)) if channel_id else None
    if not isinstance(channel, discord.TextChannel):
        return

    message = pick_message(values)
    view, file = build_view(message, values, member, when)
    try:
        await channel.send(
            view=view,
            allowed_mentions=discord.AllowedMentions(users="{member}" in message),
            **({"file": file} if file is not None else {}),
        )
    except discord.HTTPException:
        pass


async def preview(
    interaction: discord.Interaction,
    module: str,
    when: datetime.datetime,
) -> None:
    await interaction.response.defer()
    values = await module_config.get_all(interaction.guild.id, module)
    if not values["channel"]:
        await _finish(
            interaction,
            ErrorUI(f"**Set a {module} channel first with /{module} config.**"),
        )
        return
    view, file = build_view(pick_message(values), values, interaction.user, when)
    await _finish(interaction, view, file)


async def _finish(
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
        log.warning("Original interaction response missing, falling back to a followup")
        try:
            await interaction.followup.send(
                view=view,
                **({"file": file} if file is not None else {}),
            )
        except discord.HTTPException:
            log.exception("Followup send also failed")


async def clear(guild: discord.Guild, module: str) -> None:
    try:
        await module_config.clear_module(guild.id, module)
    except Exception:
        log.exception("Couldn't clean up %s settings for guild %s", module, guild.id)
