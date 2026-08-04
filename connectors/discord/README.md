# Character Relay Discord Connector

This worker connects one official Discord Bot account to Character Relay deployments.

## Current capabilities

- Discord Gateway connection through `discord.js`.
- Active deployment routing by Discord Server, Channel, and optional Thread.
- Multiple Character Cards can share one Channel or Thread.
- Explicit character selection through `@CharacterRelayBot CharacterName message`.
- Replies to character-authored messages return to the same Character Deployment.
- Persistent `Discord message_id -> deployment_id` routing survives Connector restarts.
- Mention-only, reply-only, mention-plus-reply, and opt-in Smart Participation modes.
- Small in-memory per-destination context buffer.
- Per-destination serial processing to prevent overlapping character replies.
- Duplicate-message protection.
- Character Relay heartbeat and deployment refresh.
- Railway-compatible health endpoint and container.
- Character-specific webhook names and avatars, with shared Bot fallback.
- Responses use the deployed Character Card's Compiled Character Prompt without per-message OOC evaluation.

## Discord application setup

Create a Discord Application and Bot in the Discord Developer Portal. Invite it to the target Server with these minimum permissions:

```text
View Channels
Send Messages
Send Messages in Threads
Read Message History
Manage Webhooks
```

Use the `bot` OAuth scope. Add `applications.commands` when Slash Commands are introduced. Administrator permission is not required.

Enable the privileged Message Content Intent in the Developer Portal and set:

```text
DISCORD_MESSAGE_CONTENT_INTENT=true
```

This is required for reliable reply routing and ordinary message text. Smart Participation also requires it.

## Character Relay setup

1. Add a Discord connection in the Character Relay Deployment Center.
2. Copy the resulting Connection ID.
3. Create one or more Active deployments using that connection.
4. Configure the same shared connector secret in the API and worker:

```text
Character Relay API
ECHO_MASQUE_CONNECTOR_SHARED_SECRET=<long random secret>

Discord Connector
CHARACTER_RELAY_CONNECTOR_TOKEN=<same secret>
```

Each deployment uses the Discord parent Channel ID. For a Thread deployment, also set the exact Thread ID. Multiple characters may use the same Channel or Thread because each Character Deployment remains independent.

## Addressing characters

When one character is deployed to a destination, the normal forms continue to work:

```text
@CharacterRelayBot hello
Reply to the character's message
```

When multiple characters share the destination, select one by its Character Card or Discord identity display name:

```text
@CharacterRelayBot Ann what do you think?
@CharacterRelayBot 宁：你同意吗？
```

After a character replies, users may reply directly to that message. Character Relay persists the outgoing Discord message ID and resolves the reply back to the original Character Deployment, even when multiple characters share the same webhook.

If a user mentions the Bot without selecting a character in a multi-character destination, the Connector returns a short disambiguation prompt instead of guessing.

## Local development

Requires Node.js 24.17 or newer.

```bash
cd connectors/discord
npm install
cp .env.example .env
npm run dev
```

Required variables:

```text
DISCORD_BOT_TOKEN
CHARACTER_RELAY_API_URL
CHARACTER_RELAY_CONNECTOR_TOKEN
CHARACTER_RELAY_CONNECTION_ID
```

## Railway deployment

Create another Service in the same Railway Project and set its Root Directory to:

```text
/connectors/discord
```

Railway uses the local `Dockerfile` and `railway.toml`. Keep one replica because one Bot token should have one active Gateway consumer.

Set:

```text
DISCORD_BOT_TOKEN=<Discord Bot token>
CHARACTER_RELAY_API_URL=https://<Character Relay service domain>
CHARACTER_RELAY_CONNECTOR_TOKEN=<shared secret>
CHARACTER_RELAY_CONNECTION_ID=<Connection ID from Deployment Center>
DISCORD_MESSAGE_CONTENT_INTENT=true
DISCORD_SMART_PARTICIPATION_ENABLED=false
```

The worker exposes `/health` and reports active deployments, destinations, multi-character destinations, cached reply routes, webhook readiness, the last deployment refresh, and the last Connector error.

## Trigger behavior

```text
mention_only
  Reply only when the Bot is mentioned.

reply_only
  Reply only when a member replies to a routed character message.

mention_and_reply
  Accept either explicit trigger.

smart
  Behaves like mention_and_reply by default.
  Full-channel submission requires DISCORD_SMART_PARTICIPATION_ENABLED=true.
```

For multiple characters in one destination, unaddressed Smart Participation remains silent until a later Social Participation Engine can choose a character intentionally.
