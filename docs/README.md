# Character Relay documentation

Status: **canonical navigation index**

Choose the path that matches what you are trying to do:

| I am… | Start here |
| --- | --- |
| Using Character Relay | [User guide](user/README.md) |
| Running production or handling an incident | [Operator guide](operator/README.md) |
| Developing the product | [Developer guide](developer/README.md) |
| An AI coding agent taking over work | repository `AGENTS.md`, then [AI agent workflow](ai-agent-development-workflow.md) and [agent handoff](agent-handoff.md) |
| Looking for current authority | [Canonical contracts](contracts/README.md) |
| Investigating why an old design exists | [Historical/reference index](history/README.md) |

## Product support snapshot

Discord is the current production connector. New Connection and Deployment creation is Discord-only; legacy WhatsApp and Telegram records remain readable/deletable for compatibility, but are not supported runtimes.

Intelligence Core v3 is the current intelligence authority. Topic fallback, Topic-scoped durable memory, `topic_id` continuation authority, and Topic-driven Wiki/Discovery behavior must not be reintroduced. See the [v3 contract](intelligence-core-v3-architecture.md).

## Fast links

- [Set up Discord](user/discord-setup.md)
- [Debug Discord](user/discord-debugging.md)
- [Deploy on Railway](railway-deployment.md)
- [Security and privacy](security.md)
- [Run release checks](manual-validation.md)
- [Repository architecture](architecture.md)
- [Current branch execution ledger](active-development-plan.md) — use only when its recorded branch matches the checkout

## Evidence and authority

For implemented behavior, use this order:

1. source, schemas/types, migrations, and tests on the current branch;
2. current `main` when establishing the merged baseline;
3. task-relevant canonical contracts;
4. generated OpenWiki orientation;
5. proposals, branch records, PR text, and chat history.

Accepted product/UI contracts may lead intended direction, but they do not prove implementation. When sources conflict, report the conflict instead of inventing a compatible answer. A filename containing “roadmap”, “phase”, or “status” is not proof that the work is current or merged.

## OpenWiki

`openwiki/INSTRUCTIONS.md` is the stable human-authored generation brief. `openwiki/quickstart.md` and other generated pages appear only after OpenWiki runs; do not hand-write them. Generated pages orient an agent and must link back to source/tests/contracts. They never become a product contract.

The preferred refresh cycle is: merge architectural work, update local `main`, generate OpenWiki in a dedicated documentation branch, review the generated diff for invented behavior, secrets, scope widening, obsolete Topic claims, and broken source links, then merge that documentation-only change.

## Maintenance rules

- Put durable product authority in a canonical contract, not a generated wiki or branch ledger.
- Prefer updating an existing contract over adding another status document.
- Keep old filenames when links depend on them; classify them in the historical index instead of silently presenting them as current.
- Never copy secrets, tokens, raw Discord captures, private payloads, or provider credentials into docs or OpenWiki.
- Application settings use `CHARACTER_RELAY_*`; `ECHO_MASQUE_LIVE_*` names are workflow secrets, not runtime configuration.
