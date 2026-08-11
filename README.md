# Character Relay

**A playful AI character research studio for creating, testing, deploying, and observing persistent characters in real group chats.**

Character Relay grew out of Echo Masque. Echo Masque remains the evaluation and pressure-testing module, while Character Relay is the wider product: Character Cards, runtime configuration, Discord deployment, Smart Participation, media perception and creation, tools, evaluation, and runtime observability.

The product is intentionally **creator-oriented rather than enterprise-oriented**. The UI direction is a 50 / 50 balance between clear product interaction and a notebook / scrapbook character-lab identity.

## Product loop

```text
Create a Character
  -> configure persona, model, tools, memory, and participation behavior
  -> test it in Echo Masque / Lab
  -> deploy it into a real Discord server
  -> let multiple characters participate naturally
  -> observe why a character joined, what it perceived, which tools it used,
     and how the runtime produced the final response
  -> refine the character and repeat
```

## Current product areas

- **Character Studio** — user-owned Character Cards, persona data, prompt/model bindings, semantic participation profiles, and character-level configuration.
- **Deployment Center** — platform connections, Discord server profiles, character deployments, webhook identities, channel exclusions, memory scopes, knowledge, tools, and Smart Participation settings.
- **Discord Connector** — managed Gateway integration with per-character webhook identities, explicit addressing, Smart Participation, multi-character social turns, tool execution, media handling, and durable delivery boundaries.
- **Smart Participation** — deterministic signals plus optional semantic relevance, candidate ranking, primary / secondary relationships, interjection and follow-up behavior, cooldowns, and rate limits.
- **LangGraph Runtime** — Character Turn, Social Turn, and condition-watch orchestration with privacy-safe runtime tracing.
- **Behavior / Provider Observability** — Runtime Trace, Provider Trace, media epistemic state, model latency/tokens, tool routing, and provider request inspection.
- **Media Runtime** — character-controlled media attention, media understanding, article/video extraction, shared analysis cache, conversation media references, and image creation through runtime tools.
- **Echo Masque Lab** — deterministic and model-backed character evaluation, scenarios, test packs, experiments, reports, calibration, and matrices.
- **Security boundaries** — owner-scoped resources, encrypted provider credentials, audit controls, quotas, and a read-only public Demo mode.

## UI / design direction

The next Portal pass treats Character Relay as an **AI Character Research Studio**, not a conventional SaaS admin dashboard.

Target visual balance:

```text
50% clear product UI
+ 50% notebook / scrapbook / anime character-lab personality
```

The design language should use visual objects to communicate meaning rather than turning every element into the same generic card:

- notebook pages for primary workspaces;
- Polaroid-style character identity cards;
- sticky notes for explanations and behavior summaries;
- receipts for Provider calls;
- tickets for Tool calls;
- stamps for completed / blocked / failed runtime decisions;
- index tabs for navigation and filters;
- margin notes for contextual inspection;
- archive sheets for Raw JSON and low-level diagnostics.

The intended application shell is:

```text
Character Relay
├── Characters
├── Deployments
├── Lab
├── Observer
└── Settings
```

**Observer** is planned as the human-readable replacement for treating Runtime Trace and Provider Trace as two unrelated log viewers. A Character Turn should become the primary unit of observation, with Provider calls, Tool calls, media behavior, Smart Participation evidence, state changes, and Runtime authorization attached to the relevant step.

## Character portraits and deployment identity

Character Cards currently use a built-in portrait variant. The next character-identity pass should add **user-uploaded Character Card portraits**.

Deployment identity should follow a simple inheritance rule:

```text
Deployment avatar override
        ↓ if empty
Character Card portrait
        ↓ if empty
Character Relay default portrait / silhouette
```

A Deployment may still override its avatar when a character needs a different identity in a particular server. If no deployment-specific image is configured, the Character Card portrait should be used automatically.

This keeps the Character Card as the canonical visual identity while preserving per-server customization.

## Runtime architecture

```text
Chat platform
  -> Platform Connector
  -> audience / participation routing
  -> Social Turn Runtime
  -> Character Turn LangGraph
       -> context / RAG / media perception
       -> provider model
       -> optional Tool loop
       -> Smart Output
       -> Runtime authority
  -> platform-specific renderer / delivery
```

The Runtime keeps raw messages, prompts, RAG excerpts, credentials, Tool arguments/results, and final reply text outside persistent LangGraph coordination state where possible. Runtime Trace stores bounded orchestration evidence, while Provider Trace stores bounded provider-call diagnostics according to the configured trace mode.

## Character Turn graph

The current Character Turn graph follows this shape:

```text
START
  -> turn_resolve
  -> turn_context
  -> turn_model
       -> turn_tool_execution -> turn_model   (when tools are requested)
  -> turn_smart_output
  -> turn_authority
  -> END
```

Social Turn orchestration coordinates ordered multi-character participation around Character Turn execution.

## Smart Participation

Smart Participation can score eligible Discord character deployments using signals such as:

- question / help-request detection;
- configured topics, keywords, and trigger phrases;
- avoid phrases and cooldown blocks;
- optional semantic relevance;
- initiative style (`quiet`, `balanced`, `active`);
- recent-turn and lightweight follow-up context;
- primary / secondary character relationships.

The runtime can select multiple characters when the evidence supports it and assigns ordered social roles such as `primary`, `interject`, and `complement`.

## Media behavior

Characters can decide whether shared media is worth inspecting before a response is produced. Runtime observability separates:

