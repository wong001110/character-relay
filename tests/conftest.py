"""Regression tests use explicit provider doubles, never a resident embedding model.

The retired --live-embeddings switch is intentionally not retained. Live routing
qualification is an explicit external evaluation, not part of ordinary pytest.
"""
