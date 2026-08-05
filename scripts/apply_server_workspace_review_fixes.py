from pathlib import Path


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected snippet not found in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


# Deployment form: Character remains selectable; Connection and Server are fixed by workspace.
replace(
    "web/src/DeploymentCenter.tsx",
    '                    disabled={Boolean(editingDeployment) || Boolean(selectedWorkspaceProfile)}\n',
    '                    disabled={Boolean(editingDeployment)}\n',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''                    disabled={Boolean(editingDeployment)}
                    required
                  >
                    {connections.map((item) => (
''',
    '''                    disabled={Boolean(editingDeployment) || Boolean(selectedWorkspaceProfile)}
                    required
                  >
                    {connections.map((item) => (
''',
)

# Server-scoped deployments are always Discord; remove the misleading platform filter.
replace(
    "web/src/DeploymentCenter.tsx",
    '  const [platformFilter, setPlatformFilter] = useState<"all" | PlatformId>("all");\n',
    "",
)
replace(
    "web/src/DeploymentCenter.tsx",
    '          platform: platformFilter,\n',
    '          platform: "discord",\n',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '  }, [characterFilter, platformFilter, selectedServerProfileId, statusFilter]);\n',
    '  }, [characterFilter, selectedServerProfileId, statusFilter]);\n',
)
replace(
    "web/src/DeploymentCenter.tsx",
    '''              <label>
                {zh ? "平台" : "Platform"}
                <select
                  value={platformFilter}
                  onChange={(event) =>
                    setPlatformFilter(event.currentTarget.value as "all" | PlatformId)
                  }
                >
                  <option value="all">{zh ? "全部平台" : "All platforms"}</option>
                  <option value="discord">Discord</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                </select>
              </label>
''',
    "",
)

# Summary cards describe the selected Server rather than global Server-profile count.
replace(
    "web/src/DeploymentCenter.tsx",
    '''        <article className="paper-sheet deployment-summary-card">
          <span>{zh ? "Server 配置" : "Server profiles"}</span>
          <strong>{serverProfiles.length}</strong>
          <small>{zh ? "可供多个角色复用" : "Reusable across characters"}</small>
        </article>
''',
    '''        <article className="paper-sheet deployment-summary-card">
          <span>{zh ? "同步 Channel" : "Synced Channels"}</span>
          <strong>{selectedWorkspaceCatalog?.channels.length ?? 0}</strong>
          <small>
            {selectedWorkspaceProfile
              ? selectedWorkspaceProfile.guild_name
              : zh
                ? "尚未选择 Server"
                : "No Server selected"}
          </small>
        </article>
''',
)

# Existing Server settings remain editable when its latest Connector catalog is unavailable.
replace(
    "web/src/DiscordServerProfilesPanel.tsx",
    '''    event.preventDefault();
    if (!selectedServer || !profileName.trim()) return;
    try {
''',
    '''    event.preventDefault();
    if (!profileName.trim() || (!editing && !selectedServer)) return;
    const guildName = selectedServer?.guild_name ?? editing?.guild_name ?? "";
    const serverGuildId = selectedServer?.guild_id ?? editing?.guild_id ?? "";
    try {
''',
)
replace(
    "web/src/DiscordServerProfilesPanel.tsx",
    '            guild_name: selectedServer.guild_name,\n',
    '            guild_name: guildName,\n',
    count=2,
)
replace(
    "web/src/DiscordServerProfilesPanel.tsx",
    '            guild_id: selectedServer.guild_id,\n',
    '            guild_id: serverGuildId,\n',
)
replace(
    "web/src/DiscordServerProfilesPanel.tsx",
    '                  <button className="ink-button" disabled={working || !selectedServer}>\n',
    '                  <button className="ink-button" disabled={working || (!editing && !selectedServer)}>\n',
)

# Use a real SQLAlchemy Session type and clean Server-scoped runtime data on deletion.
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    'from sqlalchemy import delete, select, update\n',
    'from sqlalchemy import delete, select, update\nfrom sqlalchemy.orm import Session\n',
)
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '''        session: object,
''',
    '''        session: Session,
''',
)
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '            character = session.get(CharacterCardRecord, character_card_id)  # type: ignore[attr-defined]\n',
    '            character = session.get(CharacterCardRecord, character_card_id)\n',
)
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '            deployment = session.scalar(  # type: ignore[attr-defined]\n',
    '            deployment = session.scalar(\n',
)

marker = '''    def delete_template(self, template_id: str, owner_id: str) -> bool:
'''
cleanup_methods = '''    def delete_server_scope(
        self,
        *,
        owner_id: str,
        server_profile_id: str,
        connection_id: str,
        guild_id: str,
    ) -> dict[str, int]:
        with self.database.session() as session:
            session_ids = list(
                session.scalars(
                    select(DiscordInteractionSessionRecord.id).where(
                        DiscordInteractionSessionRecord.owner_id == owner_id,
                        DiscordInteractionSessionRecord.connection_id == connection_id,
                        DiscordInteractionSessionRecord.guild_id == guild_id,
                    )
                )
            )
            run_count = 0
            if session_ids:
                result = session.execute(
                    delete(DiscordInteractionRunRecord).where(
                        DiscordInteractionRunRecord.session_id.in_(session_ids)
                    )
                )
                run_count = int(getattr(result, "rowcount", 0) or 0)
            session_result = session.execute(
                delete(DiscordInteractionSessionRecord).where(
                    DiscordInteractionSessionRecord.owner_id == owner_id,
                    DiscordInteractionSessionRecord.connection_id == connection_id,
                    DiscordInteractionSessionRecord.guild_id == guild_id,
                )
            )
            template_result = session.execute(
                delete(DiscordInteractionTemplateRecord).where(
                    DiscordInteractionTemplateRecord.owner_id == owner_id,
                    DiscordInteractionTemplateRecord.server_profile_id == server_profile_id,
                )
            )
            session.commit()
        return {
            "discord_interaction_runs": run_count,
            "discord_interaction_sessions": int(
                getattr(session_result, "rowcount", 0) or 0
            ),
            "discord_interaction_templates": int(
                getattr(template_result, "rowcount", 0) or 0
            ),
        }

    def delete_connection_scope(
        self,
        *,
        owner_id: str,
        connection_id: str,
        server_profile_ids: list[str],
    ) -> dict[str, int]:
        with self.database.session() as session:
            session_ids = list(
                session.scalars(
                    select(DiscordInteractionSessionRecord.id).where(
                        DiscordInteractionSessionRecord.owner_id == owner_id,
                        DiscordInteractionSessionRecord.connection_id == connection_id,
                    )
                )
            )
            run_count = 0
            if session_ids:
                result = session.execute(
                    delete(DiscordInteractionRunRecord).where(
                        DiscordInteractionRunRecord.session_id.in_(session_ids)
                    )
                )
                run_count = int(getattr(result, "rowcount", 0) or 0)
            session_result = session.execute(
                delete(DiscordInteractionSessionRecord).where(
                    DiscordInteractionSessionRecord.owner_id == owner_id,
                    DiscordInteractionSessionRecord.connection_id == connection_id,
                )
            )
            sticker_result = session.execute(
                delete(DiscordStickerSemanticRecord).where(
                    DiscordStickerSemanticRecord.owner_id == owner_id,
                    DiscordStickerSemanticRecord.connection_id == connection_id,
                )
            )
            template_count = 0
            if server_profile_ids:
                result = session.execute(
                    delete(DiscordInteractionTemplateRecord).where(
                        DiscordInteractionTemplateRecord.owner_id == owner_id,
                        DiscordInteractionTemplateRecord.server_profile_id.in_(
                            server_profile_ids
                        ),
                    )
                )
                template_count = int(getattr(result, "rowcount", 0) or 0)
            session.commit()
        return {
            "discord_interaction_runs": run_count,
            "discord_interaction_sessions": int(
                getattr(session_result, "rowcount", 0) or 0
            ),
            "discord_interaction_templates": template_count,
            "discord_sticker_semantics": int(
                getattr(sticker_result, "rowcount", 0) or 0
            ),
        }

'''
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    marker,
    cleanup_methods + marker,
)

# Deployment routes coordinate cleanup after a Server profile deletion and before Connection deletion.
replace(
    "src/echo_masque/api/routes/deployments.py",
    'from echo_masque.persistence import DeploymentConflict, DeploymentRepository, Repository\n',
    '''from echo_masque.persistence import (
    DeploymentConflict,
    DeploymentRepository,
    InteractionRepository,
    Repository,
)
''',
)
replace(
    "src/echo_masque/api/routes/deployments.py",
    '''def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


''',
    '''def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


''',
)
replace(
    "src/echo_masque/api/routes/deployments.py",
    '''def delete_connection(
    connection_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not deployment_repository(request).delete_connection(connection_id, user.id):
        raise HTTPException(status_code=404, detail="Platform connection not found.")
''',
    '''def delete_connection(
    connection_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    deployments = deployment_repository(request)
    connection = deployments.get_connection(connection_id, user.id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Platform connection not found.")
    profile_ids = [
        item.id
        for item in deployments.list_server_profiles(user.id)
        if item.connection_id == connection_id
    ]
    interaction_repository(request).delete_connection_scope(
        owner_id=user.id,
        connection_id=connection_id,
        server_profile_ids=profile_ids,
    )
    if not deployments.delete_connection(connection_id, user.id):
        raise HTTPException(status_code=404, detail="Platform connection not found.")
''',
)
replace(
    "src/echo_masque/api/routes/deployments.py",
    '''def delete_discord_server_profile(
    profile_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    try:
        deleted = deployment_repository(request).delete_server_profile(profile_id, user.id)
    except DeploymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
''',
    '''def delete_discord_server_profile(
    profile_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    deployments = deployment_repository(request)
    profile = deployments.get_server_profile(profile_id, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    try:
        deleted = deployments.delete_server_profile(profile_id, user.id)
    except DeploymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Discord server profile not found.")
    interaction_repository(request).delete_server_scope(
        owner_id=user.id,
        server_profile_id=profile.id,
        connection_id=profile.connection_id,
        guild_id=profile.guild_id,
    )
''',
)

# Add regression coverage for deletion lifecycle.
test_path = Path("tests/test_server_scoped_workspace.py")
test_text = test_path.read_text(encoding="utf-8")
test_text += '''

def test_server_profile_deletion_cleans_templates_and_sessions(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "server-cleanup.db")))
    _, profile, deployments = seed_server(client)
    template = client.post(
        "/api/interaction-templates",
        json={
            "server_profile_id": profile["id"],
            "name": "Disposable template",
            "participant_character_card_ids": [
                deployments[0]["character_card_id"],
                deployments[1]["character_card_id"],
            ],
            "rounds_per_trigger": 1,
            "maximum_triggers": 1,
            "cooldown_seconds": 0,
            "duration_seconds": 600,
            "intensity": "light",
        },
    )
    assert template.status_code == 201, template.text
    applied = client.post(
        f"/api/interaction-templates/{template.json()['id']}/apply",
        json={
            "channel_id": "channel-1",
            "target_user_id": "user-1",
            "target_display_name": "Target",
            "status": "paused",
        },
    )
    assert applied.status_code == 201, applied.text
    for deployment in deployments:
        deleted = client.delete(f"/api/deployments/{deployment['id']}")
        assert deleted.status_code == 204, deleted.text
    deleted_profile = client.delete(f"/api/discord/server-profiles/{profile['id']}")
    assert deleted_profile.status_code == 204, deleted_profile.text
    templates = client.get(
        "/api/interaction-templates",
        params={"server_profile_id": profile["id"]},
    )
    assert templates.status_code == 200
    assert templates.json() == []
    sessions = client.get("/api/interaction-sessions")
    assert sessions.status_code == 200
    assert sessions.json() == []
'''
test_path.write_text(test_text, encoding="utf-8")
