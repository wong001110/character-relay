from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected snippet not found in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


def append_before(path: str, marker: str, content: str) -> None:
    replace(path, marker, content + marker)


# ---------------------------------------------------------------------------
# Persistence models and exports
# ---------------------------------------------------------------------------
append_before(
    "src/echo_masque/persistence/interaction_models.py",
    "class DiscordInteractionSessionRecord(Base):\n",
    '''class DiscordInteractionTemplateRecord(Base):
    """Reusable multi-character interaction rules scoped to one Discord Server."""

    __tablename__ = "discord_interaction_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    server_profile_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    template_type: Mapped[str] = mapped_column(String(32), default="roast", nullable=False)
    participant_character_card_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    rounds_per_trigger: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    maximum_triggers: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    intensity: Mapped[str] = mapped_column(String(24), default="playful", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


''',
)
replace(
    "src/echo_masque/persistence/__init__.py",
    '''from echo_masque.persistence.interaction_models import (
    DiscordInteractionRunRecord,
    DiscordInteractionSessionRecord,
    DiscordStickerSemanticRecord,
)
''',
    '''from echo_masque.persistence.interaction_models import (
    DiscordInteractionRunRecord,
    DiscordInteractionSessionRecord,
    DiscordInteractionTemplateRecord,
    DiscordStickerSemanticRecord,
)
''',
)
replace(
    "src/echo_masque/persistence/__init__.py",
    '    "DiscordInteractionSessionRecord",\n',
    '    "DiscordInteractionSessionRecord",\n    "DiscordInteractionTemplateRecord",\n',
)

# ---------------------------------------------------------------------------
# Interaction API schemas
# ---------------------------------------------------------------------------
append_before(
    "src/echo_masque/api/interaction_schemas.py",
    "class InteractionSessionCreate(BaseModel):\n",
    '''class InteractionTemplateCreate(BaseModel):
    server_profile_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    participant_character_card_ids: list[str] = Field(min_length=2, max_length=2)
    rounds_per_trigger: int = Field(default=1, ge=1, le=3)
    maximum_triggers: int = Field(default=1, ge=1, le=5)
    cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    duration_seconds: int = Field(default=600, ge=60, le=86400)
    intensity: InteractionIntensity = "playful"


class InteractionTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    participant_character_card_ids: list[str] | None = Field(
        default=None, min_length=2, max_length=2
    )
    rounds_per_trigger: int | None = Field(default=None, ge=1, le=3)
    maximum_triggers: int | None = Field(default=None, ge=1, le=5)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)
    duration_seconds: int | None = Field(default=None, ge=60, le=86400)
    intensity: InteractionIntensity | None = None


class InteractionTemplateView(BaseModel):
    id: str
    server_profile_id: str
    name: str
    template_type: Literal["roast"] = "roast"
    participant_character_card_ids: list[str]
    participant_names: list[str]
    rounds_per_trigger: int
    maximum_triggers: int
    maximum_replies_per_trigger: int
    cooldown_seconds: int
    duration_seconds: int
    intensity: InteractionIntensity
    created_at: datetime
    updated_at: datetime


class InteractionTemplateApply(BaseModel):
    channel_id: str = Field(min_length=1, max_length=200)
    target_user_id: str = Field(min_length=2, max_length=200)
    target_display_name: str = Field(default="", max_length=160)
    status: Literal["active", "paused"] = "paused"


''',
)

# ---------------------------------------------------------------------------
# Interaction repository imports and helpers
# ---------------------------------------------------------------------------
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '''from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordDeploymentScopeRecord,
    DiscordServerProfileRecord,
    PlatformConnectionRecord,
)
''',
    '''from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordDeploymentScopeRecord,
    DiscordServerCatalogRecord,
    DiscordServerProfileRecord,
    PlatformConnectionRecord,
)
''',
)
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '''from echo_masque.persistence.interaction_models import (
    DiscordInteractionRunRecord,
    DiscordInteractionSessionRecord,
    DiscordStickerSemanticRecord,
)
from echo_masque.persistence.models import utcnow
''',
    '''from echo_masque.persistence.interaction_models import (
    DiscordInteractionRunRecord,
    DiscordInteractionSessionRecord,
    DiscordInteractionTemplateRecord,
    DiscordStickerSemanticRecord,
)
from echo_masque.persistence.models import CharacterCardRecord, utcnow
''',
)
append_before(
    "src/echo_masque/persistence/interaction_repository.py",
    "class InteractionRepository:\n",
    '''def _decode_catalog_channels(value: str) -> list[dict[str, object]]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


''',
)

