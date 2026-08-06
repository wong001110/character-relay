from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Finalization anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    '''            claimed_elsewhere = session.scalar(
                select(DiscordServerProfileRecord.id)
                .where(
                    DiscordServerProfileRecord.connection_id == catalog.connection_id,
                    DiscordServerProfileRecord.guild_id == guild_id,
                    DiscordServerProfileRecord.owner_id.not_in(
                        (catalog_owner_id, owner_id)
                    ),
                )
                .limit(1)
            )
            if claimed_elsewhere is not None:
                raise DeploymentConflict(
                    "This Discord Server has already been claimed by another account."
                )
''',
    '''            if owner_id != catalog_owner_id:
                claimed_elsewhere = session.scalar(
                    select(DiscordServerProfileRecord.id)
                    .where(
                        DiscordServerProfileRecord.connection_id
                        == catalog.connection_id,
                        DiscordServerProfileRecord.guild_id == guild_id,
                        DiscordServerProfileRecord.owner_id.not_in(
                            (catalog_owner_id, owner_id)
                        ),
                    )
                    .limit(1)
                )
                if claimed_elsewhere is not None:
                    raise DeploymentConflict(
                        "This Discord Server has already been claimed by another account."
                    )
''',
)

replace_once(
    "web/src/DeploymentCenter.tsx",
    '''                      {item.external_account_id && <small>ID: {item.external_account_id}</small>}
                    </div>
''',
    '''                      {item.external_account_id && <small>ID: {item.external_account_id}</small>}
                      {item.metadata.shared_connection === true && (
                        <small>
                          {zh
                            ? "由 Super Admin 管理；当前账号只使用已认领 Server"
                            : "Managed by the Super Admin; this account only uses claimed Servers"}
                        </small>
                      )}
                    </div>
''',
)

replace_once(
    "web/src/DeploymentCenter.tsx",
    '''                    {!demoMode && (
                      <div className="connection-card-actions">
''',
    '''                    {!demoMode && item.metadata.shared_connection !== true && (
                      <div className="connection-card-actions">
''',
)
