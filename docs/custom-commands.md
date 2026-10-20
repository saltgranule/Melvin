# Custom Commands
Saved messages your server posts with `/command run`, or with the chat prefix and a name, like `?rules`. They can hold text, embeds, or containers, take arguments, make decisions, and give or take roles. A server can have up to 250.

## Managing commands
Creating, editing, renaming, copying, and deleting need Manage Messages. The dashboard (**Modules**, then **Custom Commands**) needs Manage Server, and has a live preview and a searchable reference.

**/command create**
Saves a new command. `name` and `content` are required. The other options are described below.

**/command edit**
Changes `content`, `args`, `permission`, or `new_name`. Leave out what stays. An empty `args` removes them. With no options, a box opens with the text. Tick **Delete this command** there to remove it.

**/command view**
Shows a command's setup and a preview. Give it values to preview with, or leave them out to see sample values. Roles aren't changed. Restricted commands can only be viewed by people who can use them, or who have Manage Messages.

**/command run**
Posts a command.

**/command list**
Lists the server's commands, only for you to see. Give it some text to search names.

**/command copy**, **/command delete**
Make a copy of a command under a new name, or delete one.

**/command config**
Opens the settings for the module on the dashboard.

Names use letters, numbers, hyphens, and underscores, up to 32 characters.

## Errors
Problems name the line, like `Line 4: Colors must be a hex code like #F4A261.`, and the command isn't saved.

## Brackets and braces
Special parts use curly braces `{}`. Old `[embed]` and `$rand[1-6]` style commands are converted when Melvin starts.

## Plain text, embeds, and containers
A command is plain text unless its first line is `{embed}` or `{container}`.

**Embed**
Start with `{embed}`, then one key per line:
- `title:` up to 256 characters
- `description:` up to 4096 characters, can run on several lines
- `url:` a link for the title
- `color:` a hex code, like `#F4A261`
- `image:` a large image link
- `thumbnail:` a small image link
- `footer:` up to 2048 characters
- `field: name | value` up to 25 fields, names up to 256 characters and values up to 1024

An embed needs a title, a description, or a field.

**Container (Components V2)**
Start with `{container}`. Lines are text unless they're a key below. Text can be up to 4000 characters in total.
- `color:` a hex code for the accent bar
- `button: label | link` up to 5 link buttons, added under the text
- `{separator}` a small divider
- `{separator:small}` the same, written out
- `{separator:large}` a large divider

**Writing a key as plain text**
To keep a line like `Color: red` as text, put a backslash in front: `\Color: red`. It doesn't show.

**Example**
```
{container}
## Welcome to the server
Read the rules first.
{separator}
Questions? Ask in the help channel.
button: Rules | https://example.com/rules
```

## Arguments
`/command create` and `/command edit` take an `args` list of `name:type`, separated by spaces. In the command, use them as `$1`, `$2`, and so on, in the order given.

| Type | Takes |
|------|-------|
| `word` | One word. |
| `number` | A whole number. Add a range like `amount:number:1-100`. |
| `member` | A member, as a mention or ID. |
| `role` | A role, as a mention or ID. |
| `channel` | A channel, as a mention or ID. |
| `text` | The rest of the message. Must be the last argument. |

Add `?` after the name to make one optional, like `reason?:text`. Required ones come first. Quote a value to keep spaces. A bad value stops the command and says why.

Commands without an argument list take whatever follows the name, so `$1` still works without one.

## Variables
| Variable | Result |
|----------|--------|
| `$1`, `$2`, ... | The argument in that position. Empty if there isn't one. |
| `$2+` | That argument and every argument after it. |
| `$*` | Every argument. |
| `$$` | A literal `$`. |
| `$user` | A mention of the person who used the command. |
| `$username` | The person's display name, without a mention. |
| `$userid` | The person's ID. |
| `$server` | The name of this server. |
| `$serverid` | The ID of this server. |
| `$members` | How many members the server has. |

## Stored values
`$name = value` saves a value for this run. It can use any variable or function, and the line isn't posted.

```
$userscore = $roll{2d6}
$opponentscore = $roll{2d6}
$user rolled a $userscore and $1 rolled a $opponentscore
```

Names use lowercase letters, numbers, and underscores, starting with a letter. Built-in and function names are taken. An unset value shows as its name, like `$score`.

## Conditions
Use `{if}`, `{elif}`, `{else}`, and `{endif}` to choose what the command posts.

```
{if $userscore > $opponentscore}$user wins!{elif $userscore < $opponentscore}$1 wins!{else}It's a tie!{endif}
```

