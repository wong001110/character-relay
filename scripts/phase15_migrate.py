"""Back up and initialize an Echo Masque database for Phase 15 security tables."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from echo_masque.account_lifecycle import AccountLifecycleService, LifecycleConflict
from echo_masque.persistence import AuthRepository, Database


def run_migration(
    database_url: str,
    *,
    backup_directory: Path | None = None,
    claim_user_email: str | None = None,
) -> dict[str, object]:
    """Create a pre-migration backup, initialize missing tables, and optionally claim data."""

    url = make_url(database_url)
    backup_path: Path | None = None
    if url.get_backend_name() == "sqlite" and url.database not in {None, ":memory:"}:
        database_path = Path(str(url.database)).expanduser().resolve()
        if database_path.exists():
            destination = (backup_directory or database_path.parent).expanduser().resolve()
            destination.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            backup_path = destination / f"{database_path.name}.phase15-{timestamp}.bak"
            shutil.copy2(database_path, backup_path)

    database = Database(database_url)
    database.initialize()
    storage_instance_id = database.ensure_storage_instance_id()
    claimed: dict[str, int] | None = None
    if claim_user_email:
        auth_repository = AuthRepository(database)
        user = auth_repository.get_user_by_email(claim_user_email.casefold().strip())
        if user is None or not user.is_active:
            raise ValueError("The claim target must be an active Echo Masque account.")
        try:
            claimed = AccountLifecycleService(database, auth_repository).claim_local_workspace(
                actor_user_id=user.id
            )
        except LifecycleConflict as exc:
            if "No unclaimed" not in str(exc):
                raise
            claimed = {}

    return {
        "database_backend": url.get_backend_name(),
        "database_path": str(url.database) if url.database else None,
        "backup_path": str(backup_path) if backup_path else None,
        "storage_instance_id": storage_instance_id,
        "claimed": claimed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        required=True,
        help="SQLAlchemy database URL, for example sqlite:////data/echo_masque.db",
    )
    parser.add_argument(
        "--backup-directory",
        type=Path,
        help="Optional backup destination. Defaults to the database directory.",
    )
    parser.add_argument(
        "--claim-user-email",
        help="Optional active Admin account that should claim legacy local-user data.",
    )
    args = parser.parse_args()
    result = run_migration(
        args.database_url,
        backup_directory=args.backup_directory,
        claim_user_email=args.claim_user_email,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
