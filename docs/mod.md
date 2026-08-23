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

After logging a case, the bot tries to DM the target user a summary of the action, the reason, the case ID, and the guild name.

If the DM fails for any reason (DMs closed, blocked, etc.), it is silently ignored, since the action itself has already succeeded.

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

## role command group

Path: `/mod role`

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

Rejects `@everyone` as a target role, bot targets, and members who already have the role.

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

## case command group

Path: `/mod case`

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

## warn command

Path: `/mod warn`

Warn a member.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| member | member | yes | The member to warn. |
| reason | string | no | The reason for the warning. Defaults to "No reason provided." |

**Permissions**

Requires Moderate Members.

**Behavior**

Rejects bot targets, self-warns, and warning the guild owner.

Logs a case as `warn`, attempts a DM to the target, and confirms with the member and case ID.

## kick command

Path: `/mod kick`

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

Logs a case as `kick`, attempts a DM to the target before the kick happens, then performs the kick with the reason attributed to the command user.

Confirms with the member and case ID.

## ban command

Path: `/mod ban`

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

Logs a case as `ban`, attempts a DM to the target before the ban happens, then performs the ban with a 7 day message deletion window and the reason attributed to the command user.

Confirms with the member and case ID.

## unban command

Path: `/mod unban`

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

Otherwise logs a case as `unban`, unbans the user with the reason attributed to the command user, and confirms with the user and case ID.

## mute command

Path: `/mod mute`

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

Logs a case as `mute`, attempts a DM to the target, then applies a timeout until the parsed duration has elapsed, with the reason attributed to the command user.

Confirms with the member and case ID.

## unmute command

Path: `/mod unmute`

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

Otherwise logs a case as `unmute`, attempts a DM to the target, clears the timeout with the reason attributed to the command user, and confirms with the member and case ID.

## lock command

Path: `/mod lock`

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

## unlock command

Path: `/mod unlock`

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