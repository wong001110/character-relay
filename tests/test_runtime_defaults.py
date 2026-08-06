from echo_masque.admin_runtime import AdminRuntimeConfig
from echo_masque.authoring_runtime import AuthoringRuntimeConfig


def test_all_ai_runtimes_are_enabled_by_default() -> None:
    runtime = AdminRuntimeConfig()
    authoring = AuthoringRuntimeConfig()

    assert runtime.adaptive.enabled is True
    assert runtime.judge.enabled is True
    assert runtime.default_judge_mode == "hybrid"
    assert authoring.enabled is True
