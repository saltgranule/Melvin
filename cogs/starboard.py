import asyncio
import logging
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import module_config
import module_settings
from globals import DATA_DIR, ERROR_MESSAGE, PRIMARY
from module_registry import Module, Setting
from ui import ErrorUI, SmallSeparator, open_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

MODULE = Module(
    "starboard",
    "Starboard",
    "Posts messages that get enough reactions to a starboard channel.",
    enabled_by_default=False,
    settings=(
        Setting(
            "channel",
            "Starboard channel",
            "Where starred messages go.",
            "channel",
            group="Channels",
        ),
        Setting(
            "sources",
            "Source channels",
            "Only count reactions here. Empty means everywhere.",
            "channels",
            channel_type="any",
            group="Channels",
        ),
        Setting(
            "emojis",
            "Emojis",
            "Reactions that star a message.",
            "emojis",
            default="⭐",
            max_length=300,
            group="Stars",
        ),
        Setting(
            "any_emoji",
            "Any emoji",
            "Count every reaction.",
            "choice",
            default="off",
            choices=(("off", "Off"), ("on", "On")),
            group="Stars",
        ),
        Setting(
            "threshold",
            "Threshold",
            "Reactions needed to post, from 1 to 100.",
            "number",
            default="3",
            minimum=1,
            maximum=100,
            group="Stars",
        ),
        Setting(
            "self_star",
            "Self-stars",
            "Let authors count their own reaction.",
            "choice",
            default="off",
            choices=(("off", "Off"), ("on", "On")),
            group="Stars",
        ),
        Setting(
            "auto_react",
            "Auto-react",
            "React to new messages in source channels.",
            "choice",
            default="off",
            choices=(("off", "Off"), ("on", "On")),
            group="Stars",
        ),
    ),
)

log = logging.getLogger(__name__)

DEFAULT_EMOJI = "⭐"
NO_CONTENT = "[No content, likely an embed or attachment.]"
MAX_CONTENT_LENGTH = 1000
VOTE_CACHE_SIZE = 500
MAX_GALLERY_ITEMS = 10
MAX_FILE_LINKS = 10
VOTE_CACHE_SECONDS = 600
STARBOARD_COLOR = discord.Color.from_str(PRIMARY)
NO_PINGS = discord.AllowedMentions.none()

SourceChannel = discord.TextChannel | discord.Thread | discord.VoiceChannel

type Voters = dict[int, set[int]]
type Votes = dict[str, Voters]


class _Lock:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.users = 0


@dataclass
class _CachedVotes:
    stamp: float
    users: Votes = field(default_factory=dict)


def _emoji_list(value: str | None) -> list[str]:
    return [part for part in (value or "").split(",") if part]


def _watches(settings: dict[str, str | None], emoji: str) -> bool:
    return settings["any_emoji"] == "on" or emoji in _emoji_list(settings["emojis"])


def _in_sources(channel: SourceChannel, sources: str | None) -> bool:
    if not sources:
        return True
    channel_id = (
        channel.parent_id if isinstance(channel, discord.Thread) else channel.id
    )
    return str(channel_id) in sources.split(",")


def _is_nsfw(channel: SourceChannel) -> bool:
    parent = channel.parent if isinstance(channel, discord.Thread) else channel
    return parent is None or parent.is_nsfw()


def _truncate(text: str, length: int = MAX_CONTENT_LENGTH) -> str:
    return text[: length - 3] + "..." if len(text) > length else text


def _is_image(attachment: discord.Attachment) -> bool:
    content_type = attachment.content_type or ""
    return content_type.startswith("image/")


def _split_media(
    message: discord.Message,
) -> tuple[list[str], list[discord.Attachment]]:
    images = [attachment for attachment in message.attachments if _is_image(attachment)]
    files = [
        attachment for attachment in message.attachments if not _is_image(attachment)
    ]
    gallery = [attachment.url for attachment in images[:MAX_GALLERY_ITEMS]]
    files.extend(images[MAX_GALLERY_ITEMS:])
    if not gallery and not files:
        embed_image = next(
            (
                embed.image.url
                for embed in message.embeds
                if embed.image and embed.image.url
            ),
            None,
        )
        if embed_image:
            gallery.append(embed_image)
    return gallery, files


