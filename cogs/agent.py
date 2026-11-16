import asyncio
import logging
import os
import time
import warnings
from datetime import UTC, datetime

import aiosqlite
import discord
from ddgs import DDGS
from discord import app_commands
from discord.ext import commands
from groq import AsyncGroq

from globals import DATA_DIR, MELVIN_EMOJI
from helpers.text import truncate
from module_registry import Module
from ui import ErrorUI, Paginator

MODULE = Module(
    "ai",
    "AI",
    "Ask a free AI model questions.",
)

warnings.filterwarnings("ignore", category=DeprecationWarning)

log = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "ai_usage.db"
RATE_LIMIT = 10
RATE_PERIOD = 60 * 60
GROQ_MODEL = "openai/gpt-oss-20b"
PAGE_SIZE = 2000
MAX_SOURCE_TITLE = 80
MAX_SOURCE_URL = 150
MAX_TITLE_PROMPT = 200
MAX_FOLLOW_UP = 1000
MAX_HISTORY_TURNS = 3
MAX_OLD_ANSWER = 1000

type Message = dict[str, str]

SYSTEM_PROMPT = (
    "Today's date is {date}. "
    "Try to keep responses tidy and brief, unless otherwise requested by the user. "
    "Contain responses in short, yet informative paragraphs, rather than graphs or tables or bulletpoints. "
    "Refrain from using emojis unless told to. "
)
SEARCH_PROMPT = (
    "Use the provided search context to ground your answer relative to today's date. "
)
QUERY_PROMPT = (
    "Rewrite the user's latest message into a short, standalone web search query, "
    "using the earlier conversation to fill in what it refers to. "
    "Reply with only the query, no quotes or explanation."
)
MAX_SEARCH_QUERY = 200


def paginate(text: str, size: int = PAGE_SIZE) -> list[str]:
    pages: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if len(candidate) > size:
            if current:
                pages.append(current)
            current = word
        else:
            current = candidate
    if current:
        pages.append(current)
    return pages or [""]


def _web_results(query: str, max_results: int = 5) -> list[dict[str, str]] | None:
    try:
        return list(DDGS().text(query, max_results=max_results))
    except Exception:
        return None


def _web_context(results: list[dict[str, str]] | None) -> str:
    if results is None:
        return "Could not fetch search context."
    if not results:
        return "No search context available."
    return "\n---\n".join(
        f"Source {i}:\nTitle: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}\n"
        for i, r in enumerate(results, 1)
    )


def _trim_old(message: Message) -> Message:
    if message["role"] != "assistant":
        return message
    return {**message, "content": truncate(message["content"], MAX_OLD_ANSWER)}


def _source_links(results: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for i, result in enumerate(results, 1):
        url = result.get("href")
        if (
            not url
            or not url.startswith(("https://", "http://"))
            or len(url) > MAX_SOURCE_URL
        ):
            continue
        title = (result.get("title") or url).replace("[", "(").replace("]", ")")
        title = truncate(title, MAX_SOURCE_TITLE)
        lines.append(f"-# {i}. [{discord.utils.escape_mentions(title)}](<{url}>)")
    return "\n".join(lines)


class FollowUpModal(discord.ui.Modal, title="Followup"):
    def __init__(self, cog: AgentCog, history: list[Message], *, search: bool) -> None:
        super().__init__()
        self.cog = cog
        self.history = history
        self._prompt_input = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            placeholder="ex: Can you explain that more simply?",
            min_length=1,
            max_length=MAX_FOLLOW_UP,
        )
        self.add_item(
            discord.ui.Label(
                text="Enter a follow-up question.",
                description=f"The last {MAX_HISTORY_TURNS} questions and answers are remembered.",
                component=self._prompt_input,
            ),
        )
        self._search_input = discord.ui.Checkbox(default=search)
        self.add_item(
            discord.ui.Label(
                text="Search the web",
                component=self._search_input,
            ),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self.cog.answer(
            interaction,
            self._prompt_input.value,
            history=self.history,
            search=self._search_input.value,
        )


class AnswerRow(discord.ui.ActionRow[Paginator]):
    def __init__(
        self,
        cog: AgentCog,
        user_id: int,
        prompt: str,
        ai_response: str,
        history: list[Message],
        *,
        search: bool,
    ) -> None:
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.prompt = prompt
        self.ai_response = ai_response
        self.history = history
        self.search = search
        self.btn_retry.label = "Retry without Search" if search else "Retry with Search"

    async def _is_asker(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            view=ErrorUI("**Only the person who asked can use this.**"),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Followup")
    async def btn_follow_up(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[Paginator],
    ) -> None:
        if not await self._is_asker(interaction):
            return
        turns = [
            *map(_trim_old, self.history),
            {"role": "user", "content": self.prompt},
            {"role": "assistant", "content": self.ai_response},
        ]
        await interaction.response.send_modal(
            FollowUpModal(
                self.cog,
                turns[-MAX_HISTORY_TURNS * 2 :],
                search=self.search,
            ),
        )

    @discord.ui.button(label="Retry with Search")
    async def btn_retry(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[Paginator],
    ) -> None:
        if not await self._is_asker(interaction):
            return
        await interaction.response.defer(thinking=True)
        await self.cog.answer(
            interaction,
            self.prompt,
            history=self.history,
            search=not self.search,
        )


class AgentCog(
    commands.GroupCog,
    name="ai",
    description="Self explanatory, ask a free AI model some stupid stuff.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.client = AsyncGroq(api_key=os.getenv("GROQ"))

    async def cog_load(self) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_requests (
                    user_id INTEGER NOT NULL,
                    timestamp INTEGER NOT NULL
                )
                """,
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_requests_user_ts "
                "ON ai_requests (user_id, timestamp)",
            )
            await db.commit()

    async def _check_rate_limit(self, user_id: int) -> tuple[bool, int, int]:
        now = int(time.time())
        async with (
            aiosqlite.connect(DB_PATH) as db,
            db.execute(
                "SELECT COUNT(*), MIN(timestamp) FROM ai_requests "
                "WHERE user_id = ? AND timestamp > ?",
                (user_id, now - RATE_PERIOD),
            ) as cursor,
        ):
            count, oldest = await cursor.fetchone()

        if count < RATE_LIMIT:
            return True, count, 0
        return False, count, max(0, oldest + RATE_PERIOD - now)

    async def _record_request(self, user_id: int) -> None:
        now = int(time.time())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO ai_requests (user_id, timestamp) VALUES (?, ?)",
                (user_id, now),
            )
            await db.execute(
                "DELETE FROM ai_requests WHERE timestamp <= ?",
                (now - RATE_PERIOD,),
            )
            await db.commit()

    async def _search_query(self, prompt: str, history: list[Message]) -> str:
        if not history:
            return prompt
        try:
            response = await self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": QUERY_PROMPT},
                    *history,
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                reasoning_effort="low",
            )
            query = (response.choices[0].message.content or "").strip().strip('"')
        except Exception:
            log.exception("Failed to rewrite follow-up search query")
            query = ""
        if not query:
            last = next(m["content"] for m in reversed(history) if m["role"] == "user")
            query = f"{last} {prompt}"
        return truncate(query, MAX_SEARCH_QUERY)

    async def query_groq(
        self,
        prompt: str,
        *,
        history: list[Message],
        use_search: bool = False,
    ) -> tuple[str, list[dict[str, str]]]:
        date = datetime.now(UTC).strftime("%B %d, %Y")
        system = SYSTEM_PROMPT.format(date=date)
        context = ""
        results: list[dict[str, str]] | None = None
        if use_search:
            system += SEARCH_PROMPT
            query = await self._search_query(prompt, history)
            results = await asyncio.to_thread(_web_results, query)
            search = _web_context(results)
            context = f"--- SEARCH CONTEXT ---\n{search}\n--- END CONTEXT ---\n"

        try:
            response = await self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    *history,
                    {
                        "role": "user",
                        "content": f"--- CURRENT DATE: {date} ---\n{context}\nUser Question: {prompt}",
                    },
                ],
                temperature=0.7,
            )
            text = response.choices[0].message.content
        except Exception as e:
            error = f"**Groq API Error: {e!s}.**"
            raise RuntimeError(error) from e

        if not text:
            raise RuntimeError("**Groq returned an empty response.**")
        return text, results or []

    @app_commands.command(
        name="ask",
        description="Ask a free AI model some stupid stuff.",
    )
    @app_commands.describe(
        prompt="The question or prompt to ask the AI model.",
        search="Whether to perform a web search for grounding context.",
    )
    @app_commands.checks.cooldown(2, 60)
    async def ask(
        self,
        interaction: discord.Interaction,
        prompt: str,
        *,
        search: bool = False,
    ) -> None:
        await interaction.response.defer()
        await self.answer(interaction, prompt, history=[], search=search)

    async def answer(
        self,
        interaction: discord.Interaction,
        prompt: str,
        *,
        history: list[Message],
        search: bool,
    ) -> None:
        allowed, used, retry_after = await self._check_rate_limit(interaction.user.id)
        if not allowed:
            minutes = max(1, retry_after // 60)
            await interaction.edit_original_response(
                view=ErrorUI(
                    f"**You've hit the limit of {RATE_LIMIT} requests per hour, try again in about {minutes} minute(s).**",
                ),
            )
            return

        try:
            start = time.perf_counter()
            ai_response, results = await self.query_groq(
                prompt,
                history=history,
                use_search=search,
            )
            elapsed = time.perf_counter() - start
            await self._record_request(interaction.user.id)

            shown_prompt = truncate(
                prompt.replace("`", "").replace("\n", " "),
                MAX_TITLE_PROMPT,
            )
            label = "Follow-up" if history else "Prompt"
            view = Paginator(
                f"# {label}: `{shown_prompt}`",
                paginate(ai_response),
                data_name="Pages",
                per_page=1,
                container=True,
                timeout=300,
            )
            view.set_title_button(
                discord.ui.Button(
                    label="Model",
                    style=discord.ButtonStyle.link,
                    url=f"https://huggingface.co/{GROQ_MODEL}",
                ),
            )
            grounding = (
                "Grounded using DDGS web search context"
                if search
                else "Generated without web search"
            )
            if sources := _source_links(results):
                view.add_under(discord.ui.TextDisplay(f"-# **Sources**\n{sources}"))
            remaining = max(0, RATE_LIMIT - used - 1)
            view.add_under(
                discord.ui.TextDisplay(
                    f"-# {MELVIN_EMOJI} **Took {elapsed:.1f}s. {remaining}/{RATE_LIMIT} requests left this hour.**\n"
                    f"-# **{grounding} using {GROQ_MODEL}.**",
                ),
                AnswerRow(
                    self,
                    interaction.user.id,
                    prompt,
                    ai_response,
                    history,
                    search=search,
                ),
            )
            view.message = await interaction.edit_original_response(view=view)
        except Exception:
            log.exception("Failure in agent command")
            await interaction.edit_original_response(
                view=ErrorUI("**Something went wrong. This is likely an API error.**"),
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AgentCog(bot))
