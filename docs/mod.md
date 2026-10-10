# Mod Cog Documentation

Guild moderation commands. Guild only, all commands require this cog to run inside a server.

Command group name: `mod`

## Shared Behavior

**Duration parsing**

Used by the mute command. Takes a string like `10m`, `2h`, or `1d`. The last character must be `s`, `m`, `h`, or `d`, and everything before it must be a positive integer. If either check fails, parsing returns nothing and the command treats the duration as invalid.

**Case logging**

Every action command (warn, kick, ban, unban, mute, unmute, role add, role remove) inserts a row into a `mod_cases` table in `data/mod.db`.

The row stores the guild, target user, moderator, action type, reason, and timestamp. The table is created on cog load if it does not already exist. The inserted row's autoincrement ID becomes the case ID shown to the user.

**DM notification**

The bot tries to DM the target user a summary of the action, the reason, the case ID, and the guild name.

For mute, unmute, and unban, the action runs first, and the case is only logged and the DM only sent once it succeeds. Kick and ban send the DM before the action, since the bot usually can't DM someone after they've left the guild. If the kick or ban then fails, the logged case is removed again.

If the DM fails for any reason (DMs closed, blocked, etc.), it is silently ignored.

If Discord rejects the action itself, the command replies with a short error and the details are written to the bot's log.

**Guard clauses**

Most action commands share a common set of checks before running, in order:

- target is not a bot
- target is not the command user
- target is not the guild owner
- target's top role is not equal to or above the command user's top role, unless the command user is the guild owner
- target's top role is not equal to or above the bot's top role

Whichever check fails first stops the command and replies with an error describing the reason.

**Error handling**

Cog-wide:

- missing permissions on the user's side replies with a permission error
- missing permissions on the bot's side replies with a bot permission error
- any other unhandled error replies with a generic error message

All of these replies are ephemeral.

## /mod role

Give roles to members, or take them away.

### /mod role add

Add a role to a member.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to give the role to. |
| role | role | yes | The role to add. |
| reason | string | no | The reason for adding the role. Defaults to "No reason provided." |

**Permissions**

Requires Manage Roles.

**Behavior**

Rejects `@everyone` and the server booster role as target roles, bot targets, and members who already have the role. The booster role is given out by Discord to members who boost the server, so it can't be added by hand.

Also rejects role/hierarchy violations against both the command user and the bot, using the shared guard clause logic.

If all checks pass, logs a case as `role_add`, adds the role, and confirms with the role, member, and case ID.

### /mod role remove

Remove a role from a member.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to remove the role from. |
| role | role | yes | The role to remove. |
| reason | string | no | The reason for removing the role. Defaults to "No reason provided." |

**Permissions**

Requires Manage Roles.

**Behavior**

Rejects `@everyone` as a target role, bot targets, and members who do not have the role.

Also rejects role/hierarchy violations against both the command user and the bot, using the shared guard clause logic.

If all checks pass, logs a case as `role_remove`, removes the role, and confirms with the role, member, and case ID.

## /mod case

View and remove moderation cases.

### /mod case view

View moderation cases for a user.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| target | user | yes | The target user to view cases for. |

**Permissions**

Requires Moderate Members.

**Behavior**

Rejects bot targets.

Otherwise builds a paginated case view for the target user, pulling all logged cases from the database.

### /mod case remove

Remove a mod action from a user's record.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| case_id | integer | yes | The case ID to remove, typically DMed to the user or found via `/mod case view`. |

**Permissions**

Requires Moderate Members.

**Behavior**

Looks up the case ID within the current guild.

If no matching case exists, replies with an error naming the case ID. Otherwise deletes the row and confirms with the case ID, action type, and affected user.

## /mod warn

Warn a member.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to warn. |
| reason | string | no | The reason for the warning. Defaults to "No reason provided." |

**Permissions**

Requires Moderate Members.

**Behavior**

Rejects bot targets, self-warns, warning the guild owner, and warning someone whose top role is equal to or above the command user's (unless the command user is the guild owner).

Logs a case as `warn`, attempts a DM to the target, and confirms with the member and case ID.

## /mod kick

Kick a member.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to kick. |
| reason | string | no | The reason for the kick. Defaults to "No reason provided." |

**Permissions**

Requires Kick Members.

**Behavior**

Runs the shared guard clauses.

Logs a case as `kick`, attempts a DM to the target before the kick happens, then performs the kick with the reason attributed to the command user. If the kick fails, the case is removed.

