# User guide

Use this section to connect Discord, deploy a Character, and diagnose a conversation without needing to understand the repository architecture.

## First successful Discord reply

1. [Prepare the Discord application and Bot](discord-setup.md#1-prepare-discord).
2. Add the Discord Connection and Server Profile in Deployment Center, then copy the internal Connection UUID from Connection details.
3. Create a paused Character Deployment for that Server and activate it after checking the destination.
4. Start the Discord Connector with that internal Connection UUID and the shared secret.
5. Mention the Bot in an allowed Channel and confirm the Character replies.

## Common tasks

- [Discord setup](discord-setup.md) — permissions, Message Content Intent, Character Relay setup, worker settings, and first verification.
- [Discord debugging](discord-debugging.md) — start with structured events, then use the temporary raw capture only when needed.
- [Server workspace behavior](../discord-server-workspace.md) — Server Profiles, deployments, exclusions, Sessions, and Stickers.
- [Manual validation](../manual-validation.md) — checks that require a real Discord Server, provider, or deployment.

Character Relay currently creates new connections and deployments for Discord only. Historical WhatsApp or Telegram records can still be viewed or deleted, but those platforms do not have a supported production runtime here.
