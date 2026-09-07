"""Default regressions use injected encoders, never implicit model downloads/telemetry."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live-embeddings",
        action="store_true",
        default=False,
        help="Explicitly permit real embedding model initialization in an approved environment.",
    )


@pytest.fixture(autouse=True)
def isolated_embedding_runtime(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if request.config.getoption("--live-embeddings"):
        return
    from echo_masque.semantic_participation import (
        FastEmbedSemanticEncoder,
        SemanticEmbeddingUnavailable,
    )

    def offline_model(self: FastEmbedSemanticEncoder) -> object:
        raise SemanticEmbeddingUnavailable(
            "Real embeddings are disabled in regression tests; inject a deterministic encoder."
        )

    # Tests may override this method with a local fake. Default runtime paths exercise the
    # documented unavailable-embedding fallback rather than contact third-party telemetry/CDNs.
    monkeypatch.setattr(FastEmbedSemanticEncoder, "_build_model", offline_model)
