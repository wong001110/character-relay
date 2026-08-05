# Discord Server Workspace

Deployment Center uses one selected Discord Server Profile as the boundary for Discord runtime configuration.

## Workspace selection

The selected Server Profile is stored in the `server_profile` URL query parameter. Deployment lists, deployment counts, Interaction Templates, applied Sessions, synchronized Channels, and Sticker Dictionary entries are filtered to that Server.

Character Cards remain global assets. A Character Deployment binds a Character Card to the selected Server Profile.

## Server management

Creating and editing a Server Profile uses a right-side Drawer.

- Create Server selects a Discord Connector and a Server already synchronized by that Connector.
- Server ID and Server name come from the Connector catalog and are not typed manually.
- Edit Server changes the workspace label and global Channel/category exclusions.
- Sticker Dictionary appears only while editing an existing Server.
- Existing Server settings remain editable if the Connector catalog is temporarily unavailable; stored exclusions are preserved.

Deleting a Server Profile requires deleting its Character Deployments first. After deletion, its Interaction Templates, applied Sessions, and Interaction Runs are removed. Sticker metadata remains tied to the Discord Connection and Guild catalog unless the Connection itself is deleted.

## Deployments

New Deployments automatically use the selected Server's Discord Connection and Server Profile. The user selects the Character and character-specific exclusions; Server identity is read-only in the form.

The Deployment list and summary counts show only the selected Server. The platform filter is omitted because a Discord Server Workspace contains only Discord Deployments.

Direct entry from a Character Card preserves the open Deployment form while the initial Server selection is restored. Later user-initiated Server switches close stale Deployment forms and reset pagination.

## Interaction Templates

Interaction Templates are reusable rules scoped to one Server Profile. The initial Template type is `roast` and stores:

- two Character Cards in fixed speaking order;
- rounds per trigger;
- maximum triggers;
- cooldown;
- Session duration;
- light, playful, or sharp intensity.

Both Characters must have Active Deployments in the selected Server. Applying a Template resolves their current Deployment IDs and asks only for a Channel, target Discord user, optional display name, and initial Session status.

Applied Sessions keep their own trigger counts, cooldown state, status, target user, and Channel. Editing a Template does not rewrite existing Sessions.

## Guild Sticker synchronization

The Discord Connector requests `GatewayIntentBits.GuildExpressions` and fetches each visible Guild's custom Stickers during Server catalog synchronization. Sticker ID, name, description, tags, format, and asset URL are upserted into the Server's Sticker Dictionary before the Sticker is used in conversation.

Manual intent, emotion, and semantic descriptions remain authoritative and are not overwritten by later Discord metadata refreshes. Standard Discord Stickers that are not Guild assets are still learned when they appear in an incoming message.
