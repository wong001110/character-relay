from pathlib import Path

path = Path("src/echo_masque/persistence/deployment_repository.py")
text = path.read_text(encoding="utf-8")
old = '''            claimed_elsewhere = session.scalar(
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
'''
new = '''            if owner_id != catalog_owner_id:
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
'''
if old not in text:
    raise SystemExit("Super Admin claim exclusivity anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
