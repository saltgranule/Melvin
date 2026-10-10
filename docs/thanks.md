# Thanks Cog Documentation

The `thanks` cog tracks trigger phrases, ie 'thank you', and increments them to users. these stats are global, and reflect how helpful a user has been.

## Trigger Phrases

When a user includes any of these phrases in a message (by replying to someone or tagging them), a thank is credited:

* thanks
* thx
* thank you
* ty
* ta
* cheers
* tysm
* tyvm
* thanks a lot
* thanks so much
* thank you so much
* thanks a ton
* thanks a million
* much appreciated
* appreciate it
* many thanks
* well done
* good job
* great job
* nice job
* kudos
* props

## Negation Phrases

If any of these words immediately come before a trigger phrase (like "no thanks"), the bot skips it and will not count a thank:

* no
* not
* dont
* don't
* never
* no thanks to
* not thanks to
* hardly a
* barely a
* without any
* zero
* 0
* instead of
* far from
* definitely not
* certainly not

## How It Works

1. **Replying to a message:** If you reply directly to a message and include a trigger phrase, the author of that message gets credited.
2. **Tagging a user:** If you mention (@user) someone in a message with a trigger phrase, they get credited.
3. **Checking stats:** Use the slash command `/thanks count` (or `/thanks count [user]`) to see how many times you or another member have been thanked.

## Rate Limits & Guard Clauses

* **Cooldown:** Users can only give 1 thank per cooldown, which is 1 minute unless a server changes it with `/thanks config`.
* **Self-thanking:** You cannot thank yourself.
* **Bots:** You cannot thank bot accounts, and bot messages will not trigger thanks.
* **Modules:** If the Thanks module is turned off with `/modules`, thanks aren't counted in that server and `/thanks count` is unavailable there.

## Potential Failure Points

Here are a few scenarios where the cog might not work as expected or could fail:

"no thanks" cancels a thank, but phrasing like "no, thanks!" might still trigger depending on spacing and punctuation.

Phrases with additional words between the negation and trigger (like "definitely do not give thanks") will not be caught by the negation check.

## /thanks count
Check how many times a user has been thanked.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| user | user | no | The user to check. Defaults to you. |

**Behavior**
The command replies with how many times the user has been thanked, across every server. Users who have never been thanked show 0.

**Example**
Input: `/thanks count user: @Alex`
Output: `**Alex's thanks**`, followed by `Thanked 12 times.`

## /thanks config
Change thanks settings for this server.

**Permissions**
Requires Manage Server. Guild only.

**Behavior**
The command replies with the same settings card as every other module's config command. Each change saves straight away. The same settings can be changed from the dashboard, under Config on the Thanks card.

**Settings**

| Setting | Description |
|------|--------------|
| Thank messages | Whether Melvin posts a message when someone is thanked. Thanks are counted either way. Defaults to On. |
| Cooldown | How long each member waits between giving thanks, 30 seconds, 1 minute, 5 minutes, or 10 minutes. Defaults to 1 minute. |
