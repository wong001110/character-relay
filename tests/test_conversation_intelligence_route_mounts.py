from echo_masque.api.routes.conversation_memory_control import (
    router as conversation_memory_control_router,
)
from echo_masque.api.routes.conversation_retrieval_observation import (
    router as conversation_retrieval_observation_router,
)


def test_conversation_intelligence_control_subrouters_expose_expected_routes() -> None:
    memory_paths = {
        getattr(route, "path", "") for route in conversation_memory_control_router.routes
    }
    retrieval_paths = {
        getattr(route, "path", "") for route in conversation_retrieval_observation_router.routes
    }

    assert "/characters/{character_card_id}/core-memories" in memory_paths
    assert "/core-memories/{memory_id}/revisions" in memory_paths
    assert "/core-memory-revisions/{revision_id}/restore" in memory_paths
    assert "/memories/{memory_id}/freshness" in memory_paths
    assert "/characters/{character_card_id}/memory-summary" in memory_paths
    assert "/characters/{character_card_id}/memory-summary/history" in memory_paths
    assert "/characters/{character_card_id}/retrieval-preview" in retrieval_paths
