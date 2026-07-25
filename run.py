"""Single-command Echo Masque development launcher."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


if __name__ == "__main__":
    launcher = importlib.import_module("echo_masque.dev_launcher")
    raise SystemExit(launcher.main())
