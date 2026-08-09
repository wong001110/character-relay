# Server timezone runtime

Each Discord Server Workspace can store a default IANA timezone, for example `Asia/Kuala_Lumpur`.

The runtime uses that timezone for three related behaviors:

- character prompts receive the Server's current local date/time so unqualified time references are interpreted consistently;
- `utility.current_time` uses the Server timezone when no explicit override is supplied;
- `scheduler.remind` accepts an ISO-8601 local time without an offset and interprets it in the Server timezone before storing the reminder in UTC.

The setting is stored in a companion runtime table so existing SQLite databases do not require an in-place `ALTER TABLE` migration. Existing Server Profiles without a runtime row fall back to UTC until an owner saves a timezone in Server settings.

Provider Trace treats a follow-up provider request containing a failed Tool result (`ok: false`, or failed/rejected/error status) as an error. A later successful model response does not overwrite that Tool failure back to `succeeded`.
