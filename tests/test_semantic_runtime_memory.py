from __future__ import annotations

from echo_masque.semantic_participation import FastEmbedSemanticEncoder


class _FakeEmbeddingModel:
    embed_count = 0

    def embed(self, values: list[str]):
        del values
        type(self).embed_count += 1
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
    _FakeEmbeddingModel.embed_count = 0


def teardown_function() -> None:
    FastEmbedSemanticEncoder._reset_shared_models_for_test()
    _FakeFastEmbedEncoder.build_count = 0
    _FakeEmbeddingModel.embed_count = 0


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


def test_identical_query_vector_is_shared_across_encoder_wrappers() -> None:
    participation = _encoder()
    tool_retrieval = _encoder()
    knowledge = _encoder()
    expression = _encoder()

    expected = [1.0, 0.0, 0.0]
    assert participation.embed_query("generate a cat image") == expected
    assert tool_retrieval.embed_query("generate a cat image") == expected
    assert knowledge.embed_query("generate a cat image") == expected
    assert expression.embed_query("generate a cat image") == expected

    assert _FakeEmbeddingModel.embed_count == 1
    assert FastEmbedSemanticEncoder.query_cache_entry_count() == 1
    assert FastEmbedSemanticEncoder.query_cache_miss_count() == 1
    assert FastEmbedSemanticEncoder.query_cache_hit_count() == 3


def test_query_cache_is_scoped_by_model_configuration_and_text() -> None:
    first = _encoder(cache_dir="/tmp/shared-e5-a")
    same_config = _encoder(cache_dir="/tmp/shared-e5-a")
    other_config = _encoder(cache_dir="/tmp/shared-e5-b")

    first.embed_query("same message")
    same_config.embed_query("same message")
    first.embed_query("different message")
    other_config.embed_query("same message")

    assert _FakeEmbeddingModel.embed_count == 3
    assert FastEmbedSemanticEncoder.query_cache_entry_count() == 3
    assert FastEmbedSemanticEncoder.query_cache_hit_count() == 1
    assert FastEmbedSemanticEncoder.query_cache_miss_count() == 3


def test_passage_embeddings_do_not_use_query_cache() -> None:
    first = _encoder()
    second = _encoder()

    first.embed_query("same text")
    second.embed_query("same text")
    first.embed_passage("same text")

    assert _FakeEmbeddingModel.embed_count == 2
    assert FastEmbedSemanticEncoder.query_cache_hit_count() == 1
    assert FastEmbedSemanticEncoder.query_cache_miss_count() == 1
