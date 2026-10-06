# Debug Cog Documentation
Commands for debugging purposes. They send the bot's reply layouts as they are, to check how they render.
Command group name: `debug`

## think command
Path: `/debug think`
Send raw ResponseUI class.

**Parameters**
None.

**Behavior**
The command replies with a ResponseUI containing the "Thinking..." text used while the bot is working on a reply.

## error command
Path: `/debug error`
Send raw ErrorUI class.

**Parameters**
None.

**Behavior**
The command replies with the generic error message used across the bot, which asks the user to report the issue in the support server.