insert_methods = '''    @staticmethod
    def template_character_ids(record: DiscordInteractionTemplateRecord) -> list[str]:
        return _decode(record.participant_character_card_ids_json)

    def _resolve_template_deployments(
        self,
        session: object,
        *,
        owner_id: str,
        server_profile_id: str,
        character_card_ids: list[str],
    ) -> list[str]:
        if len(character_card_ids) != 2 or len(set(character_card_ids)) != 2:
            raise InteractionConflict("Interaction Templates require two different characters.")
        deployment_ids: list[str] = []
        for character_card_id in character_card_ids:
            character = session.get(CharacterCardRecord, character_card_id)  # type: ignore[attr-defined]
            if character is None or character.owner_id != owner_id:
                raise InteractionConflict("Every template character must belong to this account.")
            deployment = session.scalar(  # type: ignore[attr-defined]
                select(CharacterDeploymentRecord)
                .join(
                    DiscordDeploymentScopeRecord,
                    DiscordDeploymentScopeRecord.deployment_id
                    == CharacterDeploymentRecord.id,
                )
                .where(
                    CharacterDeploymentRecord.owner_id == owner_id,
                    CharacterDeploymentRecord.character_card_id == character_card_id,
                    CharacterDeploymentRecord.platform == "discord",
                    CharacterDeploymentRecord.status == "active",
                    DiscordDeploymentScopeRecord.server_profile_id == server_profile_id,
                )
                .limit(1)
            )
            if deployment is None:
                raise InteractionConflict(
                    "Every template character needs an active deployment in this Discord Server."
                )
            deployment_ids.append(deployment.id)
        return deployment_ids

    def create_template(
        self,
        *,
        owner_id: str,
        server_profile_id: str,
        name: str,
        participant_character_card_ids: list[str],
        rounds_per_trigger: int,
        maximum_triggers: int,
        cooldown_seconds: int,
        duration_seconds: int,
        intensity: str,
    ) -> DiscordInteractionTemplateRecord:
        with self.database.session() as session:
            profile = session.get(DiscordServerProfileRecord, server_profile_id)
            if profile is None or profile.owner_id != owner_id:
                raise KeyError("server profile")
            self._resolve_template_deployments(
                session,
                owner_id=owner_id,
                server_profile_id=server_profile_id,
                character_card_ids=participant_character_card_ids,
            )
            record = DiscordInteractionTemplateRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                server_profile_id=server_profile_id,
                name=name,
                template_type="roast",
                participant_character_card_ids_json=_encode(
                    participant_character_card_ids
                ),
                rounds_per_trigger=rounds_per_trigger,
                maximum_triggers=maximum_triggers,
                cooldown_seconds=cooldown_seconds,
                duration_seconds=duration_seconds,
                intensity=intensity,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_templates(
        self,
        owner_id: str,
        *,
        server_profile_id: str,
    ) -> list[DiscordInteractionTemplateRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DiscordInteractionTemplateRecord)
                    .where(
                        DiscordInteractionTemplateRecord.owner_id == owner_id,
                        DiscordInteractionTemplateRecord.server_profile_id
                        == server_profile_id,
                    )
                    .order_by(
                        DiscordInteractionTemplateRecord.updated_at.desc(),
                        DiscordInteractionTemplateRecord.name,
                    )
                )
            )

    def get_template(
        self,
        template_id: str,
        owner_id: str,
    ) -> DiscordInteractionTemplateRecord | None:
        with self.database.session() as session:
            record = session.get(DiscordInteractionTemplateRecord, template_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def update_template(
        self,
        template_id: str,
        owner_id: str,
        *,
        name: str | None = None,
        participant_character_card_ids: list[str] | None = None,
        rounds_per_trigger: int | None = None,
        maximum_triggers: int | None = None,
        cooldown_seconds: int | None = None,
        duration_seconds: int | None = None,
        intensity: str | None = None,
    ) -> DiscordInteractionTemplateRecord | None:
        with self.database.session() as session:
            record = session.get(DiscordInteractionTemplateRecord, template_id)
            if record is None or record.owner_id != owner_id:
                return None
            if participant_character_card_ids is not None:
                self._resolve_template_deployments(
                    session,
                    owner_id=owner_id,
                    server_profile_id=record.server_profile_id,
                    character_card_ids=participant_character_card_ids,
                )
                record.participant_character_card_ids_json = _encode(
                    participant_character_card_ids
                )
            if name is not None:
                record.name = name
            if rounds_per_trigger is not None:
                record.rounds_per_trigger = rounds_per_trigger
            if maximum_triggers is not None:
                record.maximum_triggers = maximum_triggers
            if cooldown_seconds is not None:
                record.cooldown_seconds = cooldown_seconds
            if duration_seconds is not None:
                record.duration_seconds = duration_seconds
            if intensity is not None:
                record.intensity = intensity
            session.commit()
            session.refresh(record)
            return record

    def delete_template(self, template_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(DiscordInteractionTemplateRecord, template_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.delete(record)
            session.commit()
            return True

    def apply_template(
        self,
        *,
        template_id: str,
        owner_id: str,
        channel_id: str,
        target_user_id: str,
        target_display_name: str,
        status: str,
    ) -> DiscordInteractionSessionRecord:
        with self.database.session() as session:
            template = session.get(DiscordInteractionTemplateRecord, template_id)
            if template is None or template.owner_id != owner_id:
                raise KeyError("interaction template")
            profile = session.get(DiscordServerProfileRecord, template.server_profile_id)
            if profile is None or profile.owner_id != owner_id:
                raise KeyError("server profile")
            participant_ids = self._resolve_template_deployments(
                session,
                owner_id=owner_id,
                server_profile_id=profile.id,
                character_card_ids=self.template_character_ids(template),
            )
            catalog = session.scalar(
                select(DiscordServerCatalogRecord).where(
                    DiscordServerCatalogRecord.owner_id == owner_id,
                    DiscordServerCatalogRecord.connection_id == profile.connection_id,
                    DiscordServerCatalogRecord.guild_id == profile.guild_id,
                )
            )
            if catalog is None:
                raise InteractionConflict(
                    "The Connector has not synchronized this Discord Server yet."
                )
            channel = next(
                (
                    item
                    for item in _decode_catalog_channels(catalog.channels_json)
                    if item.get("id") == channel_id
                ),
                None,
            )
            if channel is None:
                raise InteractionConflict(
                    "The selected Channel is not present in the current Server catalog."
                )
            category_id = str(channel.get("category_id") or "")
            if channel_id in _decode(profile.excluded_channel_ids_json) or (
                category_id and category_id in _decode(profile.excluded_category_ids_json)
            ):
                raise InteractionConflict(
                    "The selected Channel is excluded by this Server configuration."
                )
            values = {
                "connection_id": profile.connection_id,
                "guild_id": profile.guild_id,
                "guild_name": profile.guild_name,
                "channel_id": channel_id,
                "channel_name": str(channel.get("name") or channel_id),
                "category_id": category_id,
                "participant_deployment_ids": participant_ids,
                "rounds_per_trigger": template.rounds_per_trigger,
                "maximum_triggers": template.maximum_triggers,
                "cooldown_seconds": template.cooldown_seconds,
                "duration_seconds": template.duration_seconds,
                "intensity": template.intensity,
            }
        return self.create_session(
            owner_id=owner_id,
            target_user_id=target_user_id,
            target_display_name=target_display_name,
            status=status,
            **values,
        )

    def sync_sticker_catalog(
        self,
        *,
        connection_id: str,
        guild_id: str,
        stickers: list[dict[str, object]],
    ) -> int:
        synchronized = 0
        for item in stickers:
            sticker_id = str(item.get("sticker_id") or "").strip()
            name = str(item.get("name") or "Sticker").strip()
            if not sticker_id or not name:
                continue
            raw_tags = item.get("tags")
            tags = (
                [str(value).strip() for value in raw_tags if str(value).strip()]
                if isinstance(raw_tags, list)
                else []
            )
            self.resolve_sticker(
                connection_id=connection_id,
                guild_id=guild_id,
                sticker_id=sticker_id,
                name=name,
                description=str(item.get("description") or ""),
                tags=tags,
                format_type=str(item.get("format_type") or "unknown"),
                asset_url=str(item.get("asset_url") or ""),
            )
            synchronized += 1
        return synchronized

'''
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '''class InteractionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

''',
    '''class InteractionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

''' + insert_methods,
)
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '''    def list_sessions(self, owner_id: str) -> list[DiscordInteractionSessionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DiscordInteractionSessionRecord)
                    .where(DiscordInteractionSessionRecord.owner_id == owner_id)
                    .order_by(
''',
    '''    def list_sessions(
        self,
        owner_id: str,
        *,
        connection_id: str | None = None,
        guild_id: str | None = None,
    ) -> list[DiscordInteractionSessionRecord]:
        with self.database.session() as session:
            conditions = [DiscordInteractionSessionRecord.owner_id == owner_id]
            if connection_id is not None:
                conditions.append(
                    DiscordInteractionSessionRecord.connection_id == connection_id
                )
            if guild_id is not None:
                conditions.append(DiscordInteractionSessionRecord.guild_id == guild_id)
            return list(
                session.scalars(
                    select(DiscordInteractionSessionRecord)
                    .where(*conditions)
                    .order_by(
''',
)
# Extend lifecycle operations.
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '''        with self.database.session() as session:
            run_result = session.execute(
''',
    '''        with self.database.session() as session:
            template_result = session.execute(
                delete(DiscordInteractionTemplateRecord).where(
                    DiscordInteractionTemplateRecord.owner_id == owner_id
                )
            )
            run_result = session.execute(
''',
)
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    '''        return {
            "discord_interaction_runs": int(getattr(run_result, "rowcount", 0) or 0),
''',
    '''        return {
            "discord_interaction_templates": int(
                getattr(template_result, "rowcount", 0) or 0
            ),
            "discord_interaction_runs": int(getattr(run_result, "rowcount", 0) or 0),
''',
    count=1,
)
# claim_owner is the second matching block.
marker = '''    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            run_result = session.execute(
'''
replace(
    "src/echo_masque/persistence/interaction_repository.py",
    marker,
    '''    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            template_result = session.execute(
                update(DiscordInteractionTemplateRecord)
                .where(DiscordInteractionTemplateRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            run_result = session.execute(
''',
)
# Add template count to the final return.
path = Path("src/echo_masque/persistence/interaction_repository.py")
text = path.read_text(encoding="utf-8")
pos = text.rfind('        return {\n            "discord_interaction_runs"')
if pos < 0:
    raise RuntimeError("claim_owner return marker not found")
