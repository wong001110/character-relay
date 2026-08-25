# Character Relay — Local Execution and Embodiment Roadmap

Status: **PLANNED / DEFERRED — NOT IMPLEMENTED**

Companion repository: [`wong001110/character-relay-local`](https://github.com/wong001110/character-relay-local)

This document records accepted product direction for a future device-side execution layer. It does **not** claim that Character Relay currently pairs local devices, controls desktop applications, exposes game adapters, or streams local gameplay.

Current source, tests, schemas, and merged contracts remain authoritative for implemented behavior. This roadmap must not be treated as an active branch execution ledger. When implementation begins, create a scoped feature branch and a branch-local `docs/active-development-plan.md` entry that names that branch and its current phase.

## 1. Product goal

Extend Character Relay from a cloud-hosted character runtime into an optional, permissioned local embodiment layer so a Character can use real applications and interactive environments on a user's device.

The first target experience is gaming presence:

```text
Character decides or is asked to play
  -> Character Relay selects an available paired device
  -> local runtime launches or observes the game
  -> Deployment activity becomes visibly gaming
  -> Portal shows the active game and session progress
  -> owner may open a low-latency live view
  -> verified session results may become later conversation evidence
```

The local runtime is broader than gaming. Games are the first embodiment use case; later adapters may target desktop applications, browsers, creative tools, local model runtimes, smart devices, or other environments.

## 2. Existing invariants that must remain unchanged

### 2.1 Deployment remains the lived Character runtime scope

Current Presence is Deployment-scoped. A Character Card remains a reusable definition and must not acquire hidden cross-server lived state through local execution.

A local device is account/owner-scoped. When a device session is acting for a Character, the lived activity and resulting evidence must be associated with the authorized Deployment/session scope rather than becoming Character-global state by accident.

### 2.2 Presence remains Runtime authority

Current merged Presence states are `sleeping`, `idle`, `browsing`, and `busy`. The repository currently restricts `activity_type` to browsing behavior. This roadmap therefore does **not** declare a new `gaming` Presence enum as already accepted implementation.

Phase 0 must choose and document one canonical representation for gaming activity, for example:

- a new Presence state; or
- `busy` plus a generalized typed activity/session projection.

The decision must preserve availability and Smart Participation semantics and must be implemented in source/tests before Portal UI depends on it.

### 2.3 Runtime owns authority and side effects

Model output may express intent, but it must not bypass device permissions, plugin permissions, user policy, session policy, or runtime validation.

### 2.4 No fabricated lived experience

A Character may only later claim to have played, watched, completed, collected, or changed something when the local runtime produced objective session evidence for that event. A roleplay model must not manufacture local-device activity logs.

## 3. Repository boundary

### `character-relay`

Cloud/runtime authority remains here:

- account, Character Card, Deployment, and Presence authority;
- paired device records and authorization;
- cloud-to-device command/session orchestration;
- Portal device/session/presence UI;
- live-view authorization/signaling tokens;
- persisted game/session summaries and auditable outcomes;
- conversion of verified outcomes into scoped memory/evidence when appropriate;
- server-side policy and permission decisions.

### `character-relay-local`

Device-side execution belongs in the companion repository:

- local desktop GUI;
- outbound cloud connection, heartbeat, reconnect, and session resume;
- device identity and local credential storage;
- process/window detection;
- window/audio capture;
- keyboard/mouse or other local input backends;
- on-demand WebRTC publishing;
- plugin host and MCP client/host boundary;
- plugin permission enforcement;
- Adapter Lab, traces, fixtures, and local validation;
- optional local runtime-agent providers;
- optional coding-agent providers for adapter development/repair;
- installer, updater, and platform-specific native code.

### Protocol ownership

Cloud ↔ Local messages must have one versioned schema authority. Do not maintain independent handwritten copies that can silently drift. Phase 0 must choose the concrete schema/code-generation mechanism before implementation.

Plugin ↔ Local Host contracts are owned by the local repository and its Plugin SDK.

## 4. Planned architecture

```text
                         Character Relay Cloud

                 Character / Deployment Runtime
                           |          |
                       intent      Presence
                           |          |
                    Game/Device Session
                           |
                    WSS control + telemetry
                           |
                    Character Relay Local
                 +---------+-----------+
                 |                     |
             Plugin/MCP             Capture
                 |                     |
            Game Adapter          encoder/audio
                 |                     |
        vision + skills + input        |
                 |                     |
                Game              WebRTC media
                                       |
                                       v
                                 Portal Live View
```

Transport responsibilities are deliberately separate:

- **HTTPS/WSS** — pairing, commands, session events, Presence, progress, heartbeat, resume;
- **local MCP (prefer local process/stdio)** — high-level tools exposed by local plugins/adapters;
- **WebRTC** — live video/audio; media must not be tunneled through MCP or ordinary telemetry messages.

The local client initiates outbound connections. Character Relay Cloud should not require an inbound public port on the user's machine.

## 5. Plugin and Adapter model

Terminology:

- **Plugin** — installable/distributable package.
- **Adapter** — runtime integration inside a plugin for a specific game/application/environment.

Generic device capabilities belong to Local Core. Environment-specific knowledge belongs to plugins.

```text
Local Core
  process detection
  window/audio capture
  input
  streaming
  permissions
  MCP/plugin lifecycle

Plugin / Adapter
  how to recognize the target
  how to understand its screens/state
  which high-level skills are supported
  how a skill advances and verifies success
```

First-party adapters may initially live in the `character-relay-local` monorepo, but they must use the same plugin contract intended for later external packages.

Planned capability tiers:

1. **Presence** — detect the application/game and report activity.
2. **Integration** — use an official/mod/API integration where available.
3. **Visual Control** — capture + UI/state recognition + local input where permitted and appropriate.

A plugin manifest must declare capabilities and requested permissions. Plugins must not gain unrestricted desktop access merely because they are callable through MCP.

## 6. Agent execution model

High-frequency motor control must remain local. The cloud Character model must not issue individual mouse coordinates or key presses as its normal gameplay loop.

Preferred hierarchy:

```text
Character intent / long-term goal
            |
      high-level skill
            |
  deterministic local controller
            |
       local environment
```

Fallback policy may later be:

```text
deterministic skill
  -> optional local runtime agent
  -> cloud agent
  -> human takeover
```

### Runtime Agent vs Coding Agent

Keep these as separate provider types.

**Runtime Agent** helps a Character execute an environment task. It may be absent, cloud-backed, local-model-backed, or hybrid.

**Coding Agent** edits and repairs adapter code in Developer Mode. Planned providers may include Codex, Claude Code, or a custom coding-agent integration. A Coding Agent must operate through repository permissions and Adapter Lab tools/tests; it must not automatically push unreviewed changes to `main`.

## 7. Live viewing model

The Portal target is real-time viewing, not periodic screenshots.

Initial target when implementation begins:

- target-window capture rather than whole-desktop capture by default;
- 720p30 baseline;
- H.264 video and game/system audio where supported;
- hardware encoder when available;
- on-demand publishing only while at least one authorized viewer is subscribed;
- separate low-rate observation sampling for the agent, independent of the viewer frame rate.

Phase 0/3 must decide whether the first transport implementation uses direct WebRTC + TURN or an SFU abstraction such as LiveKit. The product contract should depend on `LiveStreamSession`, not on a specific vendor.

## 8. Adapter Lab

`character-relay-local` should include a first-class Developer Mode rather than relying on ad-hoc scripts.

Planned Adapter Lab capabilities:

- target/process inspector;
- live capture inspector and detected-region overlay;
- input tester with explicit temporary arming and target-window restriction;
- MCP tool explorer;
- vision/state inspector;
- high-level skill runner and state-machine trace;
- session recorder with sanitized fixtures;
- regression test runner;
- local WebRTC preview and remote subscriber test;
- diff/reload/promote workflow;
- optional Coding Agent repair workflow.

Validation levels:

- **L0 Host** — process, capture, input, audio, streaming;
- **L1 Adapter primitive** — observe, detect, find target, open/interact;
- **L2 Skill** — one complete high-level environment skill;
- **L3 Character session** — cloud/local intent through verified outcome, Presence, and persisted session result.

Recorded traces must be opt-in developer artifacts, redacted/sanitized, and must never contain account secrets, provider credentials, private unrelated desktop content, or raw authentication state.

## 9. Security and policy boundaries

Before control is enabled, the product must provide explicit owner-visible permissions for at least:

- target process/window access;
- screen capture;
- audio capture;
- keyboard input;
- mouse input;
- filesystem/network access when a plugin genuinely requires either;
- local agent/coding agent execution.

Commercial-game adapters must respect game/platform rules. Character Relay must not make anti-cheat bypass, process-memory injection, packet interception, credential extraction, or client tampering part of its platform contract.

Presence and Live Watch should remain useful even when a game's control adapter is unsupported or intentionally disabled.

## 10. Delivery milestones

### Milestone A — Presence + Live Watch

This is the first product milestone and should be completed before autonomous game control.

- paired local device;
- secure outbound connection + heartbeat/reconnect;
- generic process/game detection;
- canonical gaming-activity projection into Character Relay Presence/Portal;
- target-window capture and audio;
- authorized on-demand WebRTC Live Watch;
- session interruption cleanup when the device disconnects.

**Acceptance:** starting a supported test application on a paired device makes the correct Deployment visibly active in Portal, and the owner can open a low-latency live stream without granting control permissions.

### Milestone B — Plugin + Adapter Lab + deterministic tools

- Plugin SDK/manifest/permission boundary;
- local MCP host/client lifecycle;
- reference/test adapter;
- Adapter Lab GUI;
- deterministic high-level skills and regression traces;
- explicit input arming and kill/stop control.

**Acceptance:** a developer can install/load a reference plugin, inspect its tools, execute one high-level skill against a real test environment, watch it live, record a sanitized trace, and pass L0–L2 validation.

### Milestone C — Character-controlled sessions

- Character/Deployment session orchestration;
- high-level skill delegation from cloud runtime;
- progress/events/interrupt/resume;
- verified outcomes into scoped memory/evidence;
- human takeover/stop;
- optional local Runtime Agent and hybrid fallback policy.

**Acceptance:** a Character can start an authorized session, execute a bounded task through a local adapter, expose progress/live view in Portal, end cleanly, and later describe only the verified outcome.

### Milestone D — Self-maintaining adapter workflow

- Coding Agent Provider abstraction;
- Codex / Claude Code integration candidates;
- Adapter Lab MCP for inspect/run/reload/test operations;
- failure trace → bounded code repair → regression gate → human diff acceptance;
- separate local commit and push controls.

**Acceptance:** an intentionally broken reference adapter can be repaired by an authorized coding agent, validated against the Lab gate, and presented as a reviewable diff without automatic merge/push.

## 11. Phase plan for later implementation

### Phase 0 — Contract freeze

- reconcile current Presence semantics with gaming activity;
- define `Device`, `DeviceSession`/`GameSession`, capability, command, event, and interruption contracts;
- define owner/Deployment/device/session scope and authorization;
- define Cloud ↔ Local protocol versioning;
- define plugin permission model and threat model;
- choose first Live Watch transport implementation behind a transport abstraction;
- define explicit non-goals for the first release.

Gate: canonical contracts accepted; no implementation assumptions remain implicit.

### Phase 1 — Local desktop and device pairing

- bootstrap `character-relay-local` desktop shell;
- local credential store;
- pairing flow;
- outbound WSS connection;
- heartbeat, reconnect, and session resume primitives;
- Normal Mode device/status GUI.

Gate: device can pair, reconnect, and appear online/offline correctly without any game integration.

### Phase 2 — Generic activity detection

- process/window inventory;
- generic game/application registry;
- activity telemetry;
- cloud persistence/projection;
- Portal device/session card;
- disconnect/interruption cleanup.

Gate: a reference target changes Portal activity correctly with no control plugin installed.

### Phase 3 — Live Watch

- target-window capture;
- audio capture;
- encoder selection;
- WebRTC publish/subscription authorization;
- Portal viewer;
- viewer-count-driven start/stop;
- network fallback/reconnect behavior.

Gate: 720p30 baseline live viewing passes local/remote validation and stops publishing when no viewer remains.

### Phase 4 — Plugin runtime and MCP boundary

- plugin manifest and discovery;
- Local Host API and permission checks;
- MCP process lifecycle, preferably local/stdio for first-party adapters;
- reference adapter;
- capability negotiation/versioning.

Gate: plugin cannot exceed its declared/approved permissions and high-level tools can be discovered/called locally.

### Phase 5 — Adapter Lab

- inspectors, Tool Explorer, Skill Runner, recorder, trace viewer;
- input arming/kill switch;
- L0–L2 test harness;
- hot reload/relevant regression workflow;
- stream diagnostics.

Gate: reference adapter can be developed and validated without involving the Character cloud agent.

### Phase 6 — First real environment adapter

Prefer an API/mod-friendly or owned test environment before closed commercial-game automation.

- implement high-level deterministic skills;
- CV/OCR/state detection fast path;
- optional VLM fallback for unknown state;
- local high-frequency controller where necessary;
- bounded error recovery.

Gate: repeatable end-to-end environment task passes live and recorded regression tests.

### Phase 7 — Character session orchestration

- cloud intent → local bounded task;
- progress and structured result events;
- interruption/cancel/resume;
- Presence/session synchronization;
- verified result → scoped lived evidence;
- owner takeover/stop.

Gate: L3 Character session passes without fabricated completion or stale Presence.

### Phase 8 — Optional local/hybrid Runtime Agent

- provider abstraction;
- local OpenAI-compatible endpoint / Ollama / LM Studio-class integrations as candidates;
- delegation policy and privacy controls;
- deterministic → local → cloud → human fallback;
- cloud-visible semantic state without requiring raw frame upload when configured.

Gate: the same bounded task can run with Local Agent disabled or enabled without changing adapter contracts.

### Phase 9 — Coding Agent and adapter repair

- separate Coding Agent Provider abstraction;
- Codex/Claude Code/custom integration candidates;
- Adapter Lab MCP surface;
- bounded repository workspace permissions;
- repair task summaries/tool traces only, never private model chain-of-thought;
- validation gate before accepting changes.

Gate: automated repair cannot bypass test, diff-review, permission, or push boundaries.

### Phase 10 — Distribution and ecosystem

- installer/update strategy and code signing;
- official/verified/developer plugin trust levels;
- plugin package/update flow;
- compatibility metadata;
- SDK/documentation for third-party adapters;
- commercial-game support matrix with Presence / Integration / Visual Control distinctions.

Gate: plugin lifecycle is independently versioned from the Local Core and a broken adapter update can be rolled back without replacing the whole runtime.

## 12. Deferred directions

Do not pull these into the first local implementation unless a later accepted contract changes priority:

- Cloud GPU Game Runner;
- generic cloud desktop execution;
- headless remote game workers;
- simulation-only game activity;
- third-party plugin marketplace;
- arbitrary unrestricted desktop-control agent;
- automatic adapter code merge/push;
- direct cloud exposure of local MCP servers.

The architecture may later introduce a generic Runner abstraction (`LocalRunner`, `CloudRunner`, `HeadlessRunner`, `SimulationRunner`), but the first implementation should prove `LocalRunner` without forcing speculative cloud complexity.

## 13. Start condition

This roadmap is intentionally deferred while current Character Relay feature work continues.

Begin implementation only when the owner explicitly promotes this roadmap into an active feature branch. At that point:

1. re-read current `main` source/tests because Presence, Portal, tools, or runtime boundaries may have changed;
2. update this roadmap where accepted architecture changed;
3. create the active branch ledger with Phase 0 as the first gate;
4. initialize implementation in `character-relay-local` from its current `main`, not from assumptions recorded here.
