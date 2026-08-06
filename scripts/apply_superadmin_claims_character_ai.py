from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:200]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Deployment schemas and shared Super Admin inventory endpoints.
# ---------------------------------------------------------------------------
replace_once(
    "src/echo_masque/api/deployment_schemas.py",
    '''class DiscordServerProfileCreate(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
''',
    '''class DiscordServerClaimCreate(BaseModel):
    guild_id: str = Field(min_length=5, max_length=200, pattern=r"^\\d+$")
    name: str = Field(default="", max_length=120)


class DiscordServerProfileCreate(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
''',
)

repo = Path("src/echo_masque/persistence/deployment_repository.py")
text = repo.read_text(encoding="utf-8")
anchor = '''    def create_server_profile(
        self,
        *,
        owner_id: str,
'''
methods = '''    def list_shared_connections_for_profiles(
        self,
        owner_id: str,
    ) -> list[PlatformConnectionRecord]:
        """Return managed Discord connections referenced by this owner's claims."""

        with self.database.session() as session:
            return list(
                session.scalars(
                    select(PlatformConnectionRecord)
                    .join(
                        DiscordServerProfileRecord,
                        DiscordServerProfileRecord.connection_id
                        == PlatformConnectionRecord.id,
                    )
                    .where(
                        DiscordServerProfileRecord.owner_id == owner_id,
                        PlatformConnectionRecord.owner_id != owner_id,
                        PlatformConnectionRecord.platform == "discord",
                    )
                    .distinct()
                    .order_by(PlatformConnectionRecord.created_at)
                )
            )

    def list_claimed_discord_server_catalog(
        self,
        owner_id: str,
    ) -> list[DiscordServerCatalogRecord]:
        """Return only catalog rows represented by this owner's Server Profiles."""

        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DiscordServerCatalogRecord)
                    .join(
                        DiscordServerProfileRecord,
                        (
                            DiscordServerProfileRecord.connection_id
                            == DiscordServerCatalogRecord.connection_id
                        )
                        & (
                            DiscordServerProfileRecord.guild_id
                            == DiscordServerCatalogRecord.guild_id
                        ),
                    )
                    .where(DiscordServerProfileRecord.owner_id == owner_id)
                    .distinct()
                    .order_by(
                        DiscordServerCatalogRecord.guild_name,
                        DiscordServerCatalogRecord.guild_id,
                    )
                )
            )

    def claim_server_profile(
        self,
        *,
        owner_id: str,
        catalog_owner_id: str,
        guild_id: str,
        name: str,
    ) -> DiscordServerProfileRecord:
        """Claim one exact Super Admin-managed Discord Server for an account."""

        with self.database.session() as session:
            catalog = session.scalar(
                select(DiscordServerCatalogRecord)
                .where(
                    DiscordServerCatalogRecord.owner_id == catalog_owner_id,
                    DiscordServerCatalogRecord.guild_id == guild_id,
                )
                .order_by(DiscordServerCatalogRecord.synced_at.desc())
                .limit(1)
            )
            if catalog is None:
                raise KeyError("server catalog")
            connection = session.get(PlatformConnectionRecord, catalog.connection_id)
            if (
                connection is None
                or connection.platform != "discord"
                or connection.owner_id != catalog_owner_id
            ):
                raise KeyError("connection")

            existing = session.scalar(
                select(DiscordServerProfileRecord).where(
                    DiscordServerProfileRecord.owner_id == owner_id,
                    DiscordServerProfileRecord.connection_id == catalog.connection_id,
                    DiscordServerProfileRecord.guild_id == guild_id,
                )
            )
            if existing is not None:
                raise DeploymentConflict(
                    "This Discord Server is already in your account."
                )

            claimed_elsewhere = session.scalar(
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

            record = DiscordServerProfileRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                connection_id=catalog.connection_id,
                name=name.strip() or catalog.guild_name,
                guild_id=catalog.guild_id,
                guild_name=catalog.guild_name,
                channel_scope_mode="all_except",
                excluded_channel_ids_json="[]",
                excluded_category_ids_json="[]",
                thread_policy="inherit_parent",
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DeploymentConflict(
                    "This Discord Server is already in your account."
                ) from exc
            session.refresh(record)
            return record

'''
if anchor not in text:
    raise SystemExit("Deployment repository server-profile anchor not found")
text = text.replace(anchor, methods + anchor, 1)

old_connection_check = '''            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None or connection.owner_id != owner_id:
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
'''
new_connection_check = '''            connection = session.get(PlatformConnectionRecord, connection_id)
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
'''
if old_connection_check not in text:
    raise SystemExit("Shared deployment connection anchor not found")