text = (
    text[:pos]
    + '''        return {
            "discord_interaction_templates": int(
                getattr(template_result, "rowcount", 0) or 0
            ),
'''
    + text[pos + len('        return {\n'):]
)
path.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Interaction owner routes
# ---------------------------------------------------------------------------
replace(
    "src/echo_masque/api/routes/interactions.py",
    '''    InteractionSessionCreate,
    InteractionSessionStatusUpdate,
    InteractionSessionView,
''',
    '''    InteractionSessionCreate,
    InteractionSessionStatusUpdate,
    InteractionSessionView,
    InteractionTemplateApply,
    InteractionTemplateCreate,
    InteractionTemplateUpdate,
    InteractionTemplateView,
''',
)
replace(
    "src/echo_masque/api/routes/interactions.py",
    '''from echo_masque.persistence.interaction_models import (
    DiscordInteractionSessionRecord,
    DiscordStickerSemanticRecord,
)
''',
    '''from echo_masque.persistence.interaction_models import (
    DiscordInteractionSessionRecord,
    DiscordInteractionTemplateRecord,
    DiscordStickerSemanticRecord,
)
''',
)
append_before(
    "src/echo_masque/api/routes/interactions.py",
    "def session_view(\n",
    '''def template_view(
    request: Request,
    record: DiscordInteractionTemplateRecord,
) -> InteractionTemplateView:
    ids = interaction_repository(request).template_character_ids(record)
    characters = character_repository(request)
    names: list[str] = []
    for character_id in ids:
        card = characters.get_character_card(character_id, record.owner_id)
        names.append(card.display_name if card is not None else "Archived character")
    return InteractionTemplateView(
        id=record.id,
        server_profile_id=record.server_profile_id,
        name=record.name,
        participant_character_card_ids=ids,
        participant_names=names,
        rounds_per_trigger=record.rounds_per_trigger,
        maximum_triggers=record.maximum_triggers,
        maximum_replies_per_trigger=record.rounds_per_trigger * len(ids),
        cooldown_seconds=record.cooldown_seconds,
        duration_seconds=record.duration_seconds,
        intensity=record.intensity,  # type: ignore[arg-type]
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


''',
)
append_before(
    "src/echo_masque/api/routes/interactions.py",
    '@router.get("/interaction-sessions", response_model=list[InteractionSessionView])\n',
    '''@router.get("/interaction-templates", response_model=list[InteractionTemplateView])
def list_interaction_templates(
    request: Request,
    user: CurrentUserDependency,
    server_profile_id: str = Query(min_length=1, max_length=64),
) -> list[InteractionTemplateView]:
    return [
        template_view(request, item)
        for item in interaction_repository(request).list_templates(
            user.id,
            server_profile_id=server_profile_id,
        )
    ]


@router.post(
    "/interaction-templates",
    response_model=InteractionTemplateView,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction_template(
    payload: InteractionTemplateCreate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionTemplateView:
    try:
        record = interaction_repository(request).create_template(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord Server not found.") from exc
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return template_view(request, record)


@router.put(
    "/interaction-templates/{template_id}",
    response_model=InteractionTemplateView,
)
def update_interaction_template(
    template_id: str,
    payload: InteractionTemplateUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionTemplateView:
    try:
        record = interaction_repository(request).update_template(
            template_id,
            user.id,
            **payload.model_dump(exclude_unset=True),
        )
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Interaction Template not found.")
    return template_view(request, record)


@router.post(
    "/interaction-templates/{template_id}/apply",
    response_model=InteractionSessionView,
    status_code=status.HTTP_201_CREATED,
)
def apply_interaction_template(
    template_id: str,
    payload: InteractionTemplateApply,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionSessionView:
    try:
        record = interaction_repository(request).apply_template(
            template_id=template_id,
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Interaction Template not found.") from exc
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session_view(request, record)


@router.delete(
    "/interaction-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_interaction_template(
    template_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not interaction_repository(request).delete_template(template_id, user.id):
        raise HTTPException(status_code=404, detail="Interaction Template not found.")


''',
)
replace(
    "src/echo_masque/api/routes/interactions.py",
    '''def list_interaction_sessions(
    request: Request,
    user: CurrentUserDependency,
) -> list[InteractionSessionView]:
    return [
        session_view(request, item)
        for item in interaction_repository(request).list_sessions(user.id)
    ]
''',
    '''def list_interaction_sessions(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
) -> list[InteractionSessionView]:
    return [
        session_view(request, item)
        for item in interaction_repository(request).list_sessions(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
        )
    ]
''',
)

