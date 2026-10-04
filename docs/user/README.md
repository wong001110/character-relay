# User guide

Use this section to connect Discord, deploy a Character, and diagnose a conversation without needing to understand the repository architecture.

## First successful Discord reply

1. [Prepare the Discord application and Bot](discord-setup.md#1-prepare-discord).
2. Add the Discord Connection and Server Profile in Deployment Center, then copy the internal Connection UUID from Connection details.
3. Create a paused Character Deployment for that Server and activate it after checking the destination.
4. Start the Discord Connector with that internal Connection UUID and the shared secret.
5. Mention the Bot in an allowed Channel and confirm the Character replies.

## Common tasks

### Room Companion

Open Rooms, choose an authorized room and an owned chat profile, then select **Pop out · Room
Companion**. Supported browsers open a small Document Picture-in-Picture window with recent
messages and a quick text reply. Keep the Character Relay tab open and use a separate tab for
Gemini or other work; navigating the parent tab to another website closes PiP. **Open full room**
returns to the current room for attachments, stickers, reactions and management.

If Document PiP is unavailable or opening is denied, the companion stays inside Character Relay;
that fallback does not remain on top of other websites. Viewing the latest messages in either
surface acknowledges the same unread count. Opening or minimizing the companion alone does not.
Pending and uncertain delivery remain visible; an unknown submission can only be checked/retried
explicitly with its original message ID. A draft containing files or a sticker must be sent from
the full room. Dots desktop visibility and control require validation in its actual cloud computer.

### Discord and diagnostics

- [Discord setup](discord-setup.md) — permissions, Message Content Intent, Character Relay setup, worker settings, and first verification.
- [Discord debugging](discord-debugging.md) — start with structured events, then use the temporary raw capture only when needed.
- [Server workspace behavior](../discord-server-workspace.md) — Server Profiles, deployments, exclusions, Sessions, and Stickers.
- [Manual validation](../manual-validation.md) — checks that require a real Discord Server, provider, or deployment.

Character Relay currently creates new connections and deployments for Discord only. Historical WhatsApp or Telegram records can still be viewed or deleted, but those platforms do not have a supported production runtime here.
