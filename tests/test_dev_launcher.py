import argparse
from pathlib import Path

from echo_masque.dev_launcher import (
    backend_command,
    dependency_fingerprint,
    frontend_command,
    marker_matches,
    venv_python,
    write_marker,
)


def arguments() -> argparse.Namespace:
    return argparse.Namespace(
        api_host="127.0.0.1",
        api_port=8000,
        web_host="127.0.0.1",
        web_port=5173,
        no_reload=False,
    )


def test_dependency_marker_changes_with_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "package.json"
    marker = tmp_path / "marker"
    manifest.write_text('{"version": 1}', encoding="utf-8")
    first = dependency_fingerprint([manifest])
    write_marker(marker, first)
    assert marker_matches(marker, first)

    manifest.write_text('{"version": 2}', encoding="utf-8")
    second = dependency_fingerprint([manifest])
    assert second != first
    assert not marker_matches(marker, second)


def test_launcher_commands_include_requested_ports() -> None:
    args = arguments()
    assert backend_command(args)[-4:] == ["127.0.0.1", "--port", "8000", "--reload"]
    assert frontend_command("npm", args)[-4:] == [
        "--host",
        "127.0.0.1",
        "--port",
        "5173",
    ]


def test_venv_python_is_platform_specific(tmp_path: Path) -> None:
    executable = venv_python(tmp_path / ".venv")
    assert executable.name in {"python", "python.exe"}
