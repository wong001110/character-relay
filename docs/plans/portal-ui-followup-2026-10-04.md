# Portal UI follow-up — 2026-10-04

Working branch: `fix/portal-ui-followup-20261004`

The user authorized implementation and squash merge to main after verification. Do not manually deploy.

## P1 — Knowledge Fabric setup reachability

Observed: Server Knowledge pages for 1001 and Bot Testing can show “Knowledge Fabric is not bootstrapped”
with no action. The real bootstrap flow already exists under Super Admin Settings → Administration →
Knowledge Fabric.

Acceptance:
- do not create another bootstrap form or API;
- when the signed-in account is Super Admin and the server scope is missing, show a clear action that
  navigates to the existing Administration → Knowledge Fabric surface;
- non-Super-Admin and Demo users keep the explanatory empty state without an unauthorized mutation UI;
- direct navigation must land on the Knowledge Fabric administration subtab rather than Account settings.

## P1 — Lab navigation semantics

Observed: Toolbox → Open Lab shows a “Character Library” button, but the close action returns to Toolbox.

Acceptance:
- preserve the existing Toolbox → Lab ownership and return behavior;
- rename the stale control to “Back to Toolbox” / “返回工具箱” (or equivalent), so label and action agree;
- Matrix navigation is out of scope unless the same stale label is present there.

## P1 — Deployment initial loading state

Observed: first render can briefly claim “No Server profiles yet”, “Bring the Discord Connector online”,
and zero counts before the API load resolves.

Acceptance:
- the Server workspace must render an explicit loading state while the first load is active;
- do not show no-profile / connector-offline copy until loading has completed;
- Server notebook Character count must not display a factual zero while the first load is unresolved;
- preserve genuine empty/offline states after loading.

## P2 — Character Archive medium-width layout

Observed: around a 1170px viewport, four cards plus the right note rail compress names and summaries.

Acceptance:
- around tablet/small-desktop widths, cap the archive shelf at three columns while the note rail is present;
- keep existing 2-column and 1-column mobile fallbacks;
- do not remove portrait, summary, tags, status or actions to make cards fit;
- improve only targeted low-contrast helper copy involved in this workspace.

## P2 — Server Passport density

Acceptance:
- make the existing Server Passport block collapsible using the same underlying content;
- default-open is acceptable; no second Server selector or duplicate settings surface;
- the compact summary must clearly identify the section and current server when available.

## Verification

Focused evidence:
- Web typecheck;
- Web unit tests, including route/query parsing for direct Knowledge Administration navigation;
- production and mock Web builds;
- source review of responsive breakpoints and loading gates.

Integrated evidence before merge:
- repository GitHub CI;
- Railway Smoke;
- Public Demo Status Check.

Not claimed by this batch: mobile visual acceptance, live role deployment, live model tests, or a manual production deploy.
