from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = ROOT / "src" / "echo_masque"
ACTIVE_CONFIG_DOCS = (
    ROOT / ".env.example",
    ROOT / "Dockerfile",
    ROOT / "README.md",
    ROOT / "docs" / "langgraph-roadmap.md",
    ROOT / "docs" / "provider-tracing.md",
    ROOT / "docs" / "railway-deployment.md",
    ROOT / "docs" / "smart-participation-v3.md",
    ROOT / "docs" / "tool-calling-roadmap.md",
)
LEGACY_ENV_VAR = re.compile(r"\bECHO_MASQUE_[A-Z][A-Z0-9_]*\b")


def _legacy_prefix_hits(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if LEGACY_ENV_VAR.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    return hits


def test_runtime_source_uses_character_relay_environment_namespace() -> None:
    source_files = sorted(RUNTIME_SOURCE.rglob("*.py"))
    hits = _legacy_prefix_hits(source_files)
    assert hits == [], (
        "Legacy environment variable remains in runtime source:\n" + "\n".join(hits)
    )


def test_active_configuration_docs_use_character_relay_environment_namespace() -> None:
    hits = _legacy_prefix_hits(list(ACTIVE_CONFIG_DOCS))
    assert hits == [], (
        "Legacy environment variable remains in active config/docs:\n" + "\n".join(hits)
    )
