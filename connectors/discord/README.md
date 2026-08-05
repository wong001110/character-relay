# Character Relay Discord Connector

This worker connects one official Discord Bot account to Character Relay deployments.

## Current capabilities

- Discord Gateway connection through `discord.js`.
- Active deployment routing by Discord Server, Channel, and optional Thread.
- Multiple Character Cards can share one Channel or Thread.
- Specific character selection through `@CharacterRelayBot CharacterName message`.
- Multiple named characters can be addressed in one message.
- Explicit group addresses route to every character in the destination.
- Character replies can explicitly Tag other deployed characters and continue a bounded Bot-to-Bot conversation.
- Replies to character-authored messages return to the exact Character Deployment.
- Persistent `Discord message_id -> deployment_id` routing survives Connector restarts.
- Mention-only, reply-only, mention-plus-reply, and opt-in Smart Participation modes.
- Ordered per-destination processing so group replies see earlier character replies.
- Small in-memory per-destination context buffer.
- Ordinary human messages are observed for context even when Mention + Reply stays silent.
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

This is required for reliable reply routing and ordinary message context. Smart Participation also requires it.

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

## Mention and Reply addressing

When one character is deployed to a destination, the normal forms continue to work:

```text
@CharacterRelayBot hello
Reply to the character's message
```

When multiple characters share a destination, address one character by its Character Card name or Discord identity name:

```text
@CharacterRelayBot Ann what do you think?
@CharacterRelayBot 宁：你同意吗？
@CharacterRelayBot Ning, are you there?
```

Bilingual display names such as `宁 · Ning` automatically expose both `宁` and `Ning` as selectors.

Address multiple named characters:

```text
@CharacterRelayBot Ann 和 宁，你们怎么看？
@CharacterRelayBot Ann and Ning, what do you think?
```

Address every active character in the Channel or Thread:

```text
@CharacterRelayBot 你们好呀
@CharacterRelayBot both of you, are you there?
@CharacterRelayBot *: hello
```

Group responses run sequentially in the destination queue. The first character reply is added to shared Channel context before the next character generates a response, reducing duplicate or contradictory replies.

After a character replies, users may reply directly to that message. Character Relay persists the outgoing Discord message ID and resolves the reply back to the original Character Deployment, even when multiple characters share the same webhook.

If a user mentions the Bot without a character name or recognized group address in a multi-character destination, the Connector returns a short disambiguation prompt instead of guessing.

### Group address aliases

Common Chinese, English, Japanese, Korean, Malay, and Indonesian group expressions are bundled in one locale pack rather than scattered through routing logic. Language-neutral `*` is also supported.

Additional Server-specific or language-specific expressions can be added without changing code:

```text
DISCORD_GROUP_ADDRESS_ALIASES=companions,team,semua kawan
```

The value accepts comma-separated or newline-separated aliases. Custom aliases extend the built-in pack.

## Character-to-character Tag conversations

A deployed character may intentionally invite another deployed character to answer by
beginning its generated reply with an explicit textual Tag:

```text
@Ning，你怎么看？
@宁 and @Zhi, can you check this?
@你们，这件事有什么遗漏？
```

Character Relay treats only a **leading** `@CharacterName` or `@group` expression as a
Bot-to-Bot trigger. Ordinary narration that merely contains another character's name does
not trigger a Provider call. A character cannot trigger itself.

Bot Tag conversations are bounded per human trigger. Defaults are:

```text
DISCORD_BOT_TAG_CONVERSATIONS_ENABLED=true
DISCORD_BOT_TAG_MAX_DEPTH=4
DISCORD_BOT_TAG_MAX_RESPONSES=8
```

`MAX_DEPTH` limits chained Tag hops. `MAX_RESPONSES` is a shared budget across all branches
created by the original human message, preventing exponential group loops. Participation
modes still apply: an internal Tag counts as a Mention, so a `reply_only` deployment remains
silent unless its mode is changed.

The runtime prompt lists other active characters at the current destination and explains the
Tag contract, while instructing characters to use it sparingly because every successful Tag
may create another Provider call.

## Context behavior

Mention + Reply observes all readable human messages in an active destination before deciding whether to respond. This allows a later explicit Mention or Reply to include the preceding conversation.

Context is currently:

- isolated by Channel or Thread;
- shared by every deployed character in that destination;
- processed serially in Discord message order;
- limited by `MAX_CONTEXT_MESSAGES`, defaulting to 20;
- stored in Connector memory and cleared when the Connector restarts.

Persistent reply routing is separate from conversation context. Discord message routes survive restarts, while recent transcript content does not yet persist.

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
DISCORD_GROUP_ADDRESS_ALIASES=
DISCORD_BOT_TAG_CONVERSATIONS_ENABLED=true
DISCORD_BOT_TAG_MAX_DEPTH=4
DISCORD_BOT_TAG_MAX_RESPONSES=8
```

The worker exposes `/health` and reports active deployments, destinations, multi-character destinations, cached reply routes, webhook readiness, Bot Tag limits, custom group-alias count, the last deployment refresh, and the last Connector error.

## Trigger behavior

```text
mention_only
  Reply only when the Bot is mentioned.

reply_only
  Reply only when a member replies to a routed character message.

mention_and_reply
  Accept either explicit trigger, including specific, multiple, and group audiences.

smart
  Behaves like mention_and_reply by default.
  Full-channel submission requires DISCORD_SMART_PARTICIPATION_ENABLED=true.
```

Smart Participation remains experimental. Bot Tag conversations are explicit and bounded; they do not enable unrestricted autonomous channel participation.

## Interaction Sessions and Sticker understanding

The Portal includes a bounded `Interaction Sessions` module. The initial Session type is
`roast`, with exactly two active Discord character deployments, a fixed speaking order,
1-3 rounds per trigger, a target Discord user ID, trigger limit, cooldown, duration, and
light/playful/sharp intensity. One round means each configured character receives one turn.
The Connector claims each target message idempotently and reports the completed run.

Incoming Discord Stickers are resolved through `/api/connectors/discord/stickers/resolve`.
Observed metadata is cached in the Portal's Sticker Dictionary. Owner-confirmed meanings are
marked `manual` and always override subsequent Discord name/description/tag metadata. Sticker
semantics are stored in shared channel context, so Sticker-only messages can be understood by
characters and by Interaction Sessions.

## Runtime behavior
