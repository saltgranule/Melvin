import discord
from discord import app_commands
from discord.ext import commands

from module_registry import Module
from ui import ErrorUI, GalleryWithItem, Paginator, SmallSeparator

MODULE = Module(
    "info",
    "Info",
    "View avatars, banners, roles, and servers.",
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


def _role_color(role: discord.Role, enhanced: bool) -> str:
    if enhanced and role.tertiary_color is not None:
        return f"{role.color}-{role.secondary_color}-{role.tertiary_color} | Holographic"
    if enhanced and role.secondary_color is not None:
        return f"{role.color}-{role.secondary_color} | Gradient"
    return f"{role.color} | Solid"


def _role_hierarchy(role: discord.Role, roles: list[discord.Role]) -> str:
    # roles are sorted lowest first, so walk down from three above to three below
    index = roles.index(role)
    lines = []
    for i in range(index + 3, index - 4, -1):
        if 0 <= i < len(roles):
            prefix = ">" if roles[i] == role else " "
            name = roles[i].name.replace("`", "")
            lines.append(f"{len(roles) - i:>4}.   {prefix} {name}")
    return "\n".join(lines)


class RoleMembersRow(discord.ui.ActionRow["RoleInfoView"]):
    def __init__(self, role: discord.Role) -> None:
        super().__init__()
        self.role = role

    @discord.ui.button(label="View Members")
    async def view_members(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button["RoleInfoView"],
    ) -> None:
        members = [f"{m.mention} | {m.name}" for m in self.role.members]
        view = Paginator(
            f"### {_role_mention(self.role)} Members",
            members,
            data_name="Members",
            per_page=10,
            container=True,
        )
        await interaction.response.send_message(
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = await interaction.original_response()


def _role_mention(role: discord.Role) -> str:
    return "@everyone" if role.is_default() else role.mention


class RoleInfoView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction, role: discord.Role) -> None:
        super().__init__(timeout=300)
        self.message: discord.Message | None = None

        guild = role.guild
        enhanced = "ENHANCED_ROLE_COLORS" in guild.features
        created = role.created_at

        details = "\n".join(
            (
                f"**Appearance:** {_role_color(role, enhanced)}",
                f"**Hoisted:** {'Yes' if role.hoist else 'No'}",
                f"**Mentionable:** {'Yes' if role.mentionable else 'No'}",
                f"**Number of Members:** {len(role.members)}",
                f"**Created at:** {discord.utils.format_dt(created, 'F')} | "
                f"{discord.utils.format_dt(created, 'R')}",
            ),
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"### {_role_mention(role)} | {role.id}"),
            SmallSeparator(),
            accent_color=role.color if role.color.value else None,
        )

        if isinstance(role.display_icon, discord.Asset):
            container.add_item(
                discord.ui.Section(
                    details,
                    accessory=discord.ui.Thumbnail(role.display_icon.url),
                ),
            )
        else:
            container.add_item(discord.ui.TextDisplay(details))

        # where the role sits compared to the command user's highest role
        user = interaction.user
        if isinstance(user, discord.Member) and not user.top_role.is_default():
            if role == user.top_role:
                diff = "This is your highest role."
            elif role > user.top_role:
                diff = "This role is above your highest role."
            else:
                diff = "This role is below your highest role."
            container.add_item(discord.ui.TextDisplay(diff))

        roles = sorted(guild.roles, key=lambda r: r.position)
        container.add_item(
            discord.ui.TextDisplay(
                f"**Relative Hierarchy**\n```\n{_role_hierarchy(role, roles)}\n```",
            ),
        )
        container.add_item(RoleMembersRow(role))
        self.add_item(container)

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


VERIFICATION_LEVELS = {
    discord.VerificationLevel.none: ("None", "Unrestricted"),
    discord.VerificationLevel.low: ("Low", "Must have a verified email"),
    discord.VerificationLevel.medium: ("Medium", "Registered on Discord for 5+ minutes"),
    discord.VerificationLevel.high: ("High", "Member of the server for 10+ minutes"),
    discord.VerificationLevel.highest: ("Highest", "Must have a verified phone number"),
}


# i was too lazy to grab the emoji's for these, will do later
def _server_type(guild: discord.Guild) -> str | None:
    features = guild.features
    if "PARTNERED" in features:
        return "Partnered"
    if "VERIFIED" in features:
        return "Verified"
    if "DISCOVERABLE" in features:
        return "Discoverable"
    if "COMMUNITY" in features:
        return "Community"
    return None


class ServerInfoView(discord.ui.LayoutView):
    def __init__(self, guild: discord.Guild, owner: discord.Member) -> None:
        super().__init__()

        member_total = guild.member_count or 0
        bots = sum(1 for member in guild.members if member.bot)
        humans = member_total - bots

        # i was too lazy to grab the emoji's for these, will do later
        channels = (
            f"{len(guild.text_channels)} text, "
            f"{len(guild.voice_channels)} voice, "
            f"{len(guild.categories)} categories, "
            f"{len(guild.stage_channels)} stage, "
            f"{len(guild.forums)} forums | "
            f"{len(guild.channels)} total"
        )

        level, requirement = VERIFICATION_LEVELS.get(
            guild.verification_level,
            ("Unknown", "Unknown"),
        )
        created = guild.created_at

        details = "\n".join(
            (
                f"**Owner:** {owner.mention} | {owner.id}",
                f"**Icon:** [Icon Link]({guild.icon.url})" if guild.icon else "**Icon:** None",
                f"**Verification:** {level} | {requirement}",
                f"**2FA:** {'Enabled' if guild.mfa_level else 'Disabled'}",
                f"**Roles:** {len(guild.roles)}",
                f"**Members:** {humans} humans, {bots} bots | {member_total} total",
                f"**Channels:** {channels}",
                f"**Server Boosts:** Level {guild.premium_tier} | "
                f"{guild.premium_subscription_count} boosts total",
                f"**Vanity Link:** {guild.vanity_url or 'None'}",
                f"**Created at:** {discord.utils.format_dt(created, 'F')} | "
                f"{discord.utils.format_dt(created, 'R')}",
            ),
        )

        server_type = _server_type(guild)
        title = (
            f"### {guild.name} | {server_type} | {guild.id}"
            if server_type
            else f"### {guild.name} | {guild.id}"
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay(title),
            SmallSeparator(),
            accent_color=owner.color if owner.color.value else None,
        )

        if guild.icon:
            container.add_item(
                discord.ui.Section(
                    details,
                    accessory=discord.ui.Thumbnail(guild.icon.url),
                ),
            )
        else:
            container.add_item(discord.ui.TextDisplay(details))

        if guild.banner:
            container.add_item(GalleryWithItem(guild.banner.url))

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

    @app_commands.command(name="role", description="View information about a role.")
    @app_commands.describe(role="The role you want to view.")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        await interaction.response.defer()
        view = RoleInfoView(interaction, role)
        view.message = await interaction.followup.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
            wait=True,
        )

    @app_commands.command(name="server", description="View information about this server.")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def server(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        guild = interaction.guild
        if guild is None:
            return

        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id or 0)
            except discord.HTTPException:
                await interaction.followup.send(
                    view=ErrorUI("Fetching the server owner failed."),
                    ephemeral=True,
                )
                return

        await interaction.followup.send(
            view=ServerInfoView(guild, owner),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoCog(bot))
