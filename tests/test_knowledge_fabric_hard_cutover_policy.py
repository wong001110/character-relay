from echo_masque.knowledge_fabric_hard_cutover_policy import (
    LEGACY_KNOWLEDGE_TABLES_TO_DROP,
    LEGACY_VECTOR_NAMESPACE,
    has_legacy_knowledge_vectors,
    retired_knowledge_tables,
)


def test_retired_knowledge_tables_are_exact_and_foreign_key_safe() -> None:
    existing = {
        "knowledge_bases",
        "knowledge_documents",
        "knowledge_chunks",
        "knowledge_wiki_pages",
        "knowledge_consolidation_checkpoints_v3",
        "server_wiki_pages_v3",
        "knowledge_corpora",
    }

    assert retired_knowledge_tables(existing) == LEGACY_KNOWLEDGE_TABLES_TO_DROP
    assert retired_knowledge_tables({"knowledge_corpora"}) == ()
    assert LEGACY_VECTOR_NAMESPACE == "knowledge-chunk"


def test_legacy_vector_purge_requires_the_shared_vector_table() -> None:
    assert has_legacy_knowledge_vectors({"semantic_vectors"})
    assert not has_legacy_knowledge_vectors({"knowledge_corpora"})
