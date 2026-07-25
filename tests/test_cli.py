import json

from echo_masque.cli import main


def test_info_command_prints_non_secret_configuration(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(["info"])

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["name"] == "Echo Masque"
    assert output["version"] == "0.1.0"
