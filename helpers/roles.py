"""Role checks shared by moderation and reaction roles."""

import discord

# audit log reason used when a reaction role panel changes a member's roles.
# audit.py checks this prefix so these changes are logged, not treated as mod actions.
REACTION_ROLE_REASON = "Reaction roles"


def actor_role_error(
    guild: discord.Guild,
    actor: discord.Member,
    role: discord.Role,
) -> str | None:
    # the person giving the role must outrank it, unless they own the guild
    if role.position >= actor.top_role.position and actor.id != guild.owner_id:
        return "You tried to manage a role equal to or above your top role."
    return None


def bot_role_error(guild: discord.Guild, role: discord.Role) -> str | None:
    if role.position >= guild.me.top_role.position:
        return "I tried to manage a role equal to or above my top role."
    return None


def assignable_error(role: discord.Role) -> str | None:
    if role.is_default():
        return "You cannot use the @everyone role."
    if role.is_premium_subscriber():
        return "You cannot use the server booster role; Discord gives it to boosters."
    if role.managed:
        return "That role is managed by an integration."
    return None
