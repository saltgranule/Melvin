# AFK Cog Documentation

The `afk` cog lets members leave an away message for one server. The global aspect of this module was stripped, because it'd be too hard to handle / gate in the long run.

## How It Works

1. **Going AFK:** Use `/afk set`, with a reason if you like.
2. **Being mentioned:** When someone mentions an AFK member, Melvin replies with that member's reason and when they went AFK. Nobody is pinged by the reply.
3. **Coming back:** Your next message in that server clears your status, and Melvin replies that you're no longer AFK.

## Limits

* **Cooldown:** Each AFK member is announced at most once every 30 seconds per channel, so a busy conversation doesn't fill up with notices.
* **Several mentions:** One message lists up to 5 AFK members, followed by how many more there are.
* **Bots:** Bot messages don't clear a status or trigger a notice.
* **Leaving:** A member's status is deleted when they leave the server. Everything for a server is deleted when Melvin leaves it.
* **Modules:** If the AFK module is turned off with `/modules`, the `/afk` commands are unavailable in that server and statuses do nothing. They're kept, and start working again when it's turned back on.

## /afk set
Go AFK in this server.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| reason | string | no | What to tell people who mention you, up to 200 characters. |

**Permissions**
Guild only.

**Behavior**
The command saves your status and replies that you're now AFK, with your reason underneath if you gave one. If you're already AFK, your reason and time are replaced.

**Example**
Input: `/afk set reason: Back after lunch`
Output: `@Alex is now AFK`, followed by `Back after lunch` in small bold text.

## /afk clear
Clear a member's AFK status.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|--------------|
| user | member | yes | The member to clear. |

**Permissions**
Requires Moderate Members. Guild only.

**Behavior**
The command removes the member's status and replies that they're no longer AFK. If the member isn't AFK, it replies with an error only you can see.

**Example**
Input: `/afk clear user: @Alex`
Output: `@Alex is no longer AFK`
