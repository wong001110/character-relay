"""Deterministic retirement decisions for the pre-Fabric Knowledge stores."""

LEGACY_KNOWLEDGE_TABLES_TO_DROP = (
    "knowledge_wiki_pages",
    "knowledge_chunks",
    "knowledge_documents",
    "knowledge_bases",
    "knowledge_consolidation_checkpoints_v3",
    "server_wiki_pages_v3",
)
LEGACY_VECTOR_NAMESPACE = "knowledge-chunk"


def retired_knowledge_tables(existing_table_names: set[str]) -> tuple[str, ...]:
    """Return existing retired tables in foreign-key-safe deletion order."""

    return tuple(
        table_name
        for table_name in LEGACY_KNOWLEDGE_TABLES_TO_DROP
        if table_name in existing_table_names
    )


def has_legacy_knowledge_vectors(existing_table_names: set[str]) -> bool:
    """Only the shared semantic-vector table needs a namespace-scoped purge."""

    return "semantic_vectors" in existing_table_names


__all__ = [
    "LEGACY_KNOWLEDGE_TABLES_TO_DROP",
    "LEGACY_VECTOR_NAMESPACE",
    "has_legacy_knowledge_vectors",
    "retired_knowledge_tables",
]