text = text.replace(old_connection_check, new_connection_check, 1)
repo.write_text(text, encoding="utf-8")

# Expression metadata is synchronized into every account that has claimed the Server.
replace_once(
    "src/echo_masque/persistence/expression_repository.py",
    '''from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)''',
    '''from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordServerProfileRecord,
    PlatformConnectionRecord,
)''',
)
expression_repo = Path("src/echo_masque/persistence/expression_repository.py")
text = expression_repo.read_text(encoding="utf-8")
old_sync = '''            connection = self._connection(session, connection_id)
            counts = {"emoji": 0, "sticker": 0}
            seen: dict[str, set[str]] = {"emoji": set(), "sticker": set()}
            for resource_type, items in (("emoji", emojis), ("sticker", stickers)):
                for item in items:
'''
new_sync = '''            connection = self._connection(session, connection_id)
            owner_ids = {
                connection.owner_id,
                *session.scalars(
                    select(DiscordServerProfileRecord.owner_id).where(
                        DiscordServerProfileRecord.connection_id == connection_id,
                        DiscordServerProfileRecord.guild_id == guild_id,
                    )
                ),
            }
            counts = {"emoji": 0, "sticker": 0}
            seen: dict[str, set[str]] = {"emoji": set(), "sticker": set()}
            for resource_type, items in (("emoji", emojis), ("sticker", stickers)):
                for item in items:
'''
if old_sync not in text:
    raise SystemExit("Expression sync start anchor not found")
text = text.replace(old_sync, new_sync, 1)
old_upsert = '''                    self._upsert_catalog_resource(
                        session,
                        owner_id=connection.owner_id,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        name=name,
                        description=str(item.get("description") or ""),
                        tags=tags,
                        format_type=str(item.get("format_type") or resource_type),
                        asset_url=str(item.get("asset_url") or ""),
                        animated=bool(item.get("animated", False)),
                        available=bool(item.get("available", True)),
                    )
'''
new_upsert = '''                    for owner_id in owner_ids:
                        self._upsert_catalog_resource(
                            session,
                            owner_id=owner_id,
                            connection_id=connection_id,
                            guild_id=guild_id,
                            resource_type=resource_type,
                            resource_id=resource_id,
                            name=name,
                            description=str(item.get("description") or ""),
                            tags=tags,
                            format_type=str(item.get("format_type") or resource_type),
                            asset_url=str(item.get("asset_url") or ""),
                            animated=bool(item.get("animated", False)),
                            available=bool(item.get("available", True)),
                        )
'''
if old_upsert not in text:
    raise SystemExit("Expression sync upsert anchor not found")
text = text.replace(old_upsert, new_upsert, 1)
old_unavailable = '''            for resource_type, resource_ids in seen.items():
                records = list(
                    session.scalars(
                        select(DiscordExpressionSemanticRecord).where(
                            DiscordExpressionSemanticRecord.owner_id == connection.owner_id,
                            DiscordExpressionSemanticRecord.connection_id == connection_id,
                            DiscordExpressionSemanticRecord.guild_id == guild_id,
                            DiscordExpressionSemanticRecord.resource_type == resource_type,
                        )
                    )
                )
                for record in records:
                    if record.resource_id not in resource_ids:
                        record.available = False
'''
new_unavailable = '''            for owner_id in owner_ids:
                for resource_type, resource_ids in seen.items():
                    records = list(
                        session.scalars(
                            select(DiscordExpressionSemanticRecord).where(
                                DiscordExpressionSemanticRecord.owner_id == owner_id,
                                DiscordExpressionSemanticRecord.connection_id == connection_id,
                                DiscordExpressionSemanticRecord.guild_id == guild_id,
                                DiscordExpressionSemanticRecord.resource_type == resource_type,
                            )
                        )
                    )
                    for record in records:
                        if record.resource_id not in resource_ids:
                            record.available = False
'''
if old_unavailable not in text:
    raise SystemExit("Expression unavailable anchor not found")
text = text.replace(old_unavailable, new_unavailable, 1)
old_manual_auth = '''            connection = self._connection(session, connection_id)
            if connection.owner_id != owner_id:
                raise KeyError("connection")
            record = self._upsert_catalog_resource(
'''
new_manual_auth = '''            connection = self._connection(session, connection_id)
            if connection.owner_id != owner_id:
                claim = session.scalar(
                    select(DiscordServerProfileRecord.id).where(
                        DiscordServerProfileRecord.owner_id == owner_id,
                        DiscordServerProfileRecord.connection_id == connection_id,
                        DiscordServerProfileRecord.guild_id == guild_id,
                    )
                )
                if claim is None:
                    raise KeyError("connection")
            record = self._upsert_catalog_resource(
'''
if old_manual_auth not in text:
    raise SystemExit("Expression manual authorization anchor not found")
