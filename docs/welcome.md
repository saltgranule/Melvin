# Welcome Cog Documentation
Welcome messages for new members, with optional custom text, an image, and up to two link buttons.
Command group name: `welcome`

All commands require Manage Server and are guild only.

## Storage
Settings are stored with the rest of Melvin's module settings, in `data/modules.db`. Uploaded images are saved in `data/config_images`, and replacing or removing an image deletes the old file.
When the bot is removed from a guild, that guild's welcome settings and image are deleted.

## /welcome config
Change welcome message settings for this server.

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
| Welcome channel | The channel welcome messages are sent in. Nothing is sent until one is set. |
| Message | The message text. Defaults to `Welcome, {member}!`. |
| Image | Shown under the message. PNG, JPG, GIF, or WebP, up to 8 MB. The form has a checkbox to remove the current image. |
| First and second button labels | The text on each link button. Default to "Link 1" and "Link 2". |
| First and second button links | Where each button goes. Leave empty for no button. Links must start with `http://` or `https://`. |

**Placeholders**
These are replaced in the message text when it is sent.

| Placeholder | Replaced with |
|------|------|
| `{member}` | A mention of the new member. |
| `{member_count}` | The guild's member count. |

## /welcome preview
Preview what the configured welcome notification looks like.

**Parameters**
None.

**Behavior**
The command defers its response.
If no welcome channel is set, the command replies with an error message asking you to set one with `/welcome config`.
Otherwise, the command replies with the welcome message exactly as a new member would see it, using the command user as the example member, without the select menu.

## Member joins
When a member joins a guild with a welcome channel set, the bot sends the welcome message to that channel. If the bot can't post in the channel, the message is skipped silently.