- Comparisons are `==`, `!=`, `<`, `>`, `<=`, and `>=`.
- If both sides are whole numbers, they're compared as numbers. Otherwise they're compared as text.
- Put text with spaces in quotes, like `$1 == "two words"`.
- A single `=` is an error. Use `==` to compare.
- A condition on its own is true unless it's empty or `0`.
- A variable that was never set counts as empty.
- Blocks can be nested, and can go in plain text, embeds, and containers.
- A condition can use functions, like `{if $rand{1-6} > 3}`.

## Functions
Functions go in braces after a `$` name. Separate several values with `|`. Functions can be nested, like `$title{$lower{HELLO}}`.

**Text**
| Function | Result |
|----------|--------|
| `$upper{text}` | In capitals. |
| `$lower{text}` | In lower case. |
| `$title{text}` | Each word capitalised. |
| `$trim{text}` | Without spaces at the ends. |
| `$reverse{text}` | Backwards. |
| `$len{text}` | How many characters. |
| `$count{a,b,c}` | How many items are in a comma list. |
| `$index{a,b,c\|n}` | Item number `n` in a comma list, counting from 1. Negative numbers count from the end. Empty if there isn't one. |
| `$replace{text\|find\|new}` | Every `find` swapped for `new`. |
| `$repeat{text\|3}` | The text, three times. Up to 20. |
| `$contains{text\|part}` | `1` if the text has the part, otherwise `0`. Not case sensitive. |
| `$default{value\|fallback}` | The value, or the fallback if the value is empty. Good for optional arguments. |

**Numbers**
| Function | Result |
|----------|--------|
| `$math{expression}` | Arithmetic with `+ - * / // % **` and brackets, like `$math{($1 + 2) * 3}`. Shows `error` if it can't work it out. |
| `$min{a\|b\|...}` | The smallest number. |
| `$max{a\|b\|...}` | The largest number. |
| `$abs{number}` | The number without its sign. |
| `$sum{a\|b\|...}` | All the numbers added together. |
| `$round{number\|places}` | Rounded to a whole number, or to that many decimal places. Halves round up, so `2.5` becomes `3`. |

**Random**
| Function | Result |
|----------|--------|
| `$rand{1-6}` | A random whole number from 1 to 6, inclusive. Each use picks again. |
| `$pick{red\|green\|blue}` | One option, picked at random. |
| `$shuffle{a\|b\|c}` | The options in a random order, joined with commas. |
| `$roll{2d6}` | The total of rolling 2 six-sided dice. Up to 20 dice, with up to 1000 sides. |
| `$chance{30}` | `1` 30% of the time, otherwise `0`. Use it in a condition. |

**Time**
| Function | Result |
|----------|--------|
| `$time` | Date and time, like "January 6, 2025 2:00 PM". |
| `$time:R` | Relative time, like "in 2 hours". |
| `$time:t` | Short time, like "14:00". |
| `$time:T` | Long time, like "14:00:00". |
| `$time:d` | Short date. |
| `$time:D` | Long date. |
| `$time:f` | Long date and short time (same as `$time`). |
| `$time:F` | Like `$time`, with the day of the week added. |
| `$until{3600}` | Relative time from now, in seconds. Like "in an hour". |

Times are shown in each reader's own timezone.

**Mentions**
| Function | Result |
|----------|--------|
| `$member{id}` | A mention of a member. |
| `$role{id}` | A mention of a role. |
| `$channel{id}` | A link to a channel. |

**Roles**
| Function | Result |
|----------|--------|
| `$addrole{member\|role}` | Gives the role to the member after the command posts. |
| `$removerole{member\|role}` | Takes the role from the member after the command posts. |

A command can change at most 10 roles. Put a role change on its own line to keep it out of the text. Members are found with `$user`, `$1`, a mention, or an ID, and roles with a mention, an ID, or an argument.

```
Welcome, $user!
$addrole{$user|<@&123456789012345678>}
```

Anyone using a command that changes roles needs Manage Roles, and Melvin skips roles at or above its own top role or the user's top role, and roles that are managed or @everyone.

## Permissions
`permission` decides who can use the command.
- `none`: everyone.
- A permission like `manage_messages`. Administrators can always use it.
- A role, as a mention or ID. Only members with that role can use it.

## Using commands
- `/command run name:... args:...` posts a command.
- In chat, type the prefix and the name, like `?rules`. The prefix is set in the module's settings and is `?` by default. The command replies to your message.
- The **Chat posts** setting turns the chat prefix off for the server. Slash commands keep working.

## Previews
`/command view` and the dashboard both show a preview. The dashboard preview also shows which roles would change. Previews use sample values for arguments and never post or change roles.
