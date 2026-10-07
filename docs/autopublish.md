# Auto-Publish Cog Documentation
**FYI, thanks to lucibot in the d.py server for showcasing this neat feature!!**
Publishes messages in announcement channels when they're sent, so servers following those channels receive them.
Command group name: `autopublish`

All commands require Manage Server and are guild only.

## How messages are published
When a message is sent in one of the picked channels, Melvin publishes it. These messages are skipped:

| Message | Why |
|------|--------------|
| System messages, like "thread created" or "poll ended" | Discord can't publish them. |
| Messages from bots and webhooks | Skipped unless Bot messages is set to publish them. |
| Messages in channels that weren't picked | Only the picked channels are published. |
| Messages in picked channels that aren't announcement channels | Only announcement channels can be published. |

Melvin needs Manage Messages in each picked channel to publish other people's messages. Without it, messages in that channel aren't published.
Discord allows 10 published messages per channel per hour. Messages past the limit are published once Discord allows it.
When the module is turned off with `/modules` or the dashboard, messages aren't published.

## Storage
Settings are stored with the rest of Melvin's module settings, in `data/modules.db`. Messages aren't stored.
When the bot is removed from a guild, that guild's auto-publish settings are deleted.

## config command
Path: `/autopublish config`
Change which announcement channels are published automatically.

**Parameters**
None.

**Permissions**
Requires Manage Server. Guild only.

**Behavior**
The command replies with a settings card listing each setting, what it does, and its current value. Channels are picked from a select menu, up to 25 of them, and deselecting all of them clears the setting. The menu also lists text channels. Only announcement channels are published, other channels are skipped.
Each change saves straight away and the card updates in place. Only members with Manage Server can use the card, and it stops responding after 5 minutes.
The same settings can be changed from the dashboard on the website, under Config on the module's card, where each channel has a checkbox.

**Settings**

| Setting | Description |
|------|--------------|
| Channels | The announcement channels whose messages are published. Other channels can be picked, but are skipped. None by default, so nothing is published until at least one is picked. |
| Bot messages | Whether messages from bots and webhooks are published too. Skipped by default. |

Output: An updated settings card after each change.
