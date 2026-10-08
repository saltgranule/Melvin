import discord
from discord import app_commands
from discord.ext import commands

from module_registry import Module
from ui import ErrorUI, GalleryWithItem, SmallSeparator

MODULE = Module(
    "info",
    "Info",
    "View avatars and banners.",
)

TYPE_CHOICES = [
    app_commands.Choice(name="Global", value="global"),
    app_commands.Choice(name="Server", value="server"),
]


def _possessive(
    interaction: discord.Interaction,
    target: discord.User | discord.Member,
) -> str:
    if target == interaction.client.user:
        return "My"
    if target == interaction.user:
        return "Your"
    return f"{target.mention}'s"


def _subject(
    interaction: discord.Interaction,
    target: discord.User | discord.Member,
) -> str:
    if target == interaction.client.user:
        return "I do"
    if target == interaction.user:
        return "You do"
    return f"{target.mention} does"


def _format_buttons(asset: discord.Asset) -> list[discord.ui.Button]:
    formats = (
        ("png", "jpg", "webp", "gif")
        if asset.is_animated()
        else ("png", "jpg", "webp")
    )
    return [
        discord.ui.Button(
            label=fmt,
            style=discord.ButtonStyle.link,
            url=asset.with_format(fmt).url,
        )
        for fmt in formats
    ]


async def _fetch_member(
    interaction: discord.Interaction,
    target: discord.User | discord.Member,
) -> discord.Member | None:
    # fetched rather than cached, since cached members don't carry guild banners
    if interaction.guild is None:
        return None
    try:
        return await interaction.guild.fetch_member(target.id)
    except discord.NotFound:
        return None


class AssetView(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        asset: discord.Asset,
        *,
        custom: bool,
    ) -> None:
        super().__init__()

        text_display = discord.ui.TextDisplay(f"**{title}**")
        media_gallery = GalleryWithItem(asset.url)

        if custom:
            buttons = _format_buttons(asset)
        else:
            # default avatars only exist as png
            buttons = [
                discord.ui.Button(
                    label="Web",
                    style=discord.ButtonStyle.link,
                    url=asset.url,
                ),
            ]

        action_row = discord.ui.ActionRow(*buttons)
        container = discord.ui.Container(
            text_display,
            SmallSeparator(),
            media_gallery,
            action_row,
        )
        self.add_item(container)


class InfoCog(
    commands.GroupCog,
    name="info",
    description="Commands for viewing user information.",
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(name="avatar", description="View a user's avatar.")
    @app_commands.rename(scope="type")
    @app_commands.describe(
        user="The user whose avatar you want to view.",
        scope="Show the global avatar or the server avatar. Defaults to global.",
    )
    @app_commands.choices(scope=TYPE_CHOICES)
    async def avatar(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        scope: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()
        target = user or interaction.user
        possessive = _possessive(interaction, target)

        if scope is not None and scope.value == "server":
            if interaction.guild is None:
                await interaction.followup.send(
                    view=ErrorUI("Server avatars can only be viewed in a server."),
                    ephemeral=True,
                )
                return

            member = await _fetch_member(interaction, target)
            if member is not None and member.guild_avatar is not None:
                view = AssetView(
                    f"{possessive} Server Avatar",
                    member.guild_avatar,
                    custom=True,
                )
                await interaction.followup.send(
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

        # global, or a server avatar that isn't set
        if target.avatar is not None:
            view = AssetView(f"{possessive} Avatar", target.avatar, custom=True)
        else:
            view = AssetView(
                f"{possessive} Avatar",
                target.default_avatar,
                custom=False,
            )
        await interaction.followup.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="banner", description="View a user's banner.")
    @app_commands.rename(scope="type")
    @app_commands.describe(
        user="The user whose banner you want to view.",
        scope="Show the global banner or the server banner. Defaults to global.",
    )
    @app_commands.choices(scope=TYPE_CHOICES)
    async def banner(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        scope: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()

        target = user or interaction.user
        possessive = _possessive(interaction, target)

        if scope is not None and scope.value == "server":
            if interaction.guild is None:
                await interaction.followup.send(
                    view=ErrorUI("Server banners can only be viewed in a server."),
                    ephemeral=True,
                )
                return

            member = await _fetch_member(interaction, target)
            if member is not None and member.guild_banner is not None:
                view = AssetView(
                    f"{possessive} Server Banner",
                    member.guild_banner,
                    custom=True,
                )
                await interaction.followup.send(
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

        # global, or a server banner that isn't set
        fetched_user = await self.bot.fetch_user(target.id)

        if fetched_user.banner is None:
            await interaction.followup.send(
                view=ErrorUI(
                    f"{_subject(interaction, target)} not have a profile banner."
                ),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        view = AssetView(f"{possessive} Banner", fetched_user.banner, custom=True)
        await interaction.followup.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoCog(bot))
