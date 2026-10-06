# Style Cog Documentation
Change how the bot's display name looks in a guild, using Discord's display name styles.
Command group name: `style`

## set command
Path: `/style set`
Set the bot's name style for the guild. Running it with no options resets the style.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| font | choice | no | The display name's font. Leave empty to keep the current font. |
| effect | choice | no | The display name's effect. Leave empty to keep the current effect. |
| colors | string | no | The display name's color, or two colors for a gradient, as hex codes without the `#`. Leave empty to keep the current colors. |

The available fonts are Sakura, Jellybean, Modern, Medieval, 8Bit, Vampyre, GG Sans (Default), and Tempo.
The available effects are Solid, Gradient, Neon, Toon, and Pop.

**Permissions**
Requires Manage Server. Guild only, and only available when the bot is added to a guild, not as a user app.

**Behavior**
The command reads the bot's current style for the guild, then applies any options that were given. Options that are left empty keep their current value.
For the Gradient effect, colors must be two hex codes joined by a dash, for example `F4A261-FFFFFF`. For every other effect, colors must be a single hex code, for example `F4A261`.
If all three options are left empty, the style is reset to the default font, a solid effect, and white.

**Example**
Input: `/style set font: Sakura effect: Gradient colors: F4A261-FFFFFF`
Output: `**Style Set**`, subtitle: `Melvin's display name style has been set for this server.`

**Error handling**
If the colors don't match the effect, the command replies with an error message showing the expected format, `ABCDEF-123456` for gradients and `ABCDEF` otherwise.
If the command user lacks Manage Server, the command replies with an error message.

## Default style
When the bot joins a new guild, it sets its own style there, using the Sakura font with a gradient effect.
