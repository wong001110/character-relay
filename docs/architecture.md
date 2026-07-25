# Architecture

## Design principles

1. **Targets are replaceable.** The trial engine depends on a small target protocol rather than a specific model provider.
2. **Trials are reproducible.** A saved run records the target configuration reference, suite version, scenario inputs, turns, evidence, and verdicts.
3. **Evidence precedes scores.** Every failed verdict must point to the response or trace data that caused it.
4. **Offline development remains possible.** Deterministic targets and judges are first-class components, not temporary mocks.
5. **Secrets stay outside domain objects.** Targets refer to credential locations; reports and traces never serialize secret values.
6. **Observation is separate from execution.** The API and future web client consume stable run records rather than coupling directly to model calls.

## Initial package boundaries

```text
src/echo_masque/
  api/          FastAPI application and HTTP routes
  domain/       Provider-independent types and validation rules
  config.py     Environment-derived application settings
  cli.py        Local developer entry point
  main.py       ASGI application object
```

Phase 2 adds `targets/`, `trials/`, `testers/`, and `judges/`. Persistence is deliberately postponed until Phase 4 so the trial contract can stabilize before database models are introduced.

## Runtime direction

```text
API or CLI
  -> trial service
  -> scenario/tester
  -> target adapter
  -> judge
  -> evidence and verdict
  -> run record
```

The trial service will own state transitions. Target adapters will not write directly to persistence, and judges will receive an immutable observation view rather than application services.
