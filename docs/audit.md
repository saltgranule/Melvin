# Audit Cog Documentation
Guild audit logging. Once a log channel is set, the bot posts a log message there whenever something notable happens in the guild.
Command group name: `audit`

## Storage
Settings are stored with the rest of Melvin's module settings, in `data/modules.db`. See the modules documentation for details.

## /audit config
Change audit log settings for this server.

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
| Log channel | The channel audit logs are posted in. Nothing is logged until one is set. |

**Example**
Input: `/audit config`, then pick `#mod-logs` as the log channel.
Output: The card updates to show `Set to #mod-logs`.

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
