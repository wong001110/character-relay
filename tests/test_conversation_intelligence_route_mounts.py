from echo_masque.api.routes import conversation_intelligence_router


def test_conversation_intelligence_subrouters_are_mounted() -> None:
    paths = {getattr(route, "path", "") for route in conversation_intelligence_router.routes}

    assert "/characters/{character_card_id}/core-memories" in paths
    assert "/core-memories/{memory_id}/revisions" in paths
    assert "/core-memory-revisions/{revision_id}/restore" in paths
    assert "/memories/{memory_id}/freshness" in paths
    assert "/characters/{character_card_id}/memory-summary" in paths
    assert "/characters/{character_card_id}/memory-summary/history" in paths
    assert "/characters/{character_card_id}/retrieval-preview" in paths
