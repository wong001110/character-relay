"""Back up and copy a current Echo Masque SQLite database into PostgreSQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from echo_masque.persistence.sqlite_to_postgres_migration import migrate_sqlite_to_postgres


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True, help="Persistent SQLite SQLAlchemy URL.")
    parser.add_argument("--target-url", required=True, help="Empty PostgreSQL SQLAlchemy URL.")
    parser.add_argument(
        "--backup-directory",
        type=Path,
        help="Optional SQLite backup destination; defaults to the source directory.",
    )
    args = parser.parse_args()
    result = migrate_sqlite_to_postgres(
        args.source_url,
        args.target_url,
        backup_directory=args.backup_directory,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
