# Info Cog Documentation
Commands for viewing user information.
Command group name: `info`

## avatar command
Path: `/info avatar`
View a user's avatar.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| user | user | no | The user whose avatar you want to view. Defaults to the command user. |
| type | choice | no | Global or Server. Defaults to Global. |

**Behavior**
The command defers its response. If no user is given, the target defaults to whoever ran the command.
The reply title reflects who the avatar belongs to: "My Avatar" if the target is the bot itself, "Your Avatar" if the target is the command user, or "{user}'s Avatar" otherwise.
With type Global, a media gallery below the title shows the target's global avatar.
With type Server, the command fetches the target as a member of the current server and shows their server avatar, titled "{user}'s Server Avatar". If they have no server avatar, or are not in the server, the global avatar is shown instead. Using type Server outside a server replies with an ephemeral error.
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
| type | choice | no | Global or Server. Defaults to Global. |

**Behavior**
The command defers its response. If no user is given, the target defaults to whoever ran the command.
Since banner data is not always present on cached user objects, the command fetches the target user fresh from Discord before checking for a banner.
With type Server, the command fetches the target as a member of the current server and shows their server banner, titled "{user}'s Server Banner". If they have no server banner, or are not in the server, the command falls back to the global banner. Using type Server outside a server replies with an ephemeral error.
If the fetched user has no banner, the command replies with an error message stating that they do not have a profile banner. The wording adapts based on the target: "I do not have a profile banner." for the bot, "You do not have a profile banner." for the command user, or "{user} does not have a profile banner." otherwise. This error reply is ephemeral, meaning only the user who ran the command can see it.
If the fetched user does have a banner, the reply title reflects who it belongs to, following the same "My / Your / {user}'s" pattern as the avatar command. Below the title, a media gallery shows the banner image.
Link buttons are shown for each available format: png, jpg, and webp, plus gif if the banner is animated.
Mentions in the reply are suppressed, so the response will not ping the target.

**Example**
Input: `/info banner user: @Alex`
Output: A layout showing "Alex's Banner", the banner image, and link buttons for each available format.

**Error handling**
If the target has no profile banner, the command replies with an ephemeral error message instead of a banner view.
If type Server is used outside a server, the command replies with an ephemeral error message.
## role command
Path: `/info role`
View information about a role.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| role | role | yes | The role you want to view. |

**Permissions**
Only available in servers.

**Behavior**
The command defers its response. The reply title shows the role mention and its ID. The container uses the role's color as its accent, unless the role has no color.
Below the title, the reply lists:
- Appearance: the role color and "Solid". If the server has enhanced role colors and the role uses them, both colors and "Gradient" are shown, or all three colors and "Holographic".
- Hoisted: whether the role is shown separately in the member list.
- Mentionable: whether anyone can mention the role.
- Number of Members: how many members have the role.
- Created at: the full creation date and a relative time.

If the role has an icon, it is shown as a thumbnail next to the details.
If the command user has any role other than @everyone, a line states whether the role is their highest role, above it, or below it.
A Relative Hierarchy code block lists up to three roles above and three below the role, numbered from the top of the role list, with the role marked by `>`.
A View Members button sends an ephemeral, paginated list of the members with the role, ten per page. The button stops responding after five minutes and is disabled.
Mentions in the reply are suppressed.

**Example**
Input: `/info role role: @Moderator`
Output: A layout showing "@Moderator | {id}", the role details, its place in the hierarchy, and a View Members button.
