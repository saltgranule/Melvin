# ruff: file-ignore[private-member-access]
# pyright: reportPrivateUsage = false
import contextlib
from collections.abc import Sequence

import discord

from ui import ErrorUI

from .views import ExceptionUI, LargeSeparator

__all__ = ["Paginator"]

type _ItemsList = list[discord.ui.Item[discord.ui.LayoutView]]
type _ItemsOrStrList = Sequence[str | discord.ui.Item[discord.ui.LayoutView]]
type _TitleButton = discord.ui.Button[Paginator]


class _PageJumpModal(discord.ui.Modal, title="Jump to Page"):
    def __init__(self, paginator: Paginator) -> None:
        super().__init__()
        self.paginator = paginator

        max_digits = len(str(len(paginator.pages)))

        self._page_input = discord.ui.TextInput(
            placeholder="ex: 5",
            min_length=1,
            max_length=max_digits,
        )
        self.page_input = discord.ui.Label(
            text="Enter a page number.",
            description="Enter a positive integer greater than or equal to one.",
            component=self._page_input,
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            page = int(self._page_input.value) - 1
        except ValueError:
            await interaction.response.send_message(
                view=ErrorUI("Enter a positive integer greater than or equal to one."),
                ephemeral=True,
            )
            return

        if page == self.paginator.current_page:
            await interaction.response.send_message(
                view=ErrorUI("You are already viewing this page."),
                ephemeral=True,
            )
            return

        if 0 <= page < len(self.paginator.pages):
            await self.paginator._turn(interaction, page)

        else:
            await interaction.response.send_message(
                view=ErrorUI(
                    f"Enter a page between 1 and {len(self.paginator.pages)}.",
                ),
                ephemeral=True,
            )


class _PageRow(discord.ui.ActionRow["Paginator"]):
    def __init__(self, paginator: Paginator) -> None:
        super().__init__()
        self.paginator = paginator

        if len(paginator.pages) == 2:
            self.remove_item(self.btn_first)
            self.remove_item(self.btn_page)
            self.remove_item(self.btn_last)
        elif len(paginator.pages) == 3:
            self.remove_item(self.btn_page)

        self.update_states()

    def update_states(self) -> None:
        current = self.paginator.current_page
        total = len(self.paginator.pages)

        is_first = current == 0
        is_last = current == total - 1

        if total >= 3:
            self.btn_first.disabled = is_first
            self.btn_last.disabled = is_last
            self.btn_page.label = f"{current + 1} / {total}"

        self.btn_backward.disabled = is_first
        self.btn_forward.disabled = is_last

    @discord.ui.button(label="<<")
    async def btn_first(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[discord.ui.LayoutView],
    ) -> None:
        await self.paginator._turn(interaction, 0)

    @discord.ui.button(label="<")
    async def btn_backward(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[discord.ui.LayoutView],
    ) -> None:
        await self.paginator._turn(interaction, self.paginator.current_page - 1)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.green)
    async def btn_page(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[discord.ui.LayoutView],
    ) -> None:
        await interaction.response.send_modal(_PageJumpModal(self.paginator))

    @discord.ui.button(label=">")
    async def btn_forward(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[discord.ui.LayoutView],
    ) -> None:
        await self.paginator._turn(interaction, self.paginator.current_page + 1)

    @discord.ui.button(label=">>")
    async def btn_last(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[discord.ui.LayoutView],
    ) -> None:
        await self.paginator._turn(interaction, len(self.paginator.pages) - 1)


