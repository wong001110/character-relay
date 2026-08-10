from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService


def test_enhanced_live_media_service_is_available() -> None:
    assert EnhancedLiveMediaContextService.__name__ == "EnhancedLiveMediaContextService"