# ---------------------------------------------------------------------------
# Deployment filtering by Server Profile
# ---------------------------------------------------------------------------
replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''    def list_deployments(
        self,
        owner_id: str,
        *,
        character_card_id: str | None = None,
    ) -> list[CharacterDeploymentRecord]:
        with self.database.session() as session:
            query = select(CharacterDeploymentRecord).where(
                CharacterDeploymentRecord.owner_id == owner_id
            )
''',
    '''    def list_deployments(
        self,
        owner_id: str,
        *,
        character_card_id: str | None = None,
        server_profile_id: str | None = None,
    ) -> list[CharacterDeploymentRecord]:
        with self.database.session() as session:
            query = select(CharacterDeploymentRecord)
            if server_profile_id is not None:
                query = query.join(
                    DiscordDeploymentScopeRecord,
                    DiscordDeploymentScopeRecord.deployment_id
                    == CharacterDeploymentRecord.id,
                )
            query = query.where(CharacterDeploymentRecord.owner_id == owner_id)
''',
)
replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''            if character_card_id is not None:
                query = query.where(
                    CharacterDeploymentRecord.character_card_id == character_card_id
                )
            query = query.order_by(
''',
    '''            if character_card_id is not None:
                query = query.where(
                    CharacterDeploymentRecord.character_card_id == character_card_id
                )
            if server_profile_id is not None:
                query = query.where(
                    DiscordDeploymentScopeRecord.server_profile_id == server_profile_id
                )
            query = query.order_by(
''',
    count=1,
)
replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''        character_card_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
''',
    '''        character_card_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        server_profile_id: str | None = None,
''',
    count=1,
)
replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''        with self.database.session() as session:
            conditions = [CharacterDeploymentRecord.owner_id == owner_id]
''',
    '''        with self.database.session() as session:
            conditions = [CharacterDeploymentRecord.owner_id == owner_id]
            if server_profile_id is not None:
                conditions.append(
                    DiscordDeploymentScopeRecord.server_profile_id == server_profile_id
                )
''',
    count=1,
)
# Replace count and records select_from blocks with a joined base.
replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(CharacterDeploymentRecord)
                    .where(*conditions)
                )
                or 0
            )
''',
    '''            count_query = select(func.count()).select_from(CharacterDeploymentRecord)
            records_query = select(CharacterDeploymentRecord)
            if server_profile_id is not None:
                count_query = count_query.join(
                    DiscordDeploymentScopeRecord,
                    DiscordDeploymentScopeRecord.deployment_id
                    == CharacterDeploymentRecord.id,
                )
                records_query = records_query.join(
                    DiscordDeploymentScopeRecord,
                    DiscordDeploymentScopeRecord.deployment_id
                    == CharacterDeploymentRecord.id,
                )
            total = int(session.scalar(count_query.where(*conditions)) or 0)
''',
)
replace(
    "src/echo_masque/persistence/deployment_repository.py",
    '''                session.scalars(
                    select(CharacterDeploymentRecord)
                    .where(*conditions)
''',
    '''                session.scalars(
                    records_query.where(*conditions)
''',
    count=1,
)
# Replace counts block with server-scoped helper queries.
old_counts = '''            counts = {
                "active": int(
                    session.scalar(
                        select(func.count())
                        .select_from(CharacterDeploymentRecord)
                        .where(
                            CharacterDeploymentRecord.owner_id == owner_id,
                            CharacterDeploymentRecord.status == "active",
                        )
                    )
                    or 0
                ),
                "paused": int(
                    session.scalar(
                        select(func.count())
                        .select_from(CharacterDeploymentRecord)
                        .where(
                            CharacterDeploymentRecord.owner_id == owner_id,
                            CharacterDeploymentRecord.status == "paused",
                        )
                    )
                    or 0
                ),
                "attention": int(
                    session.scalar(
                        select(func.count())
                        .select_from(CharacterDeploymentRecord)
                        .where(
                            CharacterDeploymentRecord.owner_id == owner_id,
                            CharacterDeploymentRecord.status.in_(("error", "offline")),
                        )
                    )
                    or 0
                ),
            }
'''
new_counts = '''            def scoped_status_count(statuses: tuple[str, ...]) -> int:
                query = select(func.count()).select_from(CharacterDeploymentRecord)
                count_conditions = [
                    CharacterDeploymentRecord.owner_id == owner_id,
                    CharacterDeploymentRecord.status.in_(statuses),
                ]
                if server_profile_id is not None:
                    query = query.join(
                        DiscordDeploymentScopeRecord,
                        DiscordDeploymentScopeRecord.deployment_id
                        == CharacterDeploymentRecord.id,
                    )
                    count_conditions.append(
                        DiscordDeploymentScopeRecord.server_profile_id
                        == server_profile_id
                    )
                return int(session.scalar(query.where(*count_conditions)) or 0)

            counts = {
                "active": scoped_status_count(("active",)),
                "paused": scoped_status_count(("paused",)),
                "attention": scoped_status_count(("error", "offline")),
            }
'''
replace(
    "src/echo_masque/persistence/deployment_repository.py",
    old_counts,
    new_counts,
)
replace(
    "src/echo_masque/api/routes/deployments.py",
    '''    character_card_id: str | None = Query(default=None),
) -> list[CharacterDeploymentView]:
    records = deployment_repository(request).list_deployments(
        user.id,
        character_card_id=character_card_id,
    )
''',
    '''    character_card_id: str | None = Query(default=None),
    server_profile_id: str | None = Query(default=None, max_length=64),
) -> list[CharacterDeploymentView]:
    records = deployment_repository(request).list_deployments(
        user.id,
        character_card_id=character_card_id,
        server_profile_id=server_profile_id,
    )
''',
)
replace(
    "src/echo_masque/api/routes/deployments.py",
    '''    deployment_status: str | None = Query(
        default=None,
        alias="status",
        max_length=24,
    ),
''',
    '''    deployment_status: str | None = Query(
        default=None,
        alias="status",
        max_length=24,
    ),
    server_profile_id: str | None = Query(default=None, max_length=64),
''',
)
replace(
    "src/echo_masque/api/routes/deployments.py",
    '''        platform=platform,
        status=deployment_status,
    )
''',
    '''        platform=platform,
        status=deployment_status,
        server_profile_id=server_profile_id,
    )
''',
    count=1,
)

# ---------------------------------------------------------------------------
# Connector catalog carries Guild Stickers and syncs them into the dictionary.
# ---------------------------------------------------------------------------
append_before(
    "src/echo_masque/api/connector_schemas.py",
    "class DiscordCatalogServer(BaseModel):\n",
    '''class DiscordCatalogSticker(BaseModel):
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)


''',
)
replace(
    "src/echo_masque/api/connector_schemas.py",
    '''class DiscordCatalogServer(BaseModel):
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(min_length=1, max_length=160)
    channels: list[DiscordCatalogChannel] = Field(default_factory=list, max_length=1000)
''',
    '''class DiscordCatalogServer(BaseModel):
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(min_length=1, max_length=160)
    channels: list[DiscordCatalogChannel] = Field(default_factory=list, max_length=1000)
    stickers: list[DiscordCatalogSticker] = Field(default_factory=list, max_length=1000)
