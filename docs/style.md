# Style Cog Documentation
Change how the bot's display name looks in a guild, using Discord's display name styles.
Command group name: `style`

## /style config
Change Melvin's name style for this server.

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
| Font | Sakura, Jellybean, Modern, Medieval, 8Bit, Vampyre, GG Sans, or Tempo. Defaults to Sakura. |
| Effect | Solid, Gradient, Neon, Toon, or Pop. Defaults to Gradient. |
| Colors | One hex color like `F4A261`, or two joined by a dash like `F4A261-FFFFFF`. Defaults to white. With the Gradient effect, a single color is used for both ends. With any other effect, only the first color is used. |

Changes made in Discord apply straight away. Changes made on the dashboard apply within about 15 seconds. If Discord doesn't accept a change, it's retried automatically.

**Example**
Input: `/style config`, then pick 8Bit as the font.
Output: Melvin's name switches to the 8Bit font, and the card shows `Set to 8Bit`.

## Default style
When the bot joins a guild, it applies the guild's saved style, or the defaults above if there isn't one.
