# Character Relay — Local Execution and Embodiment Roadmap

Status: **PLANNED / DEFERRED — NOT IMPLEMENTED**

Companion repository: [`wong001110/character-relay-local`](https://github.com/wong001110/character-relay-local)

This document records accepted product direction for a future device-side execution layer. It does **not** claim that Character Relay currently pairs local devices, controls desktop applications, exposes game adapters, or streams local gameplay.

Current source, tests, schemas, and merged contracts remain authoritative for implemented behavior. This roadmap is not an active branch execution ledger.

The detailed Phase 0 Local contracts live in `character-relay-local/docs/contracts/` on the Local Phase 0 contract branch until accepted/merged. Character Relay Cloud must consume those accepted wire/execution boundaries without independently redefining them.

## 1. Product goal

Extend Character Relay from a cloud-hosted Character runtime into an optional, permissioned local embodiment layer so a Character can use real applications and interactive environments on an owner's device.

First product path:

```text
paired Device
  -> real target/activity detection
  -> Deployment activity becomes visibly gaming
  -> Portal shows device/session/progress
  -> owner may Watch Live
  -> later: bounded owner-approved routine/farming execution
  -> verified outcomes may enter scoped Character evidence
```

The Local runtime is broader than gaming. Games are the first embodiment use case; later adapters may target desktop applications, browsers, creative tools, local model runtimes, smart devices, or other environments.

## 2. Existing invariants that remain authoritative

### 2.1 Deployment remains lived Character scope

Presence and lived Character runtime state remain Deployment-scoped. A Character Card is reusable definition, not a Character-global consciousness container.

A Device is owner/account-scoped. A Local session binds an authorized `deployment_id` to an owner Device for a bounded session; Local does not invent or widen Deployment identity.

### 2.2 Presence remains availability authority

Current source still defines:

```text
sleeping
idle
browsing
busy
```

and currently clears `activity_type` for non-`browsing` states. Therefore rich Local gaming activity requires a future explicit cloud schema/runtime change before it is implemented.

Accepted Phase 0 direction is **not** a new `gaming` availability enum:

```text
Presence.state = busy
Activity.kind = gaming
Activity.target = <game/application>
Activity.session_id = <verified Local session>
```

Availability and rich activity are separate concerns. This allows future activity kinds such as gaming, coding, creating, rendering, or device control without multiplying top-level Presence states.

### 2.3 Runtime/policy owns side effects

Character/model output may express intent. It never grants itself Device, plugin, risk, lease, or Local safety authority.

### 2.4 No fabricated lived experience

Only verified Local Execution Session outcomes may support claims that a Character actually completed a Local routine/action.

Autonomy opportunities, SHADOW intents, REVIEW proposals, deferred desires, or model narration are not lived execution evidence.

## 3. Repository/authority boundary

### `character-relay`

Cloud/product authority remains here:

- account/owner, Character Card, Deployment semantics;
- paired Device records and access policy;
- cloud-side autonomy policy/admission;
- Device/session orchestration;
- Presence + rich activity persistence/projection;
- Portal Device/session/autonomy UI;
- Live Watch authorization/signaling coordination;
- durable verified session-result/evidence interpretation;
- current Intelligence Core/memory/pattern/insight semantics.

### `character-relay-local`

Device-side authority belongs here:

- Windows-first desktop application/runtime;
- outbound cloud connection, heartbeat/reconnect/resume;
- local device identity + credential storage;
- process/window/activity detection;
- capture/audio/input backends;
- physical-human/device availability enforcement;
- WebRTC publishing;
- Plugin Host / MCP lifecycle;
- plugin permissions and Local safety;
- Execution Lease/session semantics;
- Adapter Lab, fixtures/traces/validation;
- optional Runtime Agent and Coding Agent providers;
- first-party game/application adapters.

### Device Protocol source of truth

Accepted v1 direction:

```text
character-relay-local
  TypeSpec source
    -> JSON Schema + conformance fixtures
       -> Local TypeScript consumer
       -> Character Relay Cloud Python/Pydantic consumer
```

Do not create a third protocol repository for v1. Do not hand-maintain semantically divergent Cloud and Local copies.

Device Protocol major version is independent from Character Relay Local application version.

## 4. Planned transport/runtime split

```text
Character Relay Cloud / FastAPI
        |
        | HTTPS + versioned WSS Device Protocol
        v
Character Relay Local
        |
        +-- local Plugin/MCP (stdio/process-local)
        +-- Native OS capabilities
        +-- WebRTC publisher
        |
        +--> target application/game

Portal / React
        |
        +-- HTTPS/WSS -> Cloud control/presence/session
        +-- WebRTC <-> Local media (authorized/signaled by Cloud)
```

Responsibilities:

- **HTTPS/WSS** — pairing, commands, session events, activity, heartbeat, resume, WebRTC signaling;
- **local MCP** — Plugin/Adapter tools; never direct public Cloud transport;
- **WebRTC** — video/audio only.

Portal control commands such as Stop/session actions continue through Character Relay Cloud. A P2P viewer is not a direct control channel to Local.

## 5. Device ownership and shared-device execution

A Device belongs to an owner/account, not permanently to one Character.

```text
Owner
├─ Device(s)
└─ Deployment(s)
```

An authorized session combines:

```text
owner
+ deployment
+ device
+ execution surface(s)
+ plugin/adapter
+ bounded session
```

One physical Device may serve multiple Deployments concurrently when required resources do not conflict.

Side-effecting resources use **Execution Leases**:

```text
desktop-input       exclusive
target input        exclusive
capture             shared-read when allowed
live viewing        shared-read
headless/API target policy-specific
```

Characters do not arbitrate conflicts with an LLM.

## 6. Autonomy Policy and Activity Rhythm

Accepted autonomy modes:

```text
OFF
SHADOW
REVIEW
AUTO
```

Accepted intent origins:

```text
user_request
user_delegated
session_recovery
character_initiated
```

Activity time policy is Deployment-scoped:

- Sleeping is a **hard gate** for Character-initiated Local activity.
- Activity `allowed` windows are hard execution windows.
- Activity `preferred` windows are soft preferences that influence autonomy opportunities.
- Durable Activity Rhythm is owner/product policy, not silently self-edited model state.

Conceptual decision split:

```text
Runtime determines WHEN an autonomy opportunity exists
Character cognition chooses WHAT high-level activity it wants
Deterministic policy decides WHETHER it may execute
Scheduler decides WHERE/when resources are allocated
Local/Adapter decides HOW the approved skill executes
```

### Deterministic contention priority

Physical human/local owner and Local safety outrank every Character session.

For Character/user intents contending for an exclusive resource:

```text
user_request
  > user_delegated
  > session_recovery
  > character_initiated
```

Within a class, deterministic age/deadline/fairness policy may apply.

Character-initiated intents expire; they do not wait indefinitely for an offline/busy Device.

Higher-priority work normally requests cooperative preemption at adapter-declared safe checkpoints. Human Stop/Take Over and Local safety may interrupt immediately.

## 7. Human presence and Device availability

Local Device availability modes:

```text
autonomy_allowed
explicit_only
do_not_use
```

The Local GUI can always narrow this authority; Cloud/model reconnect cannot silently widen it.

For interactive desktop input, V1 targets the current unlocked Windows interactive session.

Expected safety semantics:

- recent physical human activity may block a new Character-initiated interactive session;
- Windows lock/sleep/session change/target loss disarms input;
- credible physical human keyboard/pointer activity immediately disarms conflicting automation;
- explicit user-requested work can outrank another Character but does not silently seize a desktop actively controlled by the human;
- non-conflicting headless/API work may continue.

## 8. Bounded Autonomy Context

Character autonomy is not given an unrestricted raw desktop context.

A cloud-built Autonomy Context may include bounded Deployment-scoped information such as:

- time, Presence, Activity Rhythm, autonomy budget/suppression;
- relevant goals/interests and current Character Relay memory/evidence retrieval;
- relevant recent conversation summary and commitments;
- recent verified Local activity summaries;
- semantic available activities/targets and broad Device availability/constraints.

Excluded by default:

- raw desktop/video/audio;
- credentials/secrets;
- unrelated files/windows;
- low-level process/plugin internals;
- other Deployment/Character private context;
- private model chain-of-thought.

Character cognition outputs high-level preference only: activity, target preference, goal, duration preference, alternatives, and concise reason summary.

Device allocation, Execution Lease arbitration, plugin/tool sequence, and per-frame input remain runtime responsibilities.

## 9. Verified outcome -> memory/evidence

Local emits bounded verified outcomes; it does not directly write Character memory or personality.

Appropriate semantic evidence may include:

```text
completed configured routine
spent configured ordinary stamina/energy on approved farming target
routine interrupted by human takeover
```

Ordinary lived memory should not contain complete click/key/vision traces.

Owner-configured farming priority is user policy, not Character preference.

One or repeated farming runs do not directly set `likes_game` or equivalent durable traits. Repeated **Character-initiated verified choices** may become evidence that the current Character Relay Intelligence Core pattern/insight/consolidation pipeline can consider later.

The cloud must preserve the distinction among:

- owner configuration;
- Character intent/choice;
- verified execution outcome;
- sufficiently supported durable pattern/preference.

## 10. Plugin/Adapter trust boundary

Generic device capabilities remain Local Core. Target/game knowledge remains Plugin/Adapter.

V1 user-visible trust levels:

- **Official** — first-party trusted executable code, still subject to Host capability/session/lease checks;
- **Developer** — explicitly user-enabled local development code; clearly disclosed as not necessarily OS-sandboxed.

`Verified` untrusted third-party distribution is deferred until a real OS/process sandbox is implemented and validated.

Host API permissions must not be described as a complete sandbox for arbitrary Node processes.

Commercial-game adapters must not add anti-cheat bypass, process-memory injection/read for cheating automation, packet interception/manipulation, credential extraction, or client tampering as platform features.

## 11. Live Watch v1

Accepted v1 transport:

```text
Direct WebRTC P2P
  + STUN
  + TURN fallback
```

Live Watch is:

- ephemeral/on-demand;
- owner/Cloud-authorized;
- no recording or Cloud media persistence in v1;
- video/audio only, not control authority;
- independent from low-rate agent observation cadence.

A later SFU/LiveKit implementation may be added behind a `LiveStreamSession`/transport abstraction when multi-viewer/media-server requirements justify it; it is not a v1 dependency.

## 12. Routine Game Automation v1

Character Relay Gaming v1 is **routine/maintenance/repeatable farming automation**, not broad autonomous gameplay.

Potentially automatable only when owner-approved and reliably classifiable:

- bounded daily/routine maintenance;
- routine reward claiming;
- ordinary regenerating stamina/energy consumption on configured targets;
- repeatable relic/artifact/material farming;
- replaying known repeatable encounters;
- clean return to a known safe state.

Human-only in v1:

- main/story/character narrative progression;
- limited/new events and event story/gameplay;
- first-time experiential content;
- exploration, puzzles, treasure/chests, novel secrets;
- meaningful dialogue choices;
- gacha/premium currency;
- purchases/financial actions;
- destructive/account/security actions.

If an adapter cannot confidently classify content as an approved repeatable routine, it must skip/stop with a `human_required`-class result rather than improvising.

Event availability may be observed/reported; that is not permission for the Character to play it.

## 13. First game adapters

Closed commercial games are not the first architecture proof. First validate Plugin Host, Adapter Lab, capture/input, leases, safe checkpoints, cancellation, and deterministic skills in an owned/reference test environment.

After that proof, the first intended commercial adapters are:

1. **Honkai: Star Rail** — menu/state-heavy and turn-based/repeatable routine automation;
2. **Genshin Impact** — real-time 3D movement/visual control for already-approved repeatable routines.

They intentionally validate two different embodiment shapes while sharing the same Core/Plugin/Host contracts.

Initial narrow vertical slice for each:

```text
detect authorized target
  -> establish known routine state
  -> select one owner-approved routine/farming target
  -> execute bounded repeatable loop
  -> verify progress/result
  -> return/stop at known safe state
```

Neither adapter has a v1 goal of "play the whole game for me."

## 14. Agent execution model

Preferred execution hierarchy remains:

```text
deterministic skill
  -> optional Local Runtime Agent
  -> optional Cloud Agent
  -> human takeover
```

High-frequency motor control stays local.

Runtime Agent and Coding Agent remain separate. Codex/Claude Code/custom Coding Agents belong to Adapter Lab development/repair and cannot bypass runtime permission/lease/validation or automatically push/merge unreviewed changes.

## 15. Adapter Lab

Developer Mode should provide:

- target/capture/vision inspectors;
- explicitly armed input tester;
- MCP Tool Explorer;
- Skill Runner + state/safe-checkpoint trace;
- sanitized recorder/fixtures;
- L0–L3 validation;
- WebRTC diagnostics;
- reload/regression/diff/promote workflow;
- optional Coding Agent repair.

Validation levels:

- **L0 Host** — process/capture/input/audio/streaming;
- **L1 Adapter primitive**;
- **L2 bounded high-level Skill**;
- **L3 Cloud-authorized Character session through verified result**.

For game adapters, tests must also prove that an approved routine skill does not silently cross into event/story/first-time/human-only content.

## 16. Delivery milestones

### Milestone A — Presence + Live Watch

- paired owner Device;
- secure outbound connection + reconnect;
- generic target detection;
- `busy` + rich gaming activity projection;
- Portal session/activity card;
- authorized direct WebRTC Live Watch;
- interruption cleanup.

### Milestone B — Plugin + Adapter Lab

- Plugin SDK/manifest/permissions/trust boundary;
- local MCP lifecycle;
- owned/reference test adapter;
- Adapter Lab;
- deterministic control + leases + takeover + regression evidence.

### Milestone C — Routine game control + Character orchestration

- prove owned/reference control environment first;
- first routine-only Honkai: Star Rail adapter;
- first routine-only Genshin Impact adapter;
- bounded Autonomy Context + Cloud admission;
- Device/resource scheduling and cooperative preemption;
- verified outcomes -> scoped cloud evidence;
- human takeover/stop;
- no experiential/event/story automation.

### Milestone D — Optional Local/Coding Agents

- optional Runtime Agent provider abstraction;
- separate Coding Agent provider abstraction;
- bounded repair workflow through Adapter Lab;
- no permission/validation/push bypass.

### Milestone E — Distribution

- installer/updater/code signing;
- independent plugin update/rollback;
- Official/Developer distribution;
- real sandbox before Verified/untrusted third-party plugins;
- adapter compatibility/support matrix.

## 17. Deferred directions

Do not pull these into the first Local implementation unless an explicit later decision changes priority:

- Cloud GPU/headless Game Runner;
- generic unrestricted desktop agent;
- broad autonomous game playthroughs;
- event/story/first-time experiential game automation;
- public untrusted plugin marketplace before sandboxing;
- automatic Coding Agent push/merge;
- direct Cloud exposure of Local MCP;
- multi-OS parity before Windows path is proven;
- SFU/LiveKit before multi-viewer/media-server needs justify it.

## 18. Start condition

Implementation remains deferred until explicitly promoted.

When implementation begins:

1. re-read current `main` source/tests/contracts;
2. reconcile any Presence/Portal/Intelligence Core changes;
3. consume the accepted Local Phase 0 contracts rather than chat memory;
4. create a scoped active feature branch/ledger;
5. implement phase-by-phase, proving the reference environment before commercial-game control;
6. retain real test/live evidence before advancing gates.
