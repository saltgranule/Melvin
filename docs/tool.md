# Tool Cog Documentation

Utility tools and helper commands.

Command group name: `tool`

## base64 command group

Path: `/tool base64`

### /tool base64 decode

Decode a Base64 encoded string.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| text | string | yes | The Base64 string to decode. |

**Behavior**

The command defers the interaction response, then attempts to decode the given text as Base64.

If the text is not valid Base64, the command replies with an error message showing the decoding error.

If the text decodes successfully but the resulting bytes are not valid UTF-8 text, the command replies with an error message stating that the result is not valid text.

If decoding succeeds, the command replies with the decoded string.

**Example**

Input: `SGVsbG8=`
Output: `**Hello** was the decoded result.`

### /tool base64 encode

Encode a string as Base64.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| text | string | yes | The string to encode. |

**Behavior**

The command defers the interaction response, then encodes the given text as UTF-8 bytes and converts those bytes to Base64.

If encoding fails for any reason, the command replies with an error message showing the exception.

If encoding succeeds, the command replies with the encoded string.

**Example**

Input: `Hello`
Output: `**SGVsbG8=** was the encoded result.`

## binary command group

Path: `/tool binary`

### /tool binary decode

Decode a binary string to text.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| text | string | yes | The binary string to decode, space separated bytes. |

**Behavior**

The command defers the interaction response, then splits the input text on whitespace into chunks.

Each chunk must contain only the characters 0 and 1, and must be exactly 8 characters long. If any chunk fails this check, the command replies with an error message stating that the string is not a valid binary string.

If all chunks are valid, each chunk is converted to a byte, and the resulting bytes are decoded as UTF-8 text.

If the bytes are not valid UTF-8 text, the command replies with an error message stating that the result is not valid text.

If decoding succeeds, the command replies with the decoded string.

**Example**

Input: `01001000 01101001`
Output: `**Hi** was the decoded result.`

### /tool binary encode

Encode a string as binary.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| text | string | yes | The string to encode. |

**Behavior**

The command defers the interaction response, then encodes the given text as UTF-8 bytes and converts each byte to an 8 bit binary string, joined by spaces.

If encoding fails for any reason, the command replies with an error message showing the exception.

If encoding succeeds, the command replies with the encoded string.

**Example**

Input: `Hi`
Output: `**01001000 01101001** was the encoded result.`

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

The command defers the interaction response.

If an attachment is provided, it is converted to a file and included in the response, with the attachment shown in a gallery item linked to the file.

If no attachment is provided, the command sends just the text.

In both cases, mentions in the text are suppressed, so the message will not ping users, roles, or everyone.

**Error handling**

If the command is run by a user without the Manage Messages permission, a gated response is shown instead. This response is ephemeral, meaning only the user who ran the command can see it.
