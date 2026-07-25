from echo_masque.cli import main


def test_info_command(capsys: object) -> None:
    assert main(["info"]) == 0


def test_stable_demo_returns_success(capsys: object) -> None:
    assert main(["run-demo", "--target", "stable", "--suite", "all"]) == 0