''',
)
replace(
    "src/echo_masque/api/routes/connectors.py",
    '''        deployment_repository(request).sync_discord_server_catalog(
            connection_id=payload.connection_id,
            servers=[
                (
                    server.guild_id,
                    server.guild_name,
                    [channel.model_dump() for channel in server.channels],
                )
                for server in payload.servers
            ],
        )
''',
    '''        deployment_repository(request).sync_discord_server_catalog(
            connection_id=payload.connection_id,
            servers=[
                (
                    server.guild_id,
                    server.guild_name,
                    [channel.model_dump() for channel in server.channels],
                )
                for server in payload.servers
            ],
        )
        for server in payload.servers:
            interaction_repository(request).sync_sticker_catalog(
                connection_id=payload.connection_id,
                guild_id=server.guild_id,
                stickers=[item.model_dump() for item in server.stickers],
            )
''',
)

# TypeScript connector catalog types.
replace(
    "connectors/discord/src/types.ts",
    '''export interface DiscordCatalogServer {
  guild_id: string;
  guild_name: string;
  channels: DiscordCatalogChannel[];
}
''',
    '''export interface DiscordCatalogSticker {
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
}

export interface DiscordCatalogServer {
  guild_id: string;
  guild_name: string;
  channels: DiscordCatalogChannel[];
  stickers: DiscordCatalogSticker[];
}
''',
)
replace(
    "connectors/discord/src/index.ts",
    '''const intents = [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages];
''',
    '''const intents = [
  GatewayIntentBits.Guilds,
  GatewayIntentBits.GuildMessages,
  GatewayIntentBits.GuildExpressions
];
''',
)
replace(
    "connectors/discord/src/index.ts",
    '''    servers.push({
      guild_id: guild.id,
      guild_name: guild.name,
      channels
    });