text = text.replace(old_manual_auth, new_manual_auth, 1)

clone_anchor = '''    def list_resources(
        self,
        owner_id: str,
'''
clone_method = '''    def clone_server_resources(
        self,
        *,
        source_owner_id: str,
        target_owner_id: str,
        connection_id: str,
        guild_id: str,
    ) -> int:
        """Seed one new claim with the current canonical resource metadata."""

        with self.database.session() as session:
            source = list(
                session.scalars(
                    select(DiscordExpressionSemanticRecord).where(
                        DiscordExpressionSemanticRecord.owner_id == source_owner_id,
                        DiscordExpressionSemanticRecord.connection_id == connection_id,
                        DiscordExpressionSemanticRecord.guild_id == guild_id,
                    )
                )
            )
            created = 0
            for item in source:
                existing = session.scalar(
                    select(DiscordExpressionSemanticRecord.id).where(
                        DiscordExpressionSemanticRecord.owner_id == target_owner_id,
                        DiscordExpressionSemanticRecord.connection_id == connection_id,
                        DiscordExpressionSemanticRecord.guild_id == guild_id,
                        DiscordExpressionSemanticRecord.resource_type == item.resource_type,
                        DiscordExpressionSemanticRecord.resource_id == item.resource_id,
                    )
                )
                if existing is not None:
                    continue
                session.add(
                    DiscordExpressionSemanticRecord(
                        id=str(uuid4()),
                        owner_id=target_owner_id,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        resource_type=item.resource_type,
                        resource_id=item.resource_id,
                        name=item.name,
                        description=item.description,
                        tags_json=item.tags_json,
                        format_type=item.format_type,
                        asset_url=item.asset_url,
                        animated=item.animated,
                        available=item.available,
                        enabled=item.enabled,
                        semantic_intent=item.semantic_intent,
                        semantic_emotion=item.semantic_emotion,
                        semantic_description=item.semantic_description,
                        aliases_json=item.aliases_json,
                        situations_json=item.situations_json,
                        avoid_when_json=item.avoid_when_json,
                        allowed_actions_json=item.allowed_actions_json,
                        semantic_source=item.semantic_source,
                        semantic_confidence=item.semantic_confidence,
                        last_seen_at=item.last_seen_at,
                    )
                )
                created += 1
            session.commit()
            return created

'''
if clone_anchor not in text:
    raise SystemExit("Expression clone anchor not found")
text = text.replace(clone_anchor, clone_method + clone_anchor, 1)
expression_repo.write_text(text, encoding="utf-8")

# Centralize managed inventory at startup after the Bootstrap Super Admin is resolved.
replace_once(
    "src/echo_masque/api/__init__.py",
    '''from echo_masque.credentials import CredentialVault
''',
    '''from echo_masque.credentials import CredentialVault
from echo_masque.discord_inventory import DiscordInventoryService
''',
)
replace_once(
    "src/echo_masque/api/__init__.py",
    '''    auth_service.ensure_development_user()
    auth_service.ensure_system_runtime_user()
    auth_service.ensure_bootstrap_admin()

    repository = Repository(database)
''',
    '''    auth_service.ensure_development_user()
    auth_service.ensure_system_runtime_user()
    bootstrap_admin = auth_service.ensure_bootstrap_admin()

    repository = Repository(database)
''',
)
replace_once(
    "src/echo_masque/api/__init__.py",
    '''    expression_repository = ExpressionRepository(database)
    provider_trace_repository = ProviderTraceRepository(
''',
    '''    expression_repository = ExpressionRepository(database)
    if bootstrap_admin is not None:
        centralized = DiscordInventoryService(database).centralize(bootstrap_admin.id)
        if any(centralized.values()):
            logger.info("Centralized Discord inventory: %s", centralized)
    provider_trace_repository = ProviderTraceRepository(
''',
)

# Deployment HTTP layer: Super Admin catalog, exact Server ID claims, shared connections.
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '''from echo_masque.api.dependencies import CurrentUserDependency
''',
    '''from echo_masque.api.dependencies import CurrentUserDependency, is_super_admin
''',
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '''    DiscordServerCatalogView,
    DiscordServerProfileCreate,
''',
    '''    DiscordServerCatalogView,
    DiscordServerClaimCreate,
    DiscordServerProfileCreate,
''',
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '''    DeploymentRepository,
    InteractionRepository,
    Repository,
)''',
    '''    AuthRepository,
    DeploymentRepository,
    ExpressionRepository,
    InteractionRepository,
    Repository,
)''',
)

