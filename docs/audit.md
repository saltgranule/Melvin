# Audit Cog Documentation
Guild audit logging. Once an audit channel is set, the bot posts a log message there whenever something notable happens in the guild. Events can also be sent to their own channels, see Log channels below.
Command group name: `audit`

## Storage
Settings are stored with the rest of Melvin's module settings, in `data/modules.db`. See the modules documentation for details.

Each log category posts through its own webhook, which Melvin creates automatically. Webhook details are kept in `data/logging.db`.

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
| Audit channel | Used for any event without its own channel. Nothing is logged until one is set. |
| Message channel | Message edits and deletes. Uses the audit channel if not set. |
| Member channel | Joins, leaves, and member or profile changes. Uses the audit channel if not set. |
| Moderation channel | Bans, kicks, unbans, and timeouts. Uses the audit channel if not set. |
| Server channel | Server, channel, and role changes. Uses the audit channel if not set. |
| Voice channel | Voice channel activity. Uses the audit channel if not set. |

**Example**
Input: `/audit config`, then pick `#mod-logs` as the message channel.
Output: The card updates to show `Set to #mod-logs`.

## Log channels
Each event belongs to one of five categories: message, member, moderation, server, or voice. If the category has its own channel, the event is posted there. If not, it's posted to the audit channel. If neither is set, the event isn't logged.

For example, with only the audit channel set, everything goes there. Setting a message channel moves message edits and deletes to it, and everything else stays in the audit channel.

The "Other channel" setting has been replaced by the Voice channel. If it was set, its value is moved to the Voice channel automatically when the bot starts.

## Logged events
Every log message includes a timestamp and an accent color. Green is used for things being created or joining, red for things being deleted or leaving, and orange for changes.

**Members** (member channel)
Joins and leaves are logged with the member's name, avatar, and the guild's member count. Kicks are logged under Moderation instead.
Member updates are logged when a member's nickname changes or roles are added or removed. Role changes made with `/mod` are logged under Moderation instead. Other member changes are ignored.
Profile updates are logged when a user changes their username, display name, or avatar. This is posted in every guild that shares the user and has logging enabled.

**Moderation** (moderation channel)
Actions taken with Melvin's `/mod` commands are logged here: warnings, kicks, bans, unbans, mutes, unmutes, role additions and removals, channel locks and unlocks, and case removals. Each entry shows the target, the moderator, the case number where there is one, and the reason.
Kicks, bans, unbans, and timeouts done outside `/mod`, such as from Discord's own menus, are logged here too, with the moderator and reason when available.
Timeouts are logged when one is applied, including when it ends, and when one is removed by a moderator.

**Messages** (message channel)
Edited messages are logged with the author, the channel, a "Jump to Message" button, any attachments, and the content before and after the edit. Edits that don't change the text are ignored.
Deleted messages are logged with the author, the channel, any attachments, and the deleted content.
Messages from bots and apps are ignored. Message content is cut to 500 characters, and any markdown in it is escaped. If a message has no text, for example when it only contains an embed, a placeholder is shown instead.

**Voice** (voice channel)
Joining a voice channel, leaving one, and moving between voice channels are logged.

**Channels, roles, and server** (server channel)
Channels being created or deleted are logged, along with name and topic changes.
Roles being created or deleted are logged, along with name, color, and permission changes. Color changes also state the role's style, which is either Solid, Gradient, or Holographic.
Server updates are logged when the server's name or icon changes, or when ownership is transferred.

## Webhooks
Each of the five categories has its own webhook, named Message Logs, Member Logs, Moderation Logs, Server Logs, or Voice Logs. Melvin creates it the first time an event is logged, in that category's channel. If the category's channel is changed, the old webhook is deleted and a new one is created in the new channel on the next event. If someone deletes a webhook manually, Melvin creates a new one the next time it's needed.

Melvin needs the Manage Webhooks permission in each log channel. Melvin also needs View Audit Log. It's used to tell kicks apart from leaves, to show moderators and reasons for kicks, bans, and timeouts, and to avoid logging `/mod` actions twice. Without it, kicks show up as leaves, reasons and moderators are left out, and `/mod` actions may be logged twice. It doesn't need to be able to send messages there. If it can't create a webhook, the event is skipped and a warning is written to the bot's logs.

## Notes
Each log channel must be a text channel. Events are skipped silently if the channel is missing or the webhook can't be created.