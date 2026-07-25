# Contributing

Echo Masque is developed in numbered phases. A change should belong to one phase or a clearly scoped defect fix.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the API

```bash
make run
```

The OpenAPI document is available at `http://127.0.0.1:8000/docs`.

## Required checks

```bash
make check
```

This runs Ruff, mypy, and pytest. Model credentials must not be required by the default test suite and must never be committed.