helpers_anchor = '''def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


'''
helpers = '''def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


def expression_repository(request: Request) -> ExpressionRepository:
    return cast(ExpressionRepository, request.app.state.expression_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def super_admin_id(request: Request) -> str:
    email = request.app.state.settings.bootstrap_admin_email
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bootstrap Super Admin is not configured.",
        )
    record = auth_repository(request).get_user_by_email(email.casefold().strip())
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bootstrap Super Admin is not available.",
        )
    return record.id


'''
replace_once("src/echo_masque/api/routes/deployments.py", helpers_anchor, helpers)

old_list_connections = '''    return [
        PlatformConnectionView.from_record(item)
        for item in deployment_repository(request).list_connections(user.id)
    ]
'''
new_list_connections = '''    repo = deployment_repository(request)
    own = repo.list_connections(user.id)
    shared = repo.list_shared_connections_for_profiles(user.id)
    views = [PlatformConnectionView.from_record(item) for item in own]
    known = {item.id for item in own}
    for item in shared:
        if item.id in known:
            continue
        view = PlatformConnectionView.from_record(item)
        view.display_name = "Character Relay Discord Bot"
        view.external_account_id = ""
        view.metadata = {
            "shared_connection": True,
            "connector_display_name": "Character Relay Discord Bot",
        }
        views.append(view)
    return views
'''
replace_once("src/echo_masque/api/routes/deployments.py", old_list_connections, new_list_connections)

replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '''def create_connection(
    payload: PlatformConnectionCreate,
    request: Request,
    user: CurrentUserDependency,
) -> PlatformConnectionView:
    record = deployment_repository(request).create_connection(
''',
    '''def create_connection(
    payload: PlatformConnectionCreate,
    request: Request,
    user: CurrentUserDependency,
) -> PlatformConnectionView:
    if payload.platform == "discord" and not is_super_admin(user, request.app.state.settings):
        raise HTTPException(
            status_code=403,
            detail="The managed Discord Bot is controlled by the Super Admin. Claim a Server by ID instead.",
        )
    record = deployment_repository(request).create_connection(
''',
)

old_catalog = '''    return [
        DiscordServerCatalogView.from_record(item)
        for item in deployment_repository(request).list_discord_server_catalog(
            user.id,
            connection_id=connection_id,
        )
    ]
'''
new_catalog = '''    repo = deployment_repository(request)
    if is_super_admin(user, request.app.state.settings):
        records = repo.list_discord_server_catalog(
            super_admin_id(request),
            connection_id=connection_id,
        )
    else:
        records = repo.list_claimed_discord_server_catalog(user.id)
        if connection_id is not None:
            records = [item for item in records if item.connection_id == connection_id]
    return [DiscordServerCatalogView.from_record(item) for item in records]
'''
replace_once("src/echo_masque/api/routes/deployments.py", old_catalog, new_catalog)

claim_anchor = '''@router.post(
    "/discord/server-profiles",
    response_model=DiscordServerProfileView,
'''
claim_endpoint = '''@router.post(
    "/discord/server-profiles/claim",
    response_model=DiscordServerProfileView,
    status_code=status.HTTP_201_CREATED,
)
def claim_discord_server_profile(
    payload: DiscordServerClaimCreate,
    request: Request,
    user: CurrentUserDependency,
) -> DiscordServerProfileView:
    catalog_owner_id = super_admin_id(request)
    try:
        record = deployment_repository(request).claim_server_profile(
            owner_id=user.id,
            catalog_owner_id=catalog_owner_id,
            guild_id=payload.guild_id.strip(),
            name=payload.name,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                "Server ID was not found. Add the Character Relay Bot to that Discord "
                "Server and wait for the next catalog sync before trying again."
            ),
        ) from exc
    except DeploymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    expression_repository(request).clone_server_resources(
        source_owner_id=catalog_owner_id,
        target_owner_id=user.id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
    )
    return DiscordServerProfileView.from_record(record)


'''
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    claim_anchor,
    claim_endpoint + claim_anchor,
)

replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '''    records, safe_page, total, pages = repo.list_discord_events(
        user.id,
''',
    '''    event_owner_id = user.id
    if resolved_connection_id is not None:
        connection = repo.get_connection(resolved_connection_id, user.id)
        if connection is None:
            shared = {
                item.id: item for item in repo.list_shared_connections_for_profiles(user.id)
            }
            connection = shared.get(resolved_connection_id)
        if connection is not None:
            event_owner_id = connection.owner_id

    records, safe_page, total, pages = repo.list_discord_events(
        event_owner_id,
''',
)

