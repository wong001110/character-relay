# Debug Discord conversations

Use the least sensitive diagnostic surface that answers the question.

## 1. Check the ordinary signals

- Confirm the Connector `/health` endpoint is healthy and has a recent deployment refresh.
- Confirm the Connection, Server Profile, Deployment, Channel/Thread, participation mode, and exclusions match the message.
- In **Deployment Center**, open the selected Server's Discord event log for IDs, decisions, reason codes, counts, timings, and delivery state. Use **Behavior Notebook** for Character Runtime/Provider traces and the temporary capture described below.
- Check API and Connector process logs for an allowlisted error kind/code or HTTP status.

Ordinary logs intentionally do not contain message text, prompts, responses, nested payloads, tokens, or credentials.

## 2. Temporarily capture Runtime ingress

When structured signals are insufficient, a configured Bootstrap Admin/Super Admin can use Option B:

```text
Behavior Notebook
→ select the affected Discord Server
→ Runtime ingress capture
→ choose 15 minutes / 1 hour / 24 hours
→ Start capture
→ reproduce once
→ explicitly reveal only the needed record
→ Stop and Clear
```

The raw payload is held only in bounded application-process memory. It is scoped to one stored Server Profile, is never written to SQLite/backups/OpenWiki, and disappears on application restart. It captures normalized messages that reach a real Character-generation step, not every Discord Gateway event.

Do not paste revealed content into issues, chat, screenshots, fixtures, or documentation. Record the source IDs, structured outcome, and a redacted explanation instead. The full access, retention, capacity, and Option C extension contract is [Discord temporary debug capture](../discord-debug-capture.md).

## 3. Interpret common outcomes

| Symptom | Check first |
| --- | --- |
| Bot is offline | Connector process, Bot token, Gateway intent, and `/health` |
| No reply and no Runtime event | destination exclusions, Server/Connection mapping, participation trigger |
| Runtime receives the turn but stays silent | v3 participation decision and structured reason |
| Character generated but nothing appeared | durable delivery claim/ack state and Discord permissions/webhook readiness |
| Reply reaches the wrong Character | persisted Discord message route and Deployment IDs |
| Works until restart | Connector settings, deployment refresh, and supported persistent vs in-memory state |

After a real-environment fix, complete the relevant [manual Discord checks](../manual-validation.md#discord-end-to-end).
