from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "src/echo_masque/persistence/database.py"
SERVICE = ROOT / "src/echo_masque/character_learned_state.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_database() -> None:
    text = DATABASE.read_text(encoding="utf-8")
    import_line = (
        "from echo_masque.persistence.character_learned_state_models import "
        "CharacterLearnedStateRecord\n"
    )
    if import_line not in text:
        marker = "from echo_masque.persistence.models import Base, StorageMetadataRecord\n"
        if marker not in text:
            raise RuntimeError("Database model import marker changed")
        text = text.replace(marker, import_line + marker, 1)
    registration = "        _ = CharacterLearnedStateRecord\n"
    if registration not in text:
        text = replace_once(
            text,
            "        Base.metadata.create_all(self.engine)\n",
            registration + "        Base.metadata.create_all(self.engine)\n",
            "learned-state metadata registration",
        )
    DATABASE.write_text(text, encoding="utf-8")


def patch_service() -> None:
    text = SERVICE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from typing import Any, Literal\n",
        "from typing import Any, Literal, cast\n",
        "typing cast import",
    )
    text = replace_once(
        text,
        '            rowcount = getattr(result, "rowcount", 0)\n'
        '            return int(rowcount or 0) if isinstance(result, CursorResult) else 0\n',
        '            rowcount = cast(CursorResult[Any], result).rowcount or 0\n'
        '            return int(rowcount)\n',
        "cleanup rowcount typing",
    )
    SERVICE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_database()
    patch_service()