# ---------------------------------------------------------------------------
# Character Card AI drafting API.
# ---------------------------------------------------------------------------
replace_once(
    "src/echo_masque/api/routes/characters.py",
    '''from echo_masque.character_prompts import CharacterPromptProfile
''',
    '''from echo_masque.character_assistant import (
    CharacterAssistantService,
    CharacterAssistantUnavailable,
    CharacterSuggestionRequest,
    CharacterSuggestionResult,
)
from echo_masque.character_prompts import CharacterPromptProfile
''',
)
replace_once(
    "src/echo_masque/api/routes/characters.py",
    '''from echo_masque.security_controls import QuotaExceeded
''',
    '''from echo_masque.providers import ProviderError
from echo_masque.security_controls import QuotaExceeded
''',
)
character_endpoint_anchor = '''@router.post("", response_model=CharacterCardView, status_code=status.HTTP_201_CREATED)
def create_character(
'''
character_endpoint = '''@router.post("/suggest", response_model=CharacterSuggestionResult)
async def suggest_character_card(
    payload: CharacterSuggestionRequest,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterSuggestionResult:
    try:
        quota_service(request).consume_authoring_generation(user.id)
        return await CharacterAssistantService(
            request.app.state.authoring_runtime_service
        ).suggest(payload)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except CharacterAssistantUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


'''
replace_once(
    "src/echo_masque/api/routes/characters.py",
    character_endpoint_anchor,
    character_endpoint + character_endpoint_anchor,
)

# ---------------------------------------------------------------------------
# Portal API types and exact Server ID claim action.
# ---------------------------------------------------------------------------
replace_once(
    "web/src/deploymentApi.ts",
    '''export interface DiscordServerProfileCreate {
  connection_id: string;
''',
    '''export interface DiscordServerClaimCreate {
  guild_id: string;
  name: string;
}

export interface DiscordServerProfileCreate {
  connection_id: string;
''',
)
replace_once(
    "web/src/deploymentApi.ts",
    '''  createDiscordServerProfile: (payload: DiscordServerProfileCreate) =>
    request<DiscordServerProfile>("/api/discord/server-profiles", {
''',
    '''  claimDiscordServerProfile: (payload: DiscordServerClaimCreate) =>
    request<DiscordServerProfile>("/api/discord/server-profiles/claim", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createDiscordServerProfile: (payload: DiscordServerProfileCreate) =>
    request<DiscordServerProfile>("/api/discord/server-profiles", {
''',
)

replace_once(
    "web/src/api.ts",
    '''export interface CredentialStatus {
''',
    '''export interface CharacterSuggestionRequest {
  concept: string;
  name_hint: string;
  relationship_context: string;
  writing_constraints: string;
  subject_type_hint: CharacterCard["subject_type"];
  language: "en" | "zh-CN";
}

export interface CharacterSuggestionResult {
  display_name: string;
  subtitle: string;
  subject_type: CharacterCard["subject_type"];
  persona_summary: string;
  traits: string[];
  tags: string[];
  expected_tone: string;
  forbidden_behaviors: string[];
  memory_summary: string;
  system_prompt: string;
  provider_model: string;
  correction_used: boolean;
}

export interface CredentialStatus {
''',
)
replace_once(
    "web/src/api.ts",
    '''  listCharacters: () => request<CharacterCard[]>("/api/characters"),
  createCharacter: (payload: CharacterCardCreate) =>
''',
    '''  listCharacters: () => request<CharacterCard[]>("/api/characters"),
  suggestCharacter: (payload: CharacterSuggestionRequest) =>
    request<CharacterSuggestionResult>("/api/characters/suggest", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createCharacter: (payload: CharacterCardCreate) =>
''',
)

# ---------------------------------------------------------------------------
# Server Profile UI: claim by exact Discord Server ID instead of global list.
# ---------------------------------------------------------------------------
server_panel = Path("web/src/DiscordServerProfilesPanel.tsx")
text = server_panel.read_text(encoding="utf-8")
text = text.replace(
    '  const [connectionId, setConnectionId] = useState(discordConnections[0]?.id ?? "");\n',
    '  const [connectionId, setConnectionId] = useState(discordConnections[0]?.id ?? "");\n'
    '  const [claimGuildId, setClaimGuildId] = useState("");\n',
    1,
)
text = text.replace(
    '''    setGuildId(nextServer?.guild_id ?? "");
    setProfileName(nextServer?.guild_name ?? "");
''',
    '''    setGuildId(nextServer?.guild_id ?? "");
    setClaimGuildId("");
    setProfileName("");
''',
    1,
)
old_save_guard = '''    if (!profileName.trim() || (!editing && !selectedServer)) return;
    const guildName = selectedServer?.guild_name ?? editing?.guild_name ?? "";
    const serverGuildId = selectedServer?.guild_id ?? editing?.guild_id ?? "";
'''
new_save_guard = '''    if (editing && !profileName.trim()) return;
    if (!editing && !claimGuildId.trim()) return;
    const guildName = selectedServer?.guild_name ?? editing?.guild_name ?? "";
    const serverGuildId = selectedServer?.guild_id ?? editing?.guild_id ?? "";
'''
if old_save_guard not in text:
    raise SystemExit("Server claim save guard anchor not found")