def _link_text(name: str) -> str:
    return name.replace("[", "(").replace("]", ")")


def _file_lines(files: list[discord.Attachment]) -> str:
    lines = [
        f"📎 [{_link_text(attachment.filename)}]({attachment.url})"
        for attachment in files[:MAX_FILE_LINKS]
    ]
    hidden = len(files) - MAX_FILE_LINKS
    if hidden > 0:
        lines.append(f"-# and {hidden} more")
    return "\n".join(lines)


def _build_view(
    message: discord.Message,
    emoji: str,
    count: int,
) -> discord.ui.LayoutView:
    body = _truncate(message.content.strip())
    gallery, files = _split_media(message)
    jump = discord.ui.Button(
        label="Jump to Message",
        style=discord.ButtonStyle.link,
        url=message.jump_url,
    )
    media_only = not body and bool(gallery or files)
    items: list[discord.ui.Item] = [
        discord.ui.TextDisplay(
            f"**{emoji} {count}** | {message.channel.mention} "
            f"by {message.author.mention}",
        ),
        SmallSeparator(),
    ]
    if body:
        items.append(discord.ui.Section(body, accessory=jump))
    elif not media_only:
        items.append(discord.ui.Section(NO_CONTENT, accessory=jump))
    if gallery:
        items.append(
            discord.ui.MediaGallery(
                *(discord.MediaGalleryItem(url) for url in gallery),
            ),
        )
    if files:
        items.append(discord.ui.TextDisplay(_file_lines(files)))
    if media_only:
        items.append(discord.ui.ActionRow(jump))

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(*items, accent_color=STARBOARD_COLOR))
    return view


