import re
import shlex
from dataclasses import dataclass

import discord

ARG = re.compile(
    r"(?P<name>[a-z][a-z0-9_]{0,19})(?P<optional>\?)?:(?P<kind>[a-z]+)"
    r"(?::(?P<low>-?\d+)-(?P<high>-?\d+))?",
)
ARG_KINDS = ("word", "text", "number", "member", "role", "channel")
PERMISSIONS = (
    "administrator",
    "manage_guild",
    "manage_messages",
    "manage_channels",
    "manage_roles",
    "kick_members",
    "ban_members",
    "moderate_members",
)
SNOWFLAKE = re.compile(r"<(?:@[!&]?|#)?(\d{15,21})>|(\d{15,21})")
ARGS_LENGTH = 500


class CommandError(ValueError):
    pass


@dataclass(frozen=True)
class ArgSpec:
    name: str
    kind: str
    optional: bool
    low: int | None
    high: int | None


def split_args(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def snowflake(text: str) -> int | None:
    match = SNOWFLAKE.fullmatch(text.strip())
    if match is None:
        return None
    return int(match[1] or match[2])


def parse_args(spec: str) -> list[ArgSpec]:
    specs: list[ArgSpec] = []
    for token in spec.split():
        match = ARG.fullmatch(token.lower())
        if match is None:
            msg = f"`{token}` isn't a valid argument. Use name:type, like amount:number:1-100."
            raise CommandError(msg)

        name, kind = match["name"], match["kind"]
        if kind not in ARG_KINDS:
            msg = f"`{kind}` isn't an argument type. Types are {', '.join(ARG_KINDS)}."
            raise CommandError(msg)
        if any(existing.name == name for existing in specs):
            msg = f"`{name}` is used more than once."
            raise CommandError(msg)
        if any(existing.kind == "text" for existing in specs):
            msg = "`text` has to be last, since it takes the rest."
            raise CommandError(msg)

        low = high = None
        if match["low"] is not None:
            if kind != "number":
                msg = "Only `number` arguments can have a range."
                raise CommandError(msg)
            low, high = int(match["low"]), int(match["high"])
            if low > high:
                msg = f"The range for `{name}` starts above where it ends."
                raise CommandError(msg)

        optional = bool(match["optional"])
        if not optional and any(existing.optional for existing in specs):
            msg = "Required arguments have to come before optional ones."
            raise CommandError(msg)
        specs.append(ArgSpec(name, kind, optional, low, high))
    return specs


async def _convert(spec: ArgSpec, token: str, guild: discord.Guild) -> str:
    if spec.kind == "word":
        return token
    if spec.kind == "number":
        if not re.fullmatch(r"-?\d+", token):
            msg = f"`{spec.name}` has to be a whole number."
            raise CommandError(msg)
        number = int(token)
        if spec.low is not None and spec.high is not None and not spec.low <= number <= spec.high:
            msg = f"`{spec.name}` has to be between {spec.low} and {spec.high}."
            raise CommandError(msg)
        return str(number)

    value = snowflake(token)
    if value is None:
        msg = f"`{spec.name}` has to be a {spec.kind}, like a mention or an ID."
        raise CommandError(msg)

    if spec.kind == "member":
        member = guild.get_member(value)
        if member is None:
            try:
                member = await guild.fetch_member(value)
            except discord.HTTPException:
                msg = f"`{spec.name}` isn't a member of this server."
                raise CommandError(msg) from None
        return member.mention
    if spec.kind == "role":
        role = guild.get_role(value)
        if role is None:
            msg = f"`{spec.name}` isn't a role in this server."
            raise CommandError(msg)
        return role.mention
    channel = guild.get_channel(value)
    if channel is None:
        msg = f"`{spec.name}` isn't a channel in this server."
        raise CommandError(msg)
    return channel.mention


async def bind_args(guild: discord.Guild, specs: list[ArgSpec], raw: str) -> list[str]:
    tokens = split_args(raw) if raw.strip() else []
    values: list[str] = []
    index = 0
    for spec in specs:
        if spec.kind == "text":
            rest = " ".join(tokens[index:])
            index = len(tokens)
            if rest:
                values.append(rest)
            elif spec.optional:
                values.append("")
            else:
                msg = f"Missing `{spec.name}`."
                raise CommandError(msg)
            continue

        if index >= len(tokens):
            if spec.optional:
                values.append("")
                continue
            msg = f"Missing `{spec.name}`."
            raise CommandError(msg)
        values.append(await _convert(spec, tokens[index], guild))
        index += 1

    if index < len(tokens):
        if not specs:
            msg = "This command doesn't take arguments."
        else:
            msg = f"Too many arguments. This command takes {len(specs)}."
        raise CommandError(msg)
    return values


def access_error(member: discord.Member, permission: str) -> str | None:
    if permission == "none":
        return None
    if permission.startswith("role:"):
        role_id = int(permission[5:])
        if any(role.id == role_id for role in member.roles):
            return None
        return f"You need <@&{role_id}> to use this."
    perms = member.guild_permissions
    if perms.administrator or getattr(perms, permission):
        return None
    return f"You need the {permission.replace('_', ' ').title()} permission to use this."


def describe_permission(permission: str) -> str:
    if permission == "none":
        return "Everyone"
    if permission.startswith("role:"):
        return f"<@&{permission[5:]}>"
    return permission.replace("_", " ").title()


def clean_args(args: str) -> str:
    if len(args) > ARGS_LENGTH:
        msg = f"Arguments can be at most {ARGS_LENGTH} characters."
        raise CommandError(msg)
    parse_args(args)
    return " ".join(args.split())


def clean_permission(permission: str) -> str:
    text = permission.strip().lower()
    if text in {"", "none"}:
        return "none"
    if text in PERMISSIONS:
        return text
    raw = permission.strip()
    if raw.startswith("<@&") or raw.isdigit():
        value = snowflake(raw)
        if value is not None:
            return f"role:{value}"
    msg = "Permission is `none`, a permission like `manage_messages`, or a role."
    raise CommandError(msg)