text = text.replace(old_save_guard, new_save_guard, 1)
old_create_call = '''        : await deploymentApi.createDiscordServerProfile({
            connection_id: connectionId,
            name: profileName.trim(),
            guild_id: serverGuildId,
            guild_name: guildName,
            excluded_channel_ids: [...excludedChannels],
            excluded_category_ids: [...excludedCategories],
            thread_policy: "inherit_parent"
          });
'''
new_create_call = '''        : await deploymentApi.claimDiscordServerProfile({
            guild_id: claimGuildId.trim(),
            name: profileName.trim()
          });
'''
if old_create_call not in text:
    raise SystemExit("Server claim create anchor not found")
text = text.replace(old_create_call, new_create_call, 1)
text = text.replace(
    '''                onClick={openNew}
                disabled={!discordConnections.length || !catalog.length}
''',
    '''                onClick={openNew}
''',
    1,
)
text = text.replace(
    '''                      ? "选择 Connector 已同步的 Server，不需要手动填写 Server ID。"
                      : "Choose a Server already synchronized by the Connector; no manual Server ID is required."}
''',
    '''                      ? "先把 Character Relay Bot 加入 Discord Server，再输入该 Server ID 认领到当前账号。"
                      : "Add the Character Relay Bot to Discord first, then enter the Server ID to claim it for this account."}
''',
    1,
)
old_new_fields = '''                ) : (
                  <>
                    <label>
                      {zh ? "Discord Connector" : "Discord Connector"}
                      <select
                        value={connectionId}
                        onChange={(event) => changeConnection(event.currentTarget.value)}
                        required
                      >
                        {discordConnections.map((connection) => (
                          <option key={connection.id} value={connection.id}>
                            {connection.display_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {zh ? "已同步 Server" : "Synchronized Server"}
                      <select
                        value={guildId}
                        onChange={(event) => changeGuild(event.currentTarget.value)}
                        required
                      >
                        {availableServers.map((server) => (
                          <option key={server.guild_id} value={server.guild_id}>
                            {server.guild_name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </>
                )}
'''
new_new_fields = '''                ) : (
                  <>
                    <label className="drawer-form-wide">
                      {zh ? "Discord Server ID" : "Discord Server ID"}
                      <input
                        value={claimGuildId}
                        onChange={(event) =>
                          setClaimGuildId(event.currentTarget.value.replace(/\\D+/gu, ""))
                        }
                        required
                        inputMode="numeric"
                        pattern="[0-9]+"
                        maxLength={200}
                        placeholder="123456789012345678"
                      />
                      <small>
                        {zh
                          ? "只会精确查找这个 ID。其他账号无法看到 Super Admin 的完整 Server 清单。"
                          : "Only this exact ID is checked. Other accounts cannot browse the Super Admin Server catalog."}
                      </small>
                    </label>
                  </>
                )}
'''
if old_new_fields not in text:
    raise SystemExit("Server claim form fields anchor not found")
