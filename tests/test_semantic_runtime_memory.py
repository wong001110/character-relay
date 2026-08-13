from __future__ import annotations

from echo_masque.semantic_participation import FastEmbedSemanticEncoder


class _FakeEmbeddingModel:
    def embed(self, values: list[str]):
        del values
        yield [1.0, 0.0, 0.0]


class _FakeFastEmbedEncoder(FastEmbedSemanticEncoder):
    build_count = 0

    def _build_model(self) -> object:
        type(self).build_count += 1
        return _FakeEmbeddingModel()


def _encoder(*, cache_dir: str = "/tmp/shared-e5", model_name: str = "test/e5"):
    return _FakeFastEmbedEncoder(
        model_name=model_name,
        model_file="model.onnx",
        cache_dir=cache_dir,
        dimension=3,
    )


def setup_function() -> None:
    FastEmbedSemanticEncoder._reset_shared_models_for_test()
    _FakeFastEmbedEncoder.build_count = 0


def teardown_function() -> None:
    FastEmbedSemanticEncoder._reset_shared_models_for_test()
    _FakeFastEmbedEncoder.build_count = 0


def test_encoder_wrappers_share_one_heavy_runtime() -> None:
    participation = _encoder()
    knowledge = _encoder()
    expression = _encoder()
    media = _encoder()

    assert participation.model_loaded is False
    first_model = participation._load_model()

    assert knowledge._load_model() is first_model
    assert expression._load_model() is first_model
    assert media._load_model() is first_model
    assert participation.model_loaded is True
    assert knowledge.model_loaded is True
    assert _FakeFastEmbedEncoder.build_count == 1
    assert FastEmbedSemanticEncoder.shared_model_count() == 1
    assert FastEmbedSemanticEncoder.shared_load_count() == 1


def test_different_embedding_configuration_keeps_separate_runtime() -> None:
    first = _encoder(cache_dir="/tmp/shared-e5-a")
    second = _encoder(cache_dir="/tmp/shared-e5-b")

    assert first._load_model() is not second._load_model()
    assert _FakeFastEmbedEncoder.build_count == 2
    assert FastEmbedSemanticEncoder.shared_model_count() == 2


def test_embedding_calls_reuse_shared_runtime() -> None:
    first = _encoder()
    second = _encoder()

    assert first.embed_query("hello") == [1.0, 0.0, 0.0]
    assert second.embed_passage("world") == [1.0, 0.0, 0.0]
    assert _FakeFastEmbedEncoder.build_count == 1
