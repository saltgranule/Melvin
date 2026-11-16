# Boost Cog Documentation
Boost messages for new boosters, with optional custom text, an image, and up to two link buttons. It works the same way as the welcome module, but posts when a member starts boosting instead of when they join.
Command group name: `boost`

All commands require Manage Server and are guild only.

## Storage
Settings are stored with the rest of Melvin's module settings, in `data/modules.db`. Uploaded images are saved in `data/config_images`, and replacing or removing an image deletes the old file.
When the bot is removed from a guild, that guild's boost settings and image are deleted.

## /boost config
Change boost message settings for this server.

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
| Boost channel | The channel boost messages are sent in. Nothing is sent until one is set. |
| Message | The message text. Defaults to `Thanks for boosting, {member}!`. Separate several messages with `$` and one is picked at random for each boost. |
| Image | Shown under the message. PNG, JPG, GIF, or WebP, up to 8 MB. The form has a checkbox to remove the current image. |
| First and second button labels | The text on each link button. Default to "Link 1" and "Link 2". |
| First and second button links | Where each button goes. Leave empty for no button. Links must start with `http://` or `https://`. |

**Placeholders**
These are replaced in the message text when it is sent.

| Placeholder | Replaced with |
|------|------|
| `{member}` | A mention of the booster. Only this placeholder pings them. |
| `{member_no_ping}` | A mention of the booster that doesn't ping them. |
| `{member_name}` | The member's display name. |
| `{member_username}` | The member's username. |
| `{member_created}` | When the member's account was created, as relative time, eg. 3 years ago. |
| `{member_count}` | The guild's member count. |
| `{server_name}` | The guild's name. |
| `{date_t}` | Short time, eg. 11:20. |
| `{date_T}` | Time with seconds, eg. 11:20:30. |
| `{date_d}` | Short date, eg. 01/01/2020. |
| `{date_D}` | Long date, eg. January 1, 2020. |
| `{date_f}` | Date and time, eg. January 1, 2020 at 11:30. |
| `{date_F}` | Full date and time, eg. Wednesday, January 1, 2020 at 11:30. |
| `{date_s}` | Short date and time, eg. 01/01/2020, 11:30. |
| `{date_S}` | Short date and time with seconds, eg. 01/01/2020, 11:30:30. |
| `{date_R}` | Relative time, eg. 5 minutes ago. |

The `{date_...}` placeholders use the time the member started boosting, and are shown in each reader's own timezone. They use [Discord's timestamp styles](https://discord.com/developers/docs/reference#message-formatting-timestamp-styles). Unknown placeholders are left as they are.

## /boost preview
Preview what the configured boost notification looks like.

**Parameters**
None.

**Behavior**
The command defers its response.
If no boost channel is set, the command replies with an error message asking you to set one with `/boost config`.
Otherwise, the command replies with the boost message exactly as it would be posted, using the command user as the example booster, without the select menu.

## New boosts
When a member starts boosting a guild with a boost channel set, the bot sends the boost message to that channel. Discord only reports the first boost from each member, so adding more boosts while already boosting doesn't send another message. If the message contains several parts separated by `$`, one part is picked at random. The member is only pinged if the message uses `{member}`. If the bot can't post in the channel, the message is skipped silently.
