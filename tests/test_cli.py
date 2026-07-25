from echo_masque.cli import main


def test_info_command(capsys: object) -> None:
    assert main(["info"]) == 0


def test_stable_demo_returns_success(capsys: object) -> None:
    assert main(["run-demo", "--target", "stable", "--suite", "all"]) == 0


def test_compare_results_command_enforces_gate(tmp_path) -> None:
    import asyncio

    from echo_masque.suites import scenarios_for
    from echo_masque.targets import fragile_target, stable_target
    from echo_masque.trials import TrialRunner

    async def build_results():
        runner = TrialRunner()
        return (
            await runner.run_suite(stable_target(), scenarios_for()),
            await runner.run_suite(fragile_target(), scenarios_for()),
        )

    stable, fragile = asyncio.run(build_results())
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(stable.model_dump_json())
    candidate.write_text(fragile.model_dump_json())
    assert main(["compare-results", str(baseline), str(candidate)]) == 3