class Paginator(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        data: _ItemsOrStrList,
        /,
        *,
        data_name: str,
        per_page: int = 5,
        color: discord.Color | None = None,
        container: bool = False,
        force: bool = False,
        timeout: int | None = 600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None

        self._title: str = title
        self._data: _ItemsOrStrList = data
        self._data_name: str | None = data_name
        self._per_page: int = per_page
        self._color: discord.Color | None = color
        self._container: bool = container
        self._force: bool = force

        self.pages: list[_ItemsOrStrList] = [
            data[i : i + per_page] for i in range(0, len(data), per_page)
        ] or [["No content available."]]
        self.current_page: int = 0
        self._page_row: _PageRow | None = (
            _PageRow(self) if len(self.pages) >= 2 else None
        )

        self._above_items: _ItemsList = []
        self._over_items: _ItemsList = []
        self._under_items: _ItemsList = []
        self._below_items: _ItemsList = []
        self._title_button: _TitleButton | None = None

        if color and not container:
            error = "color is dependent on container"
            raise ValueError(error)

        self._render()

    async def on_timeout(self) -> None:
        if self.timeout is not None:
            for item in self.walk_children():
                if isinstance(item, discord.ui.Button | discord.ui.Select):
                    item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                with contextlib.suppress(discord.HTTPException):
                    await self.message.delete()

    def _get_page_footer(self) -> str:
        return f"-# Page {self.current_page + 1} of {len(self.pages)} | {len(self._data)} {self._data_name}"

    def add_above(self, *items: discord.ui.Item[discord.ui.LayoutView]) -> None:
        self._above_items.extend(items)
        self._render()

    def add_over(self, *items: discord.ui.Item[discord.ui.LayoutView]) -> None:
        self._over_items.extend(items)
        self._render()

    def add_under(self, *items: discord.ui.Item[discord.ui.LayoutView]) -> None:
        self._under_items.extend(items)
        self._render()

    def add_below(self, *items: discord.ui.Item[discord.ui.LayoutView]) -> None:
        self._below_items.extend(items)
        self._render()

    def set_title_button(self, button: _TitleButton | None, /) -> None:
        self._title_button = button
        self._render()

    def update_data(self, title: str, data: _ItemsOrStrList) -> None:
        self._title = title
        self._data = data
        self.current_page = 0

        self.pages = [
            data[i : i + self._per_page] for i in range(0, len(data), self._per_page)
        ] or [["No content available."]]

        self._page_row = _PageRow(self) if len(self.pages) >= 2 else None

        self._render()

    def _render(self) -> None:
        self.clear_items()

        for item in self._above_items:
            self.add_item(item)

        page_items: _ItemsList = []

        if self._force:
            page_items = [
                discord.ui.TextDisplay(item) if isinstance(item, str) else item
                for item in self.pages[self.current_page]
            ]
        else:
            accumulated: list[str] = []

            for item in self.pages[self.current_page]:
                if isinstance(item, str):
                    accumulated.append(item)
                else:
                    if accumulated:
                        page_items.append(
                            discord.ui.TextDisplay("\n".join(accumulated)),
                        )
                        accumulated.clear()
                    page_items.append(item)

            if accumulated:
                page_items.append(discord.ui.TextDisplay("\n".join(accumulated)))

        title_button = self._title_button

        title_item: discord.ui.Item[discord.ui.LayoutView] = (
            discord.ui.Section(self._title, accessory=title_button)
            if title_button is not None
            else discord.ui.TextDisplay(self._title)
        )

        items: _ItemsList = [
            *self._over_items,
            title_item,
            LargeSeparator(),
            *page_items,
            LargeSeparator(),
            discord.ui.TextDisplay(self._get_page_footer()),
        ]

        if self._page_row:
            self._page_row.update_states()
            items.append(self._page_row)

        items.extend(self._under_items)

        if self._container:
            self.add_item(discord.ui.Container(*items, accent_color=self._color))
        else:
            for item in items:
                self.add_item(item)

        for item in self._below_items:
            self.add_item(item)

    async def _turn(self, interaction: discord.Interaction, target: int) -> None:
        if 0 <= target < len(self.pages):
            previous_page = self.current_page

            self.current_page = target
            self._render()

            try:
                await interaction.response.edit_message(view=self)
            except Exception:
                self.current_page = previous_page
                self._render()
                await interaction.response.send_message(
                    view=ExceptionUI(),
                    ephemeral=True,
                )
                raise
