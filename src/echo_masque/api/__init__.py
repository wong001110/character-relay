"""Lightweight API package exports.

Keep package import side effects minimal so low-level schemas can be imported without
eagerly loading the full FastAPI application, routes, and persistence graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from echo_masque.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    from echo_masque.api.app import create_app as _create_app

    return _create_app(settings)


__all__ = ["create_app"]
