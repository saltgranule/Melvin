# Audit Cog Documentation
Guild audit logging. Once a log channel is set, the bot posts a log message there whenever something notable happens in the guild.
Command group name: `audit`

## Storage
Log channels are stored in a SQLite database at `data/logging.db`, in a table called `log_channels`. Each row holds a guild id and the id of its log channel. The table is created automatically when the cog loads, if it does not already exist.
Setting a log channel for a guild that already has one will overwrite the old value.

## channel command
Path: `/audit channel`
Set or reset the channel for guild logs.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| channel | text channel | no | The channel to send logs to. Leave empty to turn logging off. |

**Permissions**
Requires Manage Server. Guild only.

**Behavior**
The command defers its response.
If a channel is given, it is saved as the guild's log channel and the command replies confirming the new channel.
If no channel is given, the guild's logging settings are deleted and the command replies confirming the reset. Nothing is logged until a channel is set again.

**Example**
Input: `/audit channel channel: #mod-logs`
Output: `**Logging**`, subtitle: `Logging channel set to #mod-logs.`

**Error handling**
If the command user lacks Manage Server, or the command is used outside a guild, the command replies with an error message.
If saving or resetting the channel fails, the command replies with a generic error message and the details are written to the bot's log.

## Logged events
Every log message includes a timestamp and an accent color. Green is used for things being created or joining, red for things being deleted or leaving, and orange for changes.

**Members**
Joins and leaves are logged with the member's name, avatar, and the guild's member count.
Member updates are logged when a member's nickname changes, roles are added or removed, or a timeout is applied or removed. Other member changes are ignored.
Profile updates are logged when a user changes their username, display name, or avatar. This is posted in every guild that shares the user and has logging enabled.
Bans and unbans are also logged.

**Messages**
Edited messages are logged with the author, the channel, a "Jump to Message" button, any attachments, and the content before and after the edit. Edits that don't change the text are ignored.
Deleted messages are logged with the author, the channel, any attachments, and the deleted content.
Messages from bots and apps are ignored. Message content is cut to 500 characters, and any markdown in it is escaped. If a message has no text, for example when it only contains an embed, a placeholder is shown instead.

**Voice**
Joining a voice channel, leaving one, and moving between voice channels are logged.

**Channels and roles**
Channels being created or deleted are logged, along with name and topic changes.
Roles being created or deleted are logged, along with name, color, and permission changes. Color changes also state the role's style, which is either Solid, Gradient, or Holographic.

**Notes**
Log messages never ping anyone.
The log channel must be a text channel the bot can send messages in. If the bot can't post there, the event is skipped silently.
