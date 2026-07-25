.PHONY: install run lint format typecheck test check demo

install:
	python -m pip install -e ".[dev]"

run:
	python -m uvicorn echo_masque.main:app --reload

lint:
	python -m ruff check .

format:
	python -m ruff format .

typecheck:
	python -m mypy src

test:
	python -m pytest

check: lint typecheck test

demo:
	python -m echo_masque.cli run-demo --target fragile --suite all
