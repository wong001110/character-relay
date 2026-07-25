# Echo Masque

**See what remains when the role is challenged.**

Echo Masque is a Python-first behavior validation system for conversational characters and agents. It runs repeatable adversarial sessions, identifies the first behavioral breakpoint, and records evidence for identity drift, fabricated memory, prompt injection, capability violations, and long-conversation instability.

## Product loop

```text
Define target
  -> choose a test suite
  -> run an adversarial session
  -> judge each response
  -> locate the first breakpoint
  -> inspect evidence and replay
  -> change the prompt, model, memory, or policy
  -> rerun and compare
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest
python -m echo_masque.cli run-demo --target fragile --suite all
python -m uvicorn echo_masque.main:app --reload
```

Open `http://127.0.0.1:8000/docs` or call `GET /health`.

## Initial target types

1. **Deterministic demo** — credential-free Stable and Fragile characters.
2. **Prompt + model** — Echo Masque calls an OpenAI-compatible model.
3. **Custom HTTP target** — a complete external chatbot through an adapter contract.
4. **Transcript import** — inspect an existing conversation without sending new messages.

## Core test suites

- Identity integrity
- False-memory injection
- Prompt-injection resistance
- Long-conversation drift
- Capability boundaries
- Knowledge-boundary leakage
- Tool-behavior reliability

## Delivery phases

- [x] Phase 0 — Product contract and roadmap
- [x] Phase 1 — Python foundation
- [x] Phase 2 — Deterministic trial engine
- [x] Phase 3 — Prompt-model target
- [x] Phase 4 — Persistence and HTTP API
- [x] Phase 5 — Observation interface
- [x] Phase 6 — External target adapters
- [ ] Phase 7 — Comparison and hardening

See `CHECKLIST.md` for automated and manual acceptance items.

## MVP exclusions

The MVP excludes browser automation of third-party chat websites, public leaderboards, automatic prompt rewriting, fine-tuning, production traffic monitoring, and a general-purpose multi-agent simulation framework.
