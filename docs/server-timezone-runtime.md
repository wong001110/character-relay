# Server timezone runtime

Character Relay uses `Asia/Kuala_Lumpur` as the product-level default timezone. Each Discord Server Workspace can still store another explicit IANA timezone when needed.

The runtime uses the resolved Server timezone for three related behaviors:

- character prompts receive the Server's current local date/time so unqualified time references are interpreted consistently;
- `utility.current_time` uses the Server timezone when no explicit override is supplied;
- `scheduler.remind` accepts an ISO-8601 local time without an offset and interprets it in the Server timezone before storing the reminder in UTC.

The setting is stored in a companion runtime table so existing SQLite databases do not require an in-place `ALTER TABLE` migration. Existing Server Profiles without a runtime row now fall back to `Asia/Kuala_Lumpur`. Runtime rows written as `UTC` by the former default are converted once during startup; a migration marker prevents a later intentional UTC choice from being changed again.

Portal observability keeps persisted timestamps in UTC but treats timezone-less SQLite API timestamps as UTC and renders Scheduler / Provider Trace times in Malaysia time (MYT).

Provider Trace treats a follow-up provider request containing a failed Tool result (`ok: false`, or failed/rejected/error status) as an error. A later successful model response does not overwrite that Tool failure back to `succeeded`.

The Super Admin Toolbox also includes a direct Tool Calling Runtime test panel. It executes only Tools enabled on the selected Deployment, requires explicit confirmation for side-effect Tools, and exposes the Runtime result independently from an LLM's decision to call a Tool.
