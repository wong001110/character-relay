# Room Companion — accepted MVP, 2026-10-04

Authority: the user authorized a focused branch and PR, phase commits and verification, then
explicitly authorized the squash merge of PR #223. The subsequent user request authorizes the
sizing repair and configurable resize controls below. It does not authorize a new merge,
manual production deployment or production data changes. Preserve the independent PR #219.
Baseline is the actual fetched origin/main, not a handoff SHA. Existing Web Room participant and
follow-up contracts remain authoritative for authentication, room scope, attachments and delivery.

## Outcome and boundaries

A small Room Companion shows the current room while a browser user works in another tab.
Document Picture-in-Picture is preferred; the parent Character Relay tab must remain open.
Fallback is a fixed in-app companion with explicit capability copy, not an always-on-top claim.
No external-agent principal/API, delta protocol, new backend routes, dependency/framework migration,
reaction/sticker picker or room/member/server management in Companion.

One Portal-owned Room session owns room/profile selection, snapshot, SSE, read/unread state,
text/reply draft and send acknowledgement/idempotency. Full room and Companion subscribe to it.
Management UI, expressions picker and scroll position remain presentation-local. Cross-route
navigation and PiP close must not stop the session. Logout/account change, auth/room revocation
must discard scoped state and close/disable the Companion. In-flight results are generation-bound.

The view includes current room, connection, latest five messages, shared unread count, author/time,
reply preview, image thumbnail or file name, simple shared text composer, delivery status,
minimize, close and Open full room. Stable data attributes expose room/connection/latest/unread
and message/author/actor/reply IDs. No duplicate transport-link reply preview.

## Ordered phases and acceptance

1. **Capability spike before state refactor.** Probe actual installed Chromium using a user gesture:
   API support, requestWindow, React/DOM/style rendering, click, keyboard, close and cleanup.
   Record unsupported capabilities honestly. Browser evidence cannot establish Dots usability;
   absent Dots runtime report implementation verified / computer-agent usability unverified.
2. **Shared session.** Exactly one EventSource for the selected room regardless of subscribers/routes.
   Reconnect retains transcript and permits REST send. Refresh removes lost rooms. New messages
   increment a single unread count when no visible focused surface is reading latest; viewing latest
   in either surface acknowledges the same count. Opening alone and minimizing do not acknowledge.
3. **Minimal companion and PiP.** React portal into the PiP document, same session/actions;
   same-origin styles only, parent route retained; safe in-app fallback for absent/rejected PiP.
   Parent unload closes PiP; closing PiP only closes presentation. Open full room focuses parent
   and selects its room route. Keep browser controls and keyboard-accessible labelled actions.
4. **Reliability verification and review.** Stable client_message_id and immutable retry payload;
   only explicit same-ID retry of unknown results, never blind resend. Shared pending lock prevents
   duplicate sends across surfaces. Demo/can_post/auth guards remain; backend is authoritative.
   Preserve all six delivery states, structured reply and existing private attachment contract.
   Prove stale async results cannot cross room/account scope; test auth/room loss and lifecycle.
5. **Delivery.** Web tests/typecheck/production+mock builds; focused Python Web Room/Portal tests,
   integrated CI gates where available; actual browser journey with real isolated API data;
   review, update PROJECT_STATE.md, phase commit, push focused PR and report exact head/limitations.

## Evidence location and rollback

PROJECT_STATE.md is the sole progress/evidence handoff. architecture.md documents final ownership.
Unit tests and an isolated Playwright journey provide executable acceptance evidence; no production
credentials or private captures are retained. Revert feature commits to remove frontend-only changes.
Dots visibility/input while Gemini is foreground remains a separate user-runtime acceptance gate.

## Accepted sizing follow-up (2026-10-04)

The user requested a default small window and configurable width/height for cloud computer agents
such as Dots. Local Chromium/Xfwm4 experiments establish a reproducible global-window-size override;
the actual Dots launch parameters/root cause remain unconfirmed. The frontend repair targets the
observed oversized window without assuming its cause or changing the browser environment.

- First open targets a **380×480 content area**, with Small/reset and Medium **480×640** presets.
  Custom dimensions use labelled integer pixel inputs, width **320–2000**, height **320–1600**.
  Browser/screen limits may reduce the result; expose actual content dimensions and handle denied
  resizing explicitly. Invalid inputs must never resize or submit a room message. When a browser
  keeps different dimensions, expose a direct **Use W×H** action for the saved selection, including
  the default small size. It executes synchronously on a genuine PiP click.
- After native requestWindow and document preparation, perform a bounded best-effort resize using
  measured outer-minus-inner frame margins. A resize failure must leave a usable PiP open. No
  perpetual resize correction, no cache-reset-only workaround, and no replacement browser window.
  Chromium requires user activation in the PiP window for resizeTo and consumes parent activation
  when opening it. If a launcher overrides the initial size, automatic correction cannot be promised;
  the explicit one-click application is the supported repair. Tests must not inject activation when
  measuring or testing the automatic path.
- Remember explicit/custom and manual dimensions for close/reopen during the current authenticated
  Portal lifetime, including across its routes. Reset sizing memory when authentication/room access
  ends; no persistence of room/account data or sizing preferences in localStorage is required.
- Controls operate only on native PiP. The in-app fallback retains its explicit capability copy;
  Open full room keeps the Companion open. Room/auth/session/SSE/draft/send semantics stay intact.
- Prove default-size request/explicit application, custom, manual close/reopen and reset with the real isolated API and native headed
  Chromium on a 1364×1024 Xfwm4 desktop, including the reproducible launch override. Verify validation,
  native resize denial/clamping, single SSE, shared draft and the existing functional journey.
