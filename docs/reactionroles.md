# Reaction Roles Documentation

The `reactionroles` cog lets moderators build panels of buttons and dropdowns. Members click them to get or remove roles. Panels keep working after Melvin restarts.

## Making a panel

Run `/reactionroles new` to start a draft and open the editor. The title is optional, and you can change everything else in the editor.

The editor has two parts:

* **The preview** at the top shows the panel as members will see it. Clicking a button in the preview, or picking an option from a dropdown in the preview, opens a form for that option.
* **The controls** below change the panel:
  * **Edit text** sets the title, body, footer, color, and image. The title and body share one block of text, and the footer is plain text, so you control its formatting, including small text with `-#`.
  * **Add row** creates a row. Pick buttons, a multi-select dropdown, or a single-select dropdown. The placeholder and pick limits only apply to dropdowns, and are ignored for button rows. A panel has up to 4 rows. A button row holds up to 5 buttons, and a dropdown holds up to 25 options. A panel can have up to 20 buttons.
  * **Edit a row** opens that row in its own message. From there you can add a role, remove a role, set a role's group or required role, change a dropdown's placeholder and pick limits, or remove the row. A row's type is set when it's created.
  * **Apply** saves your changes to the panel, and updates the live message if it's posted. **Discard** throws away changes since your last apply.
  * **Publish** appears once there are no unapplied changes on a draft. It asks for a channel and posts the panel there.
  * **Close** ends the editor. Unapplied changes are discarded.

Nothing changes until you press **Apply**. Applying keeps the editor open, so you can publish straight after. Closing the editor also closes any row editors you have open. Run `/reactionroles edit` to open the editor again.

## Editing a live panel

Right-click (or long-press on mobile) a panel message and choose **Edit reaction panel**. You can also run `/reactionroles edit`, giving either the panel ID from `/reactionroles list` or the message link.

Applying changes updates the live message. Only the person who opened the editor can use it, and they need Manage Roles.

If the editor sits untouched for 15 minutes, its buttons stop responding. Open it again to continue.

## Options

**Mode** decides what a click does:

* **Toggle** adds the role if the member lacks it, and removes it if they have it.
* **Add only** gives the role and never removes it.
* **Remove only** removes the role and never adds it.

**Group** makes options in the same group exclusive. Getting one removes any others from that group the member holds. Use this for "pick one region" or "pick one colour".

**Required role** means a member must already have another role before they can pick this one.

Button options have a color, and dropdown options have a description. Each form only shows the field that applies to its row.

In a dropdown, picking several options at once adds them all, and deselecting one removes it. An empty selection clears every toggle option in that dropdown. A single-select keeps one choice at a time.

## Discord's limits

Discord caps a message at 40 components, and each button, dropdown, and text block counts. A full panel of 4 rows with 5 buttons each is 31 components, and the editor's controls take 12 more, so the largest panels don't fit in full. For those, the editor's preview switches to one dropdown per row. Panels with fewer components keep their buttons in the preview. The panel itself always posts with buttons.

## Commands

| Command | What it does |
|---|---|
| `/reactionroles new` | Start a draft and open the editor |
| `/reactionroles edit` | Open the editor for a panel ID or a message |
| `/reactionroles publish` | Post a draft in a channel without opening the editor |
| `/reactionroles list` | List the server's panels and whether they're live |
| `/reactionroles delete` | Delete a panel and its message |

Commands that take a panel suggest matching panels as you type, so you don't need to remember the ID.

## Limits and checks

* A server can have 20 panels.
* Melvin can only give roles below its own top role. It can't give `@everyone`, booster, or integration roles.
* Whoever adds an option must have a higher role than the one they add. The server owner is exempt.
* If a role is deleted, its options are removed from every panel. If a required role is deleted, the requirement is dropped.
* If a live panel's message is deleted, the panel is deleted too.

## Audit logs

Role changes made by a panel are logged by the audit cog as role changes, with the panel named as the reason. They don't create moderation cases.

## When the module is off

Clicks on a panel reply with an ephemeral message saying reaction roles are turned off, and no roles change. The commands are blocked the same way as other modules.