text = text.replace(old_new_fields, new_new_fields, 1)
text = text.replace(
    '''                  required
                  maxLength={120}
                  placeholder={zh ? "例如：私人 Companion Server" : "e.g. Private companion server"}
''',
    '''                  required={Boolean(editing)}
                  maxLength={120}
                  placeholder={zh ? "可选；留空时使用 Discord Server 名称" : "Optional; defaults to the Discord Server name"}
''',
    1,
)
server_panel.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Character Creator: AI draft panel and stronger mode tabs.
# ---------------------------------------------------------------------------
creator = Path("web/src/CharacterCreator.tsx")
text = creator.read_text(encoding="utf-8")
text = text.replace(
    'import { useMemo, useState, type FormEvent } from "react";\n',
    'import { useMemo, useRef, useState, type FormEvent } from "react";\n',
    1,
)
text = text.replace(
    '''  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
''',
    '''  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(!editing);
  const [assistantBrief, setAssistantBrief] = useState("");
  const [assistantRelationship, setAssistantRelationship] = useState("");
  const [assistantConstraints, setAssistantConstraints] = useState("");
  const [assistantWorking, setAssistantWorking] = useState(false);
  const [assistantMessage, setAssistantMessage] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);
''',
    1,
)
function_anchor = '''  function changeProvider(nextProvider: ProviderId) {
'''
functions = '''  function setFormValue(name: string, value: string) {
    const element = formRef.current?.elements.namedItem(name);
    if (
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement ||
      element instanceof HTMLSelectElement
    ) {
      element.value = value;
    }
  }

  async function generateCharacterDraft() {
    const concept = assistantBrief.trim();
    if (concept.length < 10) {
      setAssistantMessage(
        zh ? "先用至少十个字描述角色定位与核心想法。" : "Describe the character concept in at least ten characters."
      );
      return;
    }
    try {
      setAssistantWorking(true);
      setAssistantMessage(null);
      const suggestion = await api.suggestCharacter({
        concept,
        name_hint: String(
          (formRef.current?.elements.namedItem("display_name") as HTMLInputElement | null)
            ?.value ?? ""
        ),
        relationship_context: assistantRelationship.trim(),
        writing_constraints: assistantConstraints.trim(),
        subject_type_hint: String(
          (formRef.current?.elements.namedItem("subject_type") as HTMLSelectElement | null)
            ?.value ?? "custom"
        ) as CharacterCard["subject_type"],
        language: zh ? "zh-CN" : "en"
      });
      setFormValue("display_name", suggestion.display_name);
      setFormValue("subtitle", suggestion.subtitle);
      setFormValue("subject_type", suggestion.subject_type);
      setFormValue("persona_summary", suggestion.persona_summary);
      setFormValue("traits", suggestion.traits.join("\\n"));
      setFormValue("tags", suggestion.tags.join("\\n"));
      setFormValue("expected_tone", suggestion.expected_tone);
      setFormValue("forbidden_behaviors", suggestion.forbidden_behaviors.join("\\n"));
      setFormValue("memory_summary", suggestion.memory_summary);
      if (promptFields) setFormValue("system_prompt", suggestion.system_prompt);
      setAssistantMessage(
        zh
          ? `已使用 ${suggestion.provider_model} 填入角色草稿。请逐区审核后再保存。`
          : `Drafted with ${suggestion.provider_model}. Review every section before saving.`
      );
    } catch (reason) {
      setAssistantMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setAssistantWorking(false);
    }
  }

'''
if function_anchor not in text:
    raise SystemExit("Character assistant function anchor not found")
text = text.replace(function_anchor, functions + function_anchor, 1)
text = text.replace(
    '<form className="notebook-form-paper" onSubmit={submit}>',
    '<form ref={formRef} className="notebook-form-paper" onSubmit={submit}>',
    1,
)
intro_end = '''        </header>

        {!editing && (
'''
assistant_markup = '''        </header>

        <section className={`character-ai-drafter${assistantOpen ? " is-open" : ""}`}>
          <button
            className="character-ai-drafter-toggle"
            type="button"
            onClick={() => setAssistantOpen((current) => !current)}
            aria-expanded={assistantOpen}
          >
            <span className="toolbox-sticker sticker-lavender">AI DRAFT</span>
            <span>
              <strong>{zh ? "让 AI 帮你起草角色卡" : "Draft the Character Card with AI"}</strong>
              <small>
                {zh
                  ? "描述一次，回填 Persona、Traits、Tone、边界、记忆与 System Prompt。"
                  : "Describe once, then review Persona, Traits, Tone, boundaries, memory, and System Prompt."}
              </small>
            </span>
            <b aria-hidden="true">{assistantOpen ? "−" : "+"}</b>
          </button>
          {assistantOpen && (
            <div className="character-ai-drafter-body">
              <NotebookField
                className="is-wide"
                label={zh ? "角色概念与核心定位" : "Character concept and core positioning"}
                guide={zh ? "写身份、性格方向、主要关系、世界观或用途。" : "Describe identity, personality direction, relationships, world, or purpose."}
                required
              >
                <NotebookTextarea
                  rows={5}
                  value={assistantBrief}
                  onChange={(event) => setAssistantBrief(event.currentTarget.value)}
                  placeholder={
                    zh
                      ? "例如：一位擅长把混乱需求整理成产品路线图的 AI 产品制作人，务实、好奇，但容易同时开太多项目。"
                      : "Example: an AI product producer who turns vague ideas into executable roadmaps; practical and curious, but prone to starting too many projects."
                  }
                />
              </NotebookField>
              <NotebookField label={zh ? "关系与互动背景" : "Relationship and interaction context"}>
                <NotebookTextarea
                  rows={3}
                  value={assistantRelationship}
                  onChange={(event) => setAssistantRelationship(event.currentTarget.value)}
                  placeholder={zh ? "角色与用户或其他角色是什么关系？" : "How does the character relate to the user or other characters?"}
                />
              </NotebookField>
              <NotebookField label={zh ? "额外限制" : "Additional constraints"}>
                <NotebookTextarea
                  rows={3}
                  value={assistantConstraints}
                  onChange={(event) => setAssistantConstraints(event.currentTarget.value)}
                  placeholder={zh ? "不要使用的语气、必须保留的设定、语言偏好等。" : "Voice to avoid, required canon, language preferences, and other constraints."}
                />
              </NotebookField>
              <div className="character-ai-drafter-actions">
                <button
                  className="ink-button"
                  type="button"
                  onClick={() => void generateCharacterDraft()}
                  disabled={assistantWorking || saving}
                >
                  {assistantWorking
                    ? zh
                      ? "生成中…"
                      : "Generating…"
                    : zh
                      ? "生成并填入草稿"
                      : "Generate and fill draft"}
                </button>
                <small>
                  {zh
                    ? "AI 不会自动保存，也不会改动 API Key 或 Provider 设置。"
                    : "AI never saves automatically and does not change Provider credentials."}
                </small>
              </div>
              {assistantMessage && <p className="character-ai-drafter-message">{assistantMessage}</p>}
            </div>
          )}
        </section>

        {!editing && (
'''
if intro_end not in text:
    raise SystemExit("Character assistant markup anchor not found")
