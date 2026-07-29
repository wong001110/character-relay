from scripts.live_demo_seed_runner import select_modes


def test_selects_adaptive_hybrid_when_both_admin_runtimes_are_ready() -> None:
    tester, judge, note = select_modes(
        {
            "adaptive": {"configured": True},
            "judge": {"configured": True},
        }
    )
    assert tester == "adaptive"
    assert judge == "hybrid"
    assert "ready" in note.lower()


def test_falls_back_to_real_subject_benchmark_when_runtime_is_disabled() -> None:
    tester, judge, note = select_modes(
        {
            "adaptive": {"configured": False, "credential_source": "environment"},
            "judge": {"configured": False, "credential_source": "environment"},
        }
    )
    assert tester == "benchmark"
    assert judge == "rules"
    assert "not both enabled" in note.lower()
