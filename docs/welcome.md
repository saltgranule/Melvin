# Welcome Cog Documentation
Welcome messages for new members, with optional custom text, an image, and up to two link buttons.
Command group name: `welcome`

All commands require Manage Server and are guild only.

## Storage
Welcome settings are stored in a SQLite database at `data/welcome.db`, in a table called `welcome_channels`. Each row holds a guild id, the welcome channel id, the message text, the image path, and the URL and label for each button. The table is created automatically when the cog loads, if it does not already exist.
Uploaded images are saved in `data/welcome_images`, one per guild, named after the guild id. Uploading a new image replaces the old one.
When the bot is removed from a guild, that guild's welcome settings and image are deleted.

## channel command
Path: `/welcome channel`
Set or reset the channel for member join events.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| channel | text channel | no | The channel to send welcome messages to. Leave empty to reset. |

**Behavior**
The command defers its response.
If a channel is given, it becomes the guild's welcome channel. Changing the channel later keeps the existing text, image, and buttons.
If no channel is given, all of the guild's welcome settings are deleted, including any uploaded image, and welcome messages stop.

**Example**
Input: `/welcome channel channel: #welcome`
Output: `**Welcome Channel Set**`, subtitle: `Welcome channel set to #welcome.`

## config command
Path: `/welcome config`
Preview and customize the welcome message.

**Parameters**
None.

**Behavior**
If no welcome channel is set, the command replies with an error message asking you to set one with `/welcome channel` first.
Otherwise, the command replies with a preview of the welcome message, using the command user as the example member, with a select menu underneath.
The Media option opens a form for uploading an image to show in the welcome message. Leaving the upload empty keeps the current image.
The Text option opens a form for editing the message text. Leaving it empty uses the default text, `Welcome, {member}!`.
The Buttons option opens a form for setting a URL and label for up to two link buttons. Leaving a URL empty removes that button, and labels default to "Link 1" and "Link 2".
After a form is submitted, the preview updates in place. Only members with Manage Server can use the select menu.

**Placeholders**
These are replaced in the message text when it is sent.

| Placeholder | Replaced with |
|------|------|
| `{member}` | A mention of the new member. |
| `{member_count}` | The guild's member count. |

**Error handling**
Button URLs must start with `http://` or `https://`, otherwise the form replies with an error message and nothing is saved.
If an uploaded image can't be saved, the form replies with an error message and the previous image is kept.

## preview command
Path: `/welcome preview`
Preview what the configured welcome notification looks like.

**Parameters**
None.

**Behavior**
The command defers its response.
If no welcome channel is set, the command replies with an error message.
Otherwise, the command replies with the welcome message exactly as a new member would see it, using the command user as the example member, without the select menu.

## Member joins
When a member joins a guild with a welcome channel set, the bot sends the welcome message to that channel. If the bot can't post in the channel, the message is skipped silently.
