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

## /tool encode
Encode text into another format.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| format | choice | yes | The format to encode into. |
| text | string | yes | The text to encode. |

**Behavior**
The command defers its response, then encodes the text into the chosen format.
For Morse, if the text has characters with no Morse code, for example accented letters or emoji, the command replies with an error message naming them, such as `É and 😀 can't be written in Morse.`
If encoding passes, the command replies with the encoded text.

**Example**
Input: `/tool encode format: Hex text: Hi`
Output: `**48 69** was the Hex encoded result.`

## /tool decode
Decode text from another format.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| format | choice | yes | The format to decode from. |
| text | string | yes | The text to decode. |

**Behavior**
The command defers its response, then decodes the text from the chosen format.
If the text isn't valid for that format, the command replies with an error message, such as `That doesn't look like Hex.`
If the text decodes but the result isn't valid UTF-8 text, the command replies with `That decodes to something that isn't text.`
If decoding passes, the command replies with the decoded text.

**Example**
Input: `/tool decode format: Morse text: .... ..`
Output: `**HI** was the Morse decoded result.`

**Error handling**
If the result is longer than 3900 characters, the command replies with `That result is too long to send.`, since it wouldn't fit in a Discord message. Encoding can make text several times longer, especially Binary and Unicode.
If the result is empty, for example when decoding only spaces, the command replies with `There's nothing to show.`
Mentions in the result are suppressed, so decoded text will not ping users, roles, or everyone.

## Decode message option
Path: right-click a message, open `Apps`, then choose `Decode`
Decode a message's text from another format, without copying it into a command.

**Parameters**
None. The option uses the text of the message it was opened on.

**Behavior**
If the message has no text, for example when it only contains an image or embed, the bot replies with an error message.
Otherwise, the bot replies with a select menu listing the same formats as the decode command. The format is never guessed, so nothing is decoded until one is picked.
Picking a format replaces the reply with the decoded result, or an error message if the text isn't valid for that format, following the same rules as the decode command. The select menu stays underneath, with the picked format selected, so another format can be tried straight away.
All replies are ephemeral, meaning only the user who opened the option can see them. Mentions in the result are suppressed.
The select menu stops responding after a few minutes. Opening the option on the message again shows a new one.

## /tool speak
Speak through Melvin. Sends a message as the bot, with an optional attachment.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| text | string | yes | The message text to send. |
| attachment | attachment | no | Optional attachment to include with the message. |
| containerized | boolean | no | Send the message in a container. Defaults to true. |

**Permissions**
Requires the Manage Messages permission. If the user does not have this permission, the command shows a gated response instead of running **unless the user is using the speak command in a private message, or group chat.**

**Behavior**

If containerized is true, the text is sent inside a container. If an attachment is provided, it is converted to a file and shown in a gallery item in the container, below the text.
If containerized is false, the text is sent as a plain message with no container. If an attachment is provided, it is included as a regular file attachment.
In both cases, mentions in the text are suppressed, so the message will not ping users, roles, or everyone.

**Error handling**
If the command is run by a user without the Manage Messages permission **inside a server**, a gated response is shown instead. This response is ephemeral, meaning only the user who ran the command can see it.

## /tool urban
Look up a word on Urban Dictionary.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| word | string | yes | The word or phrase to look up. |

**Behavior**
The command defers its response and looks the word up through the Urban Dictionary API.
The reply is a paginated layout with one definition per page, in the order Urban Dictionary returns them, up to ten. The title shows the word, with a link button to its Urban Dictionary page.
Each page shows the definition, the example if there is one, and a footer with the vote counts, the author, the date it was written, and a permalink. Words Urban Dictionary marks as links in the text become links to their own definitions.
Long definitions are cut to 1200 characters and long examples to 600, ending with "...".
The page buttons stop responding after five minutes and are disabled.
Mentions in the reply are suppressed.

**Example**
Input: `/tool urban word: chud`
Output: A layout titled "chud" showing the first definition, with buttons to page through the rest.

**Error handling**
If no definitions are found, the command replies with an ephemeral error message.
If Urban Dictionary cannot be reached or does not respond within ten seconds, the command replies with an ephemeral error message.

## /tool wiki
Look up a Wikipedia article, or get a random one.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| query | string | no | The article to look up. Leave it empty for a random article. |

**Behavior**
While typing the query, Melvin suggests up to 25 matching article titles from Wikipedia. Picking a suggestion is the easiest way to land on the right article, but any text can be sent.
The command defers its response and looks the article up on English Wikipedia. Redirects are followed, so a query like `nyc` shows the article for New York City.
The reply shows the article's title, its short description, the opening summary, and the lead image if it has one. A link button next to the title opens the full article. Summaries longer than 1500 characters are cut, ending with "...".
If the query is left empty, the command shows a random article instead, with an `Another` button underneath that swaps it for a new random article. Anyone who can see the reply can press it. The button stops responding after five minutes and is disabled.
Mentions in the reply are suppressed.

**Example**
Input: `/tool wiki query: Octopus`
Output: A layout titled "Octopus" with its summary, the lead image, and a button to open the article.

**Error handling**
If no article matches the query, the command replies with an ephemeral error message.
If the query matches a disambiguation page, such as `Python`, the command replies with an ephemeral error message asking for something more specific.
If Wikipedia cannot be reached or does not respond within ten seconds, the command replies with an ephemeral error message.

## /tool 8ball
Ask the magic 8ball a question.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| prompt | string | yes | The question for the 8ball. |

**Behavior**
The command replies with the question and one of nine answers, picked at random. `@everyone` and `@here` in the question don't ping anyone.

**Example**
Input: `/tool 8ball prompt: Will it rain tomorrow?`
Output: `**Will it rain tomorrow?**`, followed by an answer like `Without a doubt.`