''',
    '''    let stickers: DiscordCatalogServer["stickers"] = [];
    try {
      const fetchedStickers = await guild.stickers.fetch();
      stickers = [...fetchedStickers.values()]
        .map((sticker) => ({
          sticker_id: sticker.id,
          name: sticker.name || "Sticker",
          description: sticker.description ?? "",
          tags: (sticker.tags ?? "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          format_type: String(sticker.format),
          asset_url: sticker.url
        }))
        .sort((left, right) => left.name.localeCompare(right.name));
    } catch (error) {
      log("Unable to synchronize Discord Guild Stickers.", {
        guildId: guild.id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
    servers.push({
      guild_id: guild.id,
      guild_name: guild.name,
      channels,
      stickers
    });
''',
)
replace(
    "connectors/discord/src/index.ts",
    '''    channels: servers.reduce((total, server) => total + server.channels.length, 0)
''',
    '''    channels: servers.reduce((total, server) => total + server.channels.length, 0),
    stickers: servers.reduce((total, server) => total + server.stickers.length, 0)
''',
)

# ---------------------------------------------------------------------------
# Focused tests
# ---------------------------------------------------------------------------
test_path = Path("tests/test_server_scoped_workspace.py")
test_path.write_text(
    '''from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ADMIN_EMAIL = "server-workspace@example.com"
ADMIN_PASSWORD = "ServerWorkspace2026!"
SECRET = "server-workspace-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Server Workspace Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def connector_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SECRET}"}


def create_character(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": name,
            "subtitle": "Server workspace fixture",
            "subject_type": "companion",
            "persona_summary": f"{name} is concise.",
            "traits": ["witty"],
            "tags": ["discord"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent memories"],
            "memory_summary": "Use supplied context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def seed_server(client: TestClient) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    login(client)
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Managed Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-1",
            "status": "connected",
            "metadata": {},
        },
    ).json()
    catalog = client.put(
        "/api/connectors/discord/server-catalog",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "servers": [
                {
                    "guild_id": "guild-1",
                    "guild_name": "Guild One",
                    "channels": [
                        {
                            "id": "channel-1",
                            "name": "general",
                            "category_id": "category-1",
                            "category_name": "Community",
                            "type": "text",
                        }
                    ],
                    "stickers": [
                        {
                            "sticker_id": "sticker-1",
                            "name": "side_eye_cat",
                            "description": "A doubtful cat",
                            "tags": ["doubt"],
                            "format_type": "png",
                            "asset_url": "https://cdn.discordapp.com/stickers/sticker-1.png",
                        }
                    ],
                }
            ],
        },
    )
    assert catalog.status_code == 204, catalog.text
    profile_response = client.post(
        "/api/discord/server-profiles",
        json={
            "connection_id": connection["id"],
            "name": "Guild One",
            "guild_id": "guild-1",
            "guild_name": "Guild One",
            "excluded_channel_ids": [],
            "excluded_category_ids": [],
            "thread_policy": "inherit_parent",
        },
    )
    assert profile_response.status_code == 201, profile_response.text
    profile = profile_response.json()
    deployments: list[dict[str, object]] = []
    for name in ("Ann", "Ning"):
        character = create_character(client, name)
        deployment = client.post(
            "/api/deployments",
            json={
                "character_card_id": character["id"],
                "connection_id": connection["id"],
                "server_profile_id": profile["id"],
                "workspace_id": "",
                "workspace_name": "",
                "channel_id": "",
                "channel_name": "",
                "thread_id": "",
                "thread_name": "",
                "excluded_channel_ids": [],
                "excluded_category_ids": [],
                "participation_mode": "mention_and_reply",
                "memory_scope": "channel_isolated",
                "version_label": "Current",
                "sticker_count": 0,
                "status": "active",
            },
        )
        assert deployment.status_code == 201, deployment.text
        deployments.append(deployment.json())
    return connection, profile, deployments


def test_server_scoped_templates_apply_and_deployments_filter(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "server-workspace.db")))
    connection, profile, deployments = seed_server(client)
    template = client.post(
        "/api/interaction-templates",
        json={
            "server_profile_id": profile["id"],
            "name": "Ann and Ning roast",
            "participant_character_card_ids": [
                deployments[0]["character_card_id"],
                deployments[1]["character_card_id"],
            ],
            "rounds_per_trigger": 2,
            "maximum_triggers": 3,
            "cooldown_seconds": 30,
            "duration_seconds": 600,
            "intensity": "playful",
        },
    )
    assert template.status_code == 201, template.text
    assert template.json()["maximum_replies_per_trigger"] == 4

    applied = client.post(
        f"/api/interaction-templates/{template.json()['id']}/apply",
        json={
            "channel_id": "channel-1",
            "target_user_id": "user-1",
            "target_display_name": "Target",
            "status": "active",
        },
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["participant_deployment_ids"] == [
        deployments[0]["id"],
        deployments[1]["id"],
    ]
    assert applied.json()["guild_id"] == "guild-1"
    assert applied.json()["channel_name"] == "general"

    filtered = client.get(
        "/api/deployments/page",
        params={"server_profile_id": profile["id"], "page": 1, "page_size": 20},
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 2
    assert filtered.json()["active"] == 2

    sessions = client.get(
        "/api/interaction-sessions",
        params={"connection_id": connection["id"], "guild_id": "guild-1"},
    )
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1


def test_guild_sticker_catalog_populates_dictionary_without_message(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "sticker-catalog.db")))
    connection, _, _ = seed_server(client)
    stickers = client.get(
        "/api/discord/sticker-dictionary",
        params={"connection_id": connection["id"], "guild_id": "guild-1"},
    )
    assert stickers.status_code == 200, stickers.text
    assert len(stickers.json()) == 1
    assert stickers.json()[0]["name"] == "side_eye_cat"
    assert stickers.json()[0]["semantic_source"] == "discord_metadata"
''',
    encoding="utf-8",
)
