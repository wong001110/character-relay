# Architecture

## Design principles

1. Targets are replaceable through a small asynchronous protocol.
2. Trials are reproducible and record scenarios, turns, evidence, and verdicts.
3. Evidence precedes scores; failures must point to observable output.
4. Offline deterministic targets and judges are first-class components.
5. Secrets stay outside domain objects and serialized reports.
6. Observation is separated from execution.

## Runtime

```text
API or CLI
  -> trial runner
  -> scenario suite
  -> target adapter
  -> judge
  -> evidence, verdict, breakpoint
  -> persistence and observation UI
```
