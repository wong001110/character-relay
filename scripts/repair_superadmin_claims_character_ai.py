from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Repair anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '''        raise HTTPException(
            status_code=403,
            detail="The managed Discord Bot is controlled by the Super Admin. Claim a Server by ID instead.",
        )
''',
    '''        raise HTTPException(
            status_code=403,
            detail=(
                "The managed Discord Bot is controlled by the Super Admin. "
                "Claim a Server by ID instead."
            ),
        )
''',
)

replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    '''            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None:
                raise KeyError("connection")

            profile: DiscordServerProfileRecord | None = None
            if server_profile_id:
                profile = session.get(DiscordServerProfileRecord, server_profile_id)
                if (
                    profile is None
                    or profile.owner_id != owner_id
                    or profile.connection_id != connection_id
                ):
                    raise KeyError("server profile")
            elif connection.owner_id != owner_id:
                raise KeyError("connection")
                if connection.platform != "discord":
                    raise DeploymentConflict(
                        "Discord server profiles can only be used with Discord connections."
                    )
                workspace_id = profile.guild_id
                workspace_name = profile.guild_name
                channel_id = f"@server:{profile.id}"
                channel_name = "All available channels"
                thread_id = ""
                thread_name = ""
            elif not channel_id or not channel_name:
                raise DeploymentConflict(
                    "A channel is required when no Discord server profile is selected."
                )
''',
    '''            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None:
                raise KeyError("connection")

            profile: DiscordServerProfileRecord | None = None
            if server_profile_id:
                profile = session.get(DiscordServerProfileRecord, server_profile_id)
                if (
                    profile is None
                    or profile.owner_id != owner_id
                    or profile.connection_id != connection_id
                ):
                    raise KeyError("server profile")
                if connection.platform != "discord":
                    raise DeploymentConflict(
                        "Discord server profiles can only be used with Discord connections."
                    )
                workspace_id = profile.guild_id
                workspace_name = profile.guild_name
                channel_id = f"@server:{profile.id}"
                channel_name = "All available channels"
                thread_id = ""
                thread_name = ""
            elif connection.owner_id != owner_id:
                raise KeyError("connection")
            elif not channel_id or not channel_name:
                raise DeploymentConflict(
                    "A channel is required when no Discord server profile is selected."
                )
''',
)
