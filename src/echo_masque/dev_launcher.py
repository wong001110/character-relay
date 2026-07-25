"""Cross-platform development launcher for the API and web client."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
import venv
from collections.abc import Sequence
from pathlib import Path

PYTHON_MARKER = ".echo-masque-python.sha256"
WEB_MARKER = ".echo-masque-web.sha256"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def dependency_fingerprint(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def marker_matches(marker: Path, fingerprint: str) -> bool:
    return marker.exists() and marker.read_text(encoding="utf-8").strip() == fingerprint


def write_marker(marker: Path, fingerprint: str) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(fingerprint, encoding="utf-8")


def run_checked(command: Sequence[str], *, cwd: Path) -> None:
    print(f"[echo-masque] {' '.join(command)}")
    subprocess.run(list(command), cwd=cwd, check=True)


def ensure_project_venv(root: Path) -> Path:
    venv_dir = root / ".venv"
    executable = venv_python(venv_dir)
    if not executable.exists():
        print("[echo-masque] Creating .venv...")
        venv.EnvBuilder(with_pip=True).create(venv_dir)
    return executable


def ensure_python_dependencies(root: Path, *, force: bool, skip: bool) -> None:
    if skip:
        return
    fingerprint = dependency_fingerprint([root / "pyproject.toml"])
    marker = root / ".venv" / PYTHON_MARKER
    if force or not marker_matches(marker, fingerprint):
        run_checked(
            [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
            cwd=root,
        )
        write_marker(marker, fingerprint)
    else:
        print("[echo-masque] Python dependencies unchanged; skipping install.")


def ensure_web_dependencies(root: Path, *, force: bool, skip: bool) -> str:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm was not found. Install Node.js 22 or newer and retry.")
    if skip:
        return npm
    web = root / "web"
    fingerprint = dependency_fingerprint([web / "package.json"])
    marker = web / "node_modules" / WEB_MARKER
    if force or not marker_matches(marker, fingerprint):
        run_checked([npm, "install"], cwd=web)
        write_marker(marker, fingerprint)
    else:
        print("[echo-masque] Web dependencies unchanged; skipping npm install.")
    return npm


def backend_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "echo_masque.main:app",
        "--host",
        args.api_host,
        "--port",
        str(args.api_port),
    ]
    if not args.no_reload:
        command.append("--reload")
    return command


def frontend_command(npm: str, args: argparse.Namespace) -> list[str]:
    return [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        args.web_host,
        "--port",
        str(args.web_port),
    ]


def stop_processes(processes: Sequence[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    for process in processes:
        if process.poll() is not None:
            continue
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()


def run_processes(root: Path, args: argparse.Namespace, npm: str | None) -> int:
    processes: list[subprocess.Popen[bytes]] = []
    try:
        backend = subprocess.Popen(backend_command(args), cwd=root)
        processes.append(backend)
        print(f"[echo-masque] API: http://{args.api_host}:{args.api_port}")

        if not args.api_only:
            assert npm is not None
            frontend = subprocess.Popen(frontend_command(npm, args), cwd=root / "web")
            processes.append(frontend)
            print(f"[echo-masque] UI:  http://{args.web_host}:{args.web_port}")

        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    return code
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n[echo-masque] Stopping development servers...")
        return 0
    finally:
        stop_processes(processes)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Start the Echo Masque development environment.")
    value.add_argument("--install", action="store_true", help="Force dependency installation.")
    value.add_argument("--no-install", action="store_true", help="Skip dependency installation.")
    value.add_argument("--api-only", action="store_true", help="Start only FastAPI.")
    value.add_argument("--no-reload", action="store_true", help="Disable Uvicorn reload.")
    value.add_argument("--api-host", default="127.0.0.1")
    value.add_argument("--api-port", type=int, default=8000)
    value.add_argument("--web-host", default="127.0.0.1")
    value.add_argument("--web-port", type=int, default=5173)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = project_root()
    project_venv = root / ".venv"
    current_is_project_venv = Path(sys.prefix).resolve() == project_venv.resolve()

    if not current_is_project_venv:
        executable = ensure_project_venv(root)
        command = [str(executable), str(root / "run.py"), *(argv or sys.argv[1:])]
        return subprocess.call(command, cwd=root)

    ensure_python_dependencies(root, force=args.install, skip=args.no_install)
    npm = None
    if not args.api_only:
        npm = ensure_web_dependencies(root, force=args.install, skip=args.no_install)
    return run_processes(root, args, npm)


if __name__ == "__main__":
    raise SystemExit(main())