Confirms with the member and case ID.

## /mod ban

Ban a member.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to ban. |
| reason | string | no | The reason for the ban. Defaults to "No reason provided." |

**Permissions**

Requires Ban Members.

**Behavior**

Runs the shared guard clauses.

Logs a case as `ban`, attempts a DM to the target before the ban happens, then performs the ban with a 7 day message deletion window and the reason attributed to the command user. If the ban fails, the case is removed.

Confirms with the member and case ID.

## /mod unban

Unban a user.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| user | user | yes | The user to unban. |
| reason | string | no | The reason for the unban. Defaults to "No reason provided." |

**Permissions**

Requires Ban Members.

**Behavior**

Checks whether the user is actually banned first.

If not banned, replies with an error. If the ban check itself fails for some other reason, replies with that error instead.

Otherwise unbans the user with the reason attributed to the command user, then logs a case as `unban` and confirms with the user and case ID.

## /mod mute

Mute a member using Discord's timeout feature.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to mute. |
| duration | string | yes | The duration of the mute, e.g. `10m`, `2h`, `1d`. |
| reason | string | no | The reason for the mute. Defaults to "No reason provided." |

**Permissions**

Requires Moderate Members.

**Behavior**

Parses the duration first. If invalid, replies with an error. If the duration exceeds 28 days (Discord's timeout cap), replies with an error.

Otherwise runs the shared guard clauses.

Applies a timeout until the parsed duration has elapsed, with the reason attributed to the command user, then logs a case as `mute` and attempts a DM to the target.

Confirms with the member and case ID.

## /mod unmute

Remove a member's timeout early.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to unmute. |
| reason | string | no | The reason for the unmute. Defaults to "No reason given." |

**Permissions**

Requires Moderate Members.

**Behavior**

Checks that the member is actually timed out, replying with an error if not.

Checks the role hierarchy between the command user and the target, replying with an error if the target is equal to or above the command user's top role, unless the command user is the guild owner.

Otherwise clears the timeout with the reason attributed to the command user, then logs a case as `unmute`, attempts a DM to the target, and confirms with the member and case ID.

## /mod lock

Lock a channel or thread, preventing regular members from sending messages.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| channel | channel or thread | no | The channel or thread to lock. Defaults to the current channel. |
| reason | string | no | The reason for locking. Defaults to "No reason given." |

**Permissions**

Requires Manage Channels.

**Behavior**

Only works on text channels, voice channels, or threads, replying with an error otherwise.

For threads: checks if already locked and replies with an error if so, otherwise sets the thread's locked flag.

For channels: checks the `@everyone` role's `send_messages` overwrite, replying with an error if it's already set to deny, otherwise sets it to deny.

Confirms with the channel or thread that was locked. No case is logged for this command.

## /mod unlock

Unlock a channel or thread.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| channel | channel or thread | no | The channel or thread to unlock. Defaults to the current channel. |
| reason | string | no | The reason for unlocking. Defaults to "No reason given." |

**Permissions**

Requires Manage Channels.

**Behavior**

Only works on text channels, voice channels, or threads, replying with an error otherwise.

For threads: checks if already unlocked and replies with an error if so, otherwise clears the thread's locked flag.

For channels: checks the `@everyone` role's `send_messages` overwrite, replying with an error if it isn't currently set to deny, otherwise resets the overwrite to neutral (inherited).

Confirms with the channel or thread that was unlocked. No case is logged for this command.

## /mod config
Change moderation settings for this server.

**Parameters**
None.

**Permissions**
Requires Manage Server. Guild only.

**Behavior**
The command replies with a settings card listing each setting, what it does, and its current value. Channels and roles are picked from a select menu, and deselecting clears them. Other settings have an Edit button that opens a form, and leaving the form empty resets the setting to its default.
Each change saves straight away and the card updates in place. Only members with Manage Server can use the card, and it stops responding after 5 minutes.
The same settings can be changed from the dashboard on the website, under Config on the module's card.

**Settings**

| Setting | Description |
|------|--------------|
| Auto-role | Given to members when they join. Leave empty for none. Changing it also requires Manage Roles. |

The auto-role can't be `@everyone`, a role managed by an app, a role equal to or above Melvin's top role, or a role equal to or above the command user's top role unless they are the guild owner. The dashboard only lists roles that pass these checks.
When a member joins, the bot gives them the auto-role. If the role has since been deleted, or the bot can't assign it, the member is skipped silently. Auto-roles are not logged as cases.