text = text.replace(intro_end, assistant_markup, 1)
creator.write_text(text, encoding="utf-8")

# CSS for tab readability and Character AI notebook panel.
css = Path("web/src/notebook-ui.css")
styles = r'''

/* Character creation mode tabs and AI drafting */
.notebook-binding-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 4px;
  border: 1px solid rgba(88, 69, 103, 0.14);
  border-radius: 12px;
  background: #f4ecdd;
}

.notebook-binding-tabs button {
  display: grid;
  align-content: center;
  justify-items: start;
  gap: 4px;
  min-height: 76px;
  padding: 13px 15px;
  border: 1px solid rgba(88, 69, 103, 0.16) !important;
  border-radius: 9px !important;
  background: #fffaf2 !important;
  color: #4b4052 !important;
  text-align: left;
  box-shadow: none !important;
  transition: border-color 150ms ease, background 150ms ease, transform 150ms ease;
}

.notebook-binding-tabs button:hover:not(:disabled) {
  border-color: rgba(111, 91, 183, 0.4) !important;
  background: #f5effc !important;
  transform: translateY(-1px);
}

.notebook-binding-tabs button.selected {
  border-color: #7861bd !important;
  background: #e9e1fa !important;
  color: #4f3c78 !important;
  box-shadow: inset 0 0 0 1px rgba(120, 97, 189, 0.15) !important;
}

.notebook-binding-tabs button small {
  color: inherit !important;
  opacity: 0.72;
  line-height: 1.4;
}

.notebook-binding-tabs button:disabled {
  background: #eee8df !important;
  color: #938a95 !important;
  opacity: 0.78;
}

.character-ai-drafter {
  overflow: hidden;
  border: 1px dashed rgba(111, 91, 183, 0.28);
  border-radius: 10px 14px 9px 12px;
  background: #fffaf2;
}

.character-ai-drafter-toggle {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  width: 100%;
  padding: 14px 16px;
  border: 0;
  background: transparent;
  color: #342b3c;
  text-align: left;
  font: inherit;
  cursor: pointer;
}

.character-ai-drafter-toggle > span:nth-child(2) {
  display: grid;
  gap: 3px;
}

.character-ai-drafter-toggle small {
  color: #74697d;
  line-height: 1.45;
}

.character-ai-drafter-toggle b {
  color: #7861bd;
  font-size: 1.25rem;
}

.character-ai-drafter-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  padding: 16px;
  border-top: 1px dashed rgba(111, 91, 183, 0.2);
  background: rgba(233, 225, 250, 0.32);
  animation: notebook-modal-in 180ms ease both;
}

.character-ai-drafter-actions,
.character-ai-drafter-message {
  grid-column: 1 / -1;
}

.character-ai-drafter-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.character-ai-drafter-actions small,
.character-ai-drafter-message {
  color: #675776;
  line-height: 1.5;
}

.character-ai-drafter-message {
  margin: 0;
  padding: 9px 11px;
  border-radius: 8px;
  background: #fffaf2;
  font-size: 0.78rem;
}

@media (max-width: 760px) {
  .notebook-binding-tabs,
  .character-ai-drafter-body {
    grid-template-columns: 1fr;
  }
}
'''
current = css.read_text(encoding="utf-8")
if "/* Character creation mode tabs and AI drafting */" not in current:
    css.write_text(current + styles, encoding="utf-8")
