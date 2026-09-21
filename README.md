# Character Relay

A creator-oriented studio for building, testing, deploying and observing AI characters in group
chat. Echo Masque is the evaluation module within the product. Discord guild channels and Threads
are the supported platform surface; other connectors are not implied implementations.

## Project direction and implementation status

The accepted next direction is **bounded multi-character group conversation**, practical scoped
notes and relationships, optional recall, reliable Discord delivery and understandable diagnostics.
Perfect human cognition is not the goal. Zero bot participation is a valid outcome.

The [group-chat core plan](docs/plans/discord-group-chat-core.md) is accepted but **not implemented
by this documentation PR**. Existing runtime behavior is still the PR #205 baseline. The
[project state](PROJECT_STATE.md) separates that baseline, remaining work and verification.
Source movement and feature changes belong to the later Work implementation, not this PR.

## Existing product foundation

Character Cards, model/prompt configuration, portraits, deployments and webhook identities;
Smart Output and role orchestration; scoped internal recall; tools/media/jobs and delivery state;
provider/runtime diagnostics; and the Echo Masque evaluation/authoring/calibration surfaces exist.
Authentication, owner isolation, encrypted credentials, quotas and read-only Public Demo boundaries
remain. Advanced intelligence and Roast still exist at the baseline until explicitly retired.

Ordinary context no longer bulk-injects Beliefs, Episodes or Fabric evidence after PR #205, but
some automatic writers, social simulation and group-chat edge cases remain. Do not infer the whole
simplification is complete from the earlier merge or a short provider-visible relationship hint.

## Repository and development entry

| Need | Entry |
| --- | --- |
| AI-Native Development policy | [AGENTS.md](AGENTS.md) |
| Current status and Work takeover | [PROJECT_STATE.md](PROJECT_STATE.md) |
| Source ownership and target organization | [Architecture](docs/architecture.md) |
| Accepted behavior and acceptance cases | [Active group-chat plan](docs/plans/discord-group-chat-core.md) |
| Setup and validation commands | [Developer guide](docs/developer/README.md) |
| User / operator / specialized contracts | [Documentation index](docs/README.md) |

The Python API/runtime stays under `src/echo_masque/`, the Portal under `web/src/`, and the
Discord Connector under `connectors/discord/`. Tests and existing deployment infrastructure remain.
No generated wiki, fixed multi-agent topology or product-embedded coding-agent ledger is required.

## Local setup

Use the toolchain versions declared in the current Python and Node manifests. The existing launcher
prepares the environment and starts API/Portal:

```bash
python run.py
# Existing variants: --install, --no-install, --api-only, --no-reload
```

Local Portal: `http://127.0.0.1:5173`; API docs: `http://127.0.0.1:8000/docs`;
health: `http://127.0.0.1:8000/health`. See the developer guide for isolated PostgreSQL, connector,
focused checks and full surface validation. Model credentials are not required by ordinary tests.

## Production and authority

Runtime owns identity, permissions, source scope, tool authorization, lifecycle and delivery.
A model may propose a reply, silence or tool call; it cannot manufacture authority. Retired Topic
fallback/Topic-scoped memory is not reintroduced by this plan.

The existing production contract requires PostgreSQL + pgvector. SQLite is for local development,
tests or approved offline migration inputs, not production Fabric. Application settings use
`CHARACTER_RELAY_*`. Keep provider credentials, connector secrets and encryption keys outside Git.
Public Demo mutations remain denied server-side.

Read [deployment](docs/railway-deployment.md), [storage safety](docs/storage-safety.md) and
[security](docs/security.md) before rollout. A merge is not a production-health or security receipt.

## Documentation

[User guide](docs/user/README.md) · [Operator guide](docs/operator/README.md) ·
[Developer guide](docs/developer/README.md) · [Contracts](docs/contracts/README.md) ·
[Historical references](docs/history/README.md) · [Contributing](CONTRIBUTING.md)