- **actual perception** — whether usable media context was really obtained;
- **attention decision** — whether the character chose to inspect or skip;
- **declared social stance** — e.g. truthful, bluff, lie, tease, evasive, guess, or uncertain;
- **grounding** — how the outward stance relates to actual perception.

Media V2 also includes generated-image delivery/reference handling, short-lived generated artifacts, conversation media references, cache-aware media understanding, and runtime image-creation tools.

## Deployment model

One Character Card may be deployed to multiple Discord destinations and servers. Deployments remain independently configurable for runtime behavior and identity.

```text
Ann
├── Discord / Main Server
│   ├── #general
│   └── #ann-room
└── Discord / Roleplay Server
    └── selected channels / threads
```

A deployment can carry its own:

- status;
- participation mode;
- memory scope;
- server / channel scope and exclusions;
- message identity and aliases;
- enabled tools;
- Smart Participation behavior;
- knowledge context;
- runtime/error state.

## Discord Connector

The Discord worker lives in `connectors/discord` and uses the official Discord Bot Gateway.

Current capabilities include:

- active deployment caching and connector heartbeat;
- Discord server profiles and channel inventory;
- explicit mention/reply routing;
- Smart Participation candidate scoring and coordination;
- per-character webhook message identities;
- recent conversation buffering;
- multi-character Social Turn continuation;
- serialized delivery and Gateway event deduplication;
- Runtime Tool Calling;
- sticker / expression handling;
- media attachments, embeds, link previews, and reply media references;
- generated-media delivery through authenticated connector endpoints;
- durable runtime recovery boundaries.

Telegram and WhatsApp remain future connector directions rather than equivalent current production integrations.

See `connectors/discord/README.md` for Discord Developer Portal and Railway setup.

## Echo Masque evaluation module

Echo Masque continues to provide:

- exact Runtime System Prompt inspection;
- Benchmark and Adaptive pressure testing;
- Rules, Semantic, and Hybrid Judge modes;
- identity, memory, instruction-resistance, capability-honesty, persona, and language coverage;
- immutable Run and Evaluation Snapshots;
- human-controlled calibration labels and exact evidence;
- Matrix experiments and regression comparison;
- reviewable AI-assisted Scenario and Test Pack authoring;
- secret-free templates, archives, and sharing bundles.

OOC / consistency evaluation belongs mainly to authoring, testing, debugging, and release validation. A deployed character is not required to pay the latency and token cost of an OOC judge on every normal chat message.

## Quick start

Requires Python 3.12+ and Node.js 22+ for the main application. The Discord Connector uses Node.js 24.17+.

```bash
python run.py
```

Open:

```text
Web UI: http://127.0.0.1:5173
API:    http://127.0.0.1:8000/docs
```

Other launcher options:

```bash
python run.py --install
python run.py --no-install
python run.py --api-only
python run.py --no-reload
```

## Public demo account

The production URL currently remains:

```text
URL: https://echo-masque-production.up.railway.app
Email: demo@echo-masque.app
Password: EchoMasqueDemo2026!
```

The shared Demo workspace is read-only. Server-side mutation boundaries remain authoritative even if a UI control is accidentally exposed.

## Connector API

The Discord worker uses shared-secret internal endpoints under the connector API, including deployment retrieval, heartbeat, message execution, Smart Participation support, webhook identity management, and generated-media delivery.

Generated media is delivered through an authenticated connector sub-route and is not treated as permanent public storage.

## Authentication and credential security

Production uses Argon2 password hashes, opaque server-side Sessions, HttpOnly cookies, invitation-controlled registration, user/Admin roles, owner-scoped resources, encrypted provider credentials, MultiFernet rotation, redacted Audit Events, and secret-free account export.

Raw keys, encrypted blobs, Session tokens, password hashes, invitation codes, Bot tokens, shared connector secrets, and local connector sessions must not enter exports, snapshots, reports, or normal logs.

## Production deployment

Deploy the root `Dockerfile` with `railway.toml`, one replica, and a Railway Volume mounted at `/data`.

Character Relay application settings use the `CHARACTER_RELAY_*` environment prefix.

Typical production variables include:

```text
CHARACTER_RELAY_ENVIRONMENT=production
CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db
CHARACTER_RELAY_LEGACY_LOCAL_USER_ENABLED=false
CHARACTER_RELAY_PUBLIC_REGISTRATION_ENABLED=false
CHARACTER_RELAY_BOOTSTRAP_ADMIN_EMAIL=<admin email>
CHARACTER_RELAY_BOOTSTRAP_ADMIN_PASSWORD=<long unique password>
CHARACTER_RELAY_CREDENTIAL_ENCRYPTION_KEYS=<Fernet key>
CHARACTER_RELAY_CONNECTOR_SHARED_SECRET=<long random connector secret>
```

Keep credentials, encryption keys, Bot tokens, connector secrets, and administrator passwords outside Git.

## Validation

Pull requests run Python lint/type/test coverage, web TypeScript/Vitest/build validation, Discord Connector TypeScript/Vitest/build/container validation, and deployment smoke checks.

Observability failures should never break a Character request; runtime/provider tracing is diagnostic infrastructure rather than an execution dependency.

## Documentation

- `CHECKLIST.md`
- `connectors/discord/README.md`
- `docs/phase-15-security.md`
- `docs/phase-16-authoring.md`
- `docs/phase-16-ai-authoring.md`
- `docs/phase-16-calibration.md`
- `docs/phase-16-rubric-coverage.md`
- `docs/phase-16-release.md`
- `docs/railway-deployment.md`