@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
class StarboardCog(
    commands.GroupCog,
    name="starboard",
    description="Pin popular messages to a starboard channel.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db_path = DATA_DIR / "starboard.db"
        self._locks: dict[tuple[int, int], _Lock] = {}
        self._votes: OrderedDict[int, _CachedVotes] = OrderedDict()

    async def cog_load(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS starboard_posts (
                    guild_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    source_channel_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    post_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, message_id)
                )
                """,
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS starboard_posts_post
                ON starboard_posts (guild_id, post_id)
                """,
            )
            await db.commit()

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
            log.error(error)
            msg = ERROR_MESSAGE

        view = ErrorUI(msg)
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(
        name="config",
        description="Change starboard settings for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await open_config(interaction, "starboard")

    @asynccontextmanager
    async def _locked(self, key: tuple[int, int]) -> AsyncIterator[None]:
        entry = self._locks.get(key)
        if entry is None:
            entry = self._locks[key] = _Lock()
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if entry.users == 0:
                del self._locks[key]

    async def _post_row(
        self,
        guild_id: int,
        message_id: int,
    ) -> tuple[int, int] | None:
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute(
                "SELECT channel_id, post_id FROM starboard_posts "
                "WHERE guild_id = ? AND message_id = ?",
                (guild_id, message_id),
            ) as cursor,
        ):
            return await cursor.fetchone()

    async def _resolve(
        self,
        guild_id: int,
        message_id: int,
        channel_id: int,
    ) -> tuple[int, int]:
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute(
                "SELECT message_id, source_channel_id FROM starboard_posts "
                "WHERE guild_id = ? AND post_id = ?",
                (guild_id, message_id),
            ) as cursor,
        ):
            row = await cursor.fetchone()
        return row if row is not None else (message_id, channel_id)

    async def _save_post(
        self,
        guild_id: int,
        message_id: int,
        source_channel_id: int,
        channel_id: int,
        post_id: int,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO starboard_posts "
                "(guild_id, message_id, source_channel_id, channel_id, post_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (guild_id, message_id, source_channel_id, channel_id, post_id),
            )
            await db.commit()

    async def _forget(self, guild_id: int, message_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM starboard_posts WHERE guild_id = ? AND message_id = ?",
                (guild_id, message_id),
            )
            await db.commit()

    def _record(
        self,
        source_id: int,
        emoji: str,
        user_id: int,
        message_id: int,
        *,
        add: bool,
    ) -> None:
        entry = self._votes.get(source_id)
        if entry is None:
            return
        reacted = entry.users.setdefault(emoji, {})
        if add:
            reacted.setdefault(user_id, set()).add(message_id)
        elif user_id in reacted:
            reacted[user_id].discard(message_id)
            if not reacted[user_id]:
                del reacted[user_id]

    async def _fetch_post(
        self,
        channel: discord.abc.GuildChannel | None,
        post: tuple[int, int] | None,
    ) -> discord.Message | None:
        if post is None or not isinstance(channel, discord.TextChannel):
            return None
        try:
            return await channel.fetch_message(post[1])
        except discord.HTTPException:
            return None

    async def _votes_for(
        self,
        message: discord.Message,
        post_channel: discord.abc.GuildChannel | None,
        post: tuple[int, int] | None,
    ) -> Votes:
        entry = self._votes.get(message.id)
        if entry is not None and time.monotonic() - entry.stamp < VOTE_CACHE_SECONDS:
            self._votes.move_to_end(message.id)
            return entry.users

        post_message = await self._fetch_post(post_channel, post)
        users: Votes = {}
        for found in (message, post_message):
            if found is None:
                continue
            for reaction in found.reactions:
                reacted = users.setdefault(str(reaction.emoji), {})
                async for user in reaction.users():
                    if not user.bot:
                        reacted.setdefault(user.id, set()).add(found.id)

        self._votes[message.id] = _CachedVotes(time.monotonic(), users)
        self._votes.move_to_end(message.id)
        while len(self._votes) > VOTE_CACHE_SIZE:
            self._votes.popitem(last=False)
        return users

    def _count(
        self,
        users: Votes,
        settings: dict[str, str | None],
        author_id: int,
    ) -> tuple[int, str]:
        emojis = _emoji_list(settings["emojis"])
        fallback = emojis[0] if emojis else DEFAULT_EMOJI
        any_emoji = settings["any_emoji"] == "on"
        self_star = settings["self_star"] == "on"

        watched = {
            emoji: reacted
            for emoji, reacted in users.items()
            if any_emoji or emoji in emojis
        }
        voters: set[int] = set()
        for reacted in watched.values():
            voters.update(reacted)
        if not self_star:
            voters.discard(author_id)

        display = max(watched, key=lambda emoji: len(watched[emoji]), default=fallback)
        return len(voters), display

    async def _create_post(
        self,
        guild_id: int,
        channel: discord.TextChannel,
        message: discord.Message,
        emoji: str,
        count: int,
    ) -> None:
        try:
            post = await channel.send(
                view=_build_view(message, emoji, count),
                allowed_mentions=NO_PINGS,
            )
        except discord.HTTPException:
            log.warning(
                "Couldn't post message %s to the starboard in guild %s",
                message.id,
                guild_id,
            )
            return
        await self._save_post(
            guild_id,
            message.id,
            message.channel.id,
            channel.id,
            post.id,
        )

    async def _update_post(
        self,
        guild: discord.Guild,
        post: tuple[int, int],
        message: discord.Message,
        emoji: str,
        count: int,
    ) -> bool:
        channel_id, post_id = post
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False
        try:
            await channel.get_partial_message(post_id).edit(
                view=_build_view(message, emoji, count),
            )
        except discord.NotFound:
            return False
        except discord.HTTPException:
            log.warning(
                "Couldn't update starboard post %s in guild %s",
                post_id,
                guild.id,
            )
        return True

    async def _delete_post(
        self,
        guild: discord.Guild,
        message_id: int,
        post: tuple[int, int],
    ) -> None:
        await self._forget(guild.id, message_id)
        channel_id, post_id = post
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.get_partial_message(post_id).delete()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            log.warning(
                "Couldn't delete starboard post %s in guild %s",
                post_id,
                guild.id,
            )

    async def _refresh(
        self,
        guild: discord.Guild,
        source: SourceChannel,
        message_id: int,
        settings: dict[str, str | None],
    ) -> None:
        star_channel = guild.get_channel(int(settings["channel"]))
        if not isinstance(star_channel, discord.TextChannel):
            return

        try:
            message = await source.fetch_message(message_id)
        except discord.HTTPException:
            return
        if message.author.bot:
            return

        threshold = int(settings["threshold"])
        post = await self._post_row(guild.id, message.id)
        post_channel = guild.get_channel(post[0]) if post is not None else None
        blocked = _is_nsfw(source) and not star_channel.is_nsfw()

        try:
            if blocked:
                count, emoji = 0, DEFAULT_EMOJI
            else:
                users = await self._votes_for(message, post_channel, post)
                count, emoji = self._count(users, settings, message.author.id)
        except discord.HTTPException:
            log.warning("Couldn't count reactions on message %s", message.id)
            return

        if count < threshold:
            if post is not None:
                await self._delete_post(guild, message.id, post)
            return

        if post is None or not await self._update_post(
            guild,
            post,
            message,
            emoji,
            count,
        ):
            await self._create_post(guild.id, star_channel, message, emoji, count)

    async def _handle_reaction(
        self,
        payload: discord.RawReactionActionEvent,
        *,
        add: bool,
    ) -> None:
        if payload.guild_id is None or not await module_settings.is_enabled(
            payload.guild_id,
            "starboard",
        ):
            return
        if add and payload.member is not None and payload.member.bot:
            return

        settings = await module_config.get_all(payload.guild_id, "starboard")
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None or not settings["channel"]:
            return

        source_id, source_channel_id = await self._resolve(
            payload.guild_id,
            payload.message_id,
            payload.channel_id,
        )
        source = guild.get_channel_or_thread(source_channel_id)
        if not isinstance(source, SourceChannel):
            return

        emoji = str(payload.emoji)
        async with self._locked((payload.guild_id, source_id)):
            self._record(
                source_id,
                emoji,
                payload.user_id,
                payload.message_id,
                add=add,
            )
            if not _watches(settings, emoji) or not _in_sources(
                source,
                settings["sources"],
            ):
                return
            await self._refresh(guild, source, source_id, settings)

    async def _drop_source(self, guild_id: int | None, message_id: int) -> None:
        if guild_id is None:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        async with self._locked((guild_id, message_id)):
            self._votes.pop(message_id, None)
            post = await self._post_row(guild_id, message_id)
            if post is not None:
                await self._delete_post(guild, message_id, post)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.guild is None
            or message.author.bot
            or message.is_system()
            or not isinstance(message.channel, SourceChannel)
            or not await module_settings.is_enabled(message.guild.id, "starboard")
        ):
            return

        settings = await module_config.get_all(message.guild.id, "starboard")
        if settings["auto_react"] != "on" or not settings["sources"]:
            return
        if not _in_sources(message.channel, settings["sources"]):
            return

        emoji = (_emoji_list(settings["emojis"]) or [DEFAULT_EMOJI])[0]
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            log.warning(
                "Couldn't add the starboard reaction in channel %s of guild %s",
                message.channel.id,
                message.guild.id,
            )

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.guild_id is None or not await module_settings.is_enabled(
            payload.guild_id,
            "starboard",
        ):
            return

        settings = await module_config.get_all(payload.guild_id, "starboard")
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None or not settings["channel"]:
            return

        async with self._locked((payload.guild_id, payload.message_id)):
            if await self._post_row(payload.guild_id, payload.message_id) is None:
                return
            source = guild.get_channel_or_thread(payload.channel_id)
            if isinstance(source, SourceChannel):
                await self._refresh(guild, source, payload.message_id, settings)

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        await self._handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        await self._handle_reaction(payload, add=False)

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self,
        payload: discord.RawMessageDeleteEvent,
    ) -> None:
        await self._drop_source(payload.guild_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(
        self,
        payload: discord.RawBulkMessageDeleteEvent,
    ) -> None:
        for message_id in payload.message_ids:
            await self._drop_source(payload.guild_id, message_id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM starboard_posts WHERE guild_id = ? AND channel_id = ?",
                (channel.guild.id, channel.id),
            )
            await db.commit()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM starboard_posts WHERE guild_id = ?",
                    (guild.id,),
                )
                await db.commit()
            await module_config.clear_module(guild.id, "starboard")
        except Exception:
            log.exception("Couldn't clean up starboard data for guild %s", guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StarboardCog(bot))
