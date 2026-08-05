# Discord Interaction Sessions and Sticker Understanding

## Interaction Sessions

The initial Interaction Session type is `roast`. It is intended for a consenting test member or the operator's own Discord test account.

A Session is scoped to one Discord connection, Server, Channel, and target Discord user ID. It uses exactly two active Character Deployments in a fixed speaking order.

Portal controls:

- `Rounds per trigger`: 1–3. One round gives each selected character one reply.
- `Maximum triggers`: 1–5 target messages may claim the Session.
- `Cooldown`: minimum delay between accepted target messages.
- `Duration`: automatic Session expiry.
- `Intensity`: `light`, `playful`, or `sharp`; every level remains bounded by the same non-abusive content rules.
- `Status`: active, paused, stopped, or completed.

Each target Discord message is claimed idempotently. The fixed speaking order is controlled by the Session rather than generated Character Tags. Session failures are recorded, while an unavailable Session API falls back to normal Discord routing instead of blocking the Channel.

The model prompt restricts a Roast Session to the target member's current words, harmless choices, gameplay, coding mistakes, lateness, or self-directed jokes. It must not target protected or sensitive identity traits, health, body, appearance, trauma, family, private data, or threats, and it must not invent personal facts.

## Incoming Sticker understanding

The Discord Connector reads Sticker metadata and resolves it through the Character Relay API. The shared context stores:

- Sticker ID and name;
- Discord description and tags when available;
- format and asset URL;
- interpreted intent, emotion, description, source, and confidence.

Observed Stickers appear in the Portal Sticker Dictionary. A manually saved meaning has source `manual`, confidence `1.0`, and overrides later Discord metadata changes. Without a manual meaning, the current MVP uses the Sticker name, description, and tags; it does not call a Vision model.

Sticker-only messages remain in recent Channel context and can trigger a matching Interaction Session. Normal Participation Mode still governs ordinary character replies outside an Interaction Session.

This feature covers inbound Sticker understanding. Character-owned outbound Reaction Assets remain a separate future capability.
