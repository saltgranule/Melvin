import json
import logging
import urllib.parse

import discord
from discord.ext import commands, tasks

import articles
from globals import ARTICLE_CHANNEL, DATA_DIR, MELVIN_EMOJI, WEBSITE_URL
from helpers.files import write_json
from ui import GalleryWithItem, SmallSeparator

log = logging.getLogger(__name__)

POSTED_FILE = DATA_DIR / "posted_articles.json"
CHECK_MINUTES = 5


def _load_posted() -> set[str] | None:
    try:
        return set(json.loads(POSTED_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None


def _article_view(article: dict) -> discord.ui.LayoutView:
    url = f"{WEBSITE_URL}/articles/{urllib.parse.quote(article['slug'])}"
    card = discord.ui.Container(
        discord.ui.TextDisplay(f"**{article['title']}**\n-# **{article['summary']}**"),
    )
    if article["thumbnail"]:
        card.add_item(GalleryWithItem(f"{WEBSITE_URL}/static/{article['thumbnail']}"))
    card.add_item(SmallSeparator())
    card.add_item(
        discord.ui.ActionRow(
            discord.ui.Button(label="Read", style=discord.ButtonStyle.link, url=url),
        ),
    )

    view = discord.ui.LayoutView()
    view.add_item(
        discord.ui.TextDisplay(
            f"{MELVIN_EMOJI} **new article**\n"
            f"A new article for Melvin has released, read [here]({url}).",
        ),
    )
    view.add_item(card)
    return view


class ArticleFeedCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.check_articles.start()

    async def cog_unload(self) -> None:
        self.check_articles.cancel()

    @tasks.loop(minutes=CHECK_MINUTES)
    async def check_articles(self) -> None:
        try:
            await self._post_new()
        except Exception:
            log.exception("Checking for new articles failed")

    @check_articles.before_loop
    async def _wait_for_bot(self) -> None:
        await self.bot.wait_until_ready()

    async def _post_new(self) -> None:
        current = articles.all_articles()
        posted = _load_posted()
        if posted is None:
            write_json(POSTED_FILE, sorted(a["slug"] for a in current))
            return

        channel = self.bot.get_channel(ARTICLE_CHANNEL)
        if not isinstance(channel, discord.TextChannel):
            log.warning("The articles channel %s isn't available", ARTICLE_CHANNEL)
            return

        # older first, so in order
        for article in reversed(current):
            if article["slug"] in posted:
                continue
            try:
                message = await channel.send(view=_article_view(article))
            except discord.HTTPException:
                log.exception("Couldn't post the article %s", article["slug"])
                continue
            posted.add(article["slug"])
            write_json(POSTED_FILE, sorted(posted))
            if channel.is_news():
                try:
                    await message.publish()
                except discord.HTTPException:
                    log.warning("Couldn't publish the article %s", article["slug"])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ArticleFeedCog(bot))
