# Info Cog Documentation
Commands for viewing user information and bot stats.
Command group name: `info`

## latency command
Path: `/info latency`
View the bot's latency.

**Parameters**
None.

**Behavior**
The gathers the bot's latency in ms, rounded to the nearest whole number. The reply shows this value in an info view, with the title "Latency" and a subtitle stating the bot's latency.

**Example**
Input: `/info latency`
Output: `**Latency**`, subtitle: `The bot's latency is **42**ms.`

## avatar command
Path: `/info avatar`
View a user's avatar.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| user | user | no | The user whose avatar you want to view. Defaults to the command user. |

**Behavior**
The command defers its response. If no user is given, the target defaults to whoever ran the command.
The reply title reflects who the avatar belongs to: "My Avatar" if the target is the bot itself, "Your Avatar" if the target is the command user, or "{user}'s Avatar" otherwise.
Below the title, a media gallery shows the target's display avatar.
If the target has a custom avatar set, link buttons are shown for each available format: png, jpg, and webp, plus gif if the avatar is animated. If the target has no custom avatar, a single "Web" link button is shown instead, pointing to their default avatar.
Mentions in the reply are suppressed, so the response will not ping the target.

**Example**
Input: `/info avatar user: @Alex`
Output: A layout showing "Alex's Avatar", the avatar image, and link buttons for each available format.

## banner command
Path: `/info banner`
View a user's profile banner.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| user | user | no | The user whose banner you want to view. Defaults to the command user. |

**Behavior**
The command defers its response. If no user is given, the target defaults to whoever ran the command.
Since banner data is not always present on cached user objects, the command fetches the target user fresh from Discord before checking for a banner.
If the fetched user has no banner, the command replies with an error message stating that they do not have a profile banner. The wording adapts based on the target: "I do not have a profile banner." for the bot, "You do not have a profile banner." for the command user, or "{user} does not have a profile banner." otherwise. This error reply is ephemeral, meaning only the user who ran the command can see it.
If the fetched user does have a banner, the reply title reflects who it belongs to, following the same "My / Your / {user}'s" pattern as the avatar command. Below the title, a media gallery shows the banner image.
Link buttons are shown for each available format: png, jpg, and webp, plus gif if the banner is animated. If somehow no banner URL is available despite the check above, a single disabled "No Banner" button is shown instead.
Mentions in the reply are suppressed, so the response will not ping the target.

**Example**
Input: `/info banner user: @Alex`
Output: A layout showing "Alex's Banner", the banner image, and link buttons for each available format.

**Error handling**
If the target has no profile banner, the command replies with an ephemeral error message instead of a banner view.