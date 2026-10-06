# Tool Cog Documentation
Utility tools and helper commands.
Command group name: `tool`

## Formats
The encode and decode commands share the same list of formats.

| Format | Encoded looks like | Notes |
|------|------|------|
| Base64 | `SGk=` | Decoding requires valid Base64, including padding. |
| Binary | `01001000 01101001` | One 8 bit group per byte, separated by spaces. |
| Hex | `48 69` | One pair of hex digits per byte. Decoding accepts the pairs with or without spaces. |
| URL | `Hi%20there` | Percent encoding, as used in links. Every character that isn't a letter, digit, or one of `_.-~` is encoded. |
| Base32 | `JBUQ====` | Decoding ignores case and spaces, and adds missing padding. |
| Morse | `.... ..` | Letters are separated by spaces and words by ` / `. Supports letters, digits, and common punctuation. Decoded text is uppercase. |
| Unicode | `U+0048 U+0069` | One code point per character. Decoding also accepts plain hex like `48 69`, separated by spaces or commas. |

Text is converted to and from UTF-8 for every format except Morse and Unicode, which work on characters directly.

## encode command
Path: `/tool encode`
Encode text into another format.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| format | choice | yes | The format to encode into. |
| text | string | yes | The text to encode. |

**Behavior**
The command defers its response, then encodes the text into the chosen format.
For Morse, the command replies with an error message listing any characters that have no Morse code, for example accented letters or emoji.
If encoding passes, the command replies with the encoded text.

**Example**
Input: `/tool encode format: Hex text: Hi`
Output: `**48 69** was the Hex encoded result.`

## decode command
Path: `/tool decode`
Decode text from another format.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| format | choice | yes | The format to decode from. |
| text | string | yes | The text to decode. |

**Behavior**
The command defers its response, then decodes the text from the chosen format.
If the text isn't valid for that format, the command replies with an error message. For Binary, Morse, and Unicode, the message says what was wrong, such as which Morse codes weren't recognized.
If the text decodes but the result isn't valid UTF-8 text, the command replies with an error message stating that the result is not valid text.
If decoding passes, the command replies with the decoded text.

**Example**
Input: `/tool decode format: Morse text: .... ..`
Output: `**HI** was the Morse decoded result.`

**Error handling**
If the result is longer than 3900 characters, the command replies with an error message instead, since the result wouldn't fit in a Discord message. Encoding can make text several times longer, especially Binary and Unicode.
If the result is empty, for example when decoding only spaces, the command replies with an error message.
Mentions in the result are suppressed, so decoded text will not ping users, roles, or everyone.

## speak command
Path: `/tool speak`
Speak through Melvin. Sends a message as the bot, with an optional attachment.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| text | string | yes | The message text to send. |
| attachment | attachment | no | Optional attachment to include with the message. |

**Permissions**
Requires the Manage Messages permission. If the user does not have this permission, the command shows a gated response instead of running **unless the user is using the speak command in a private message, or group chat.**

**Behavior**

If an attachment is provided, it is converted to a file and included in the response, with the attachment shown in a gallery item linked to the file.
If no attachment is provided, the command sends just the text.
In both cases, mentions in the text are suppressed, so the message will not ping users, roles, or everyone.

**Error handling**
If the command is run by a user without the Manage Messages permission **inside a server**, a gated response is shown instead. This response is ephemeral, meaning only the user who ran the command can see it.
