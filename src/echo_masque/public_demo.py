"""Provision and synchronize the shared read-only public Demo account."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from argon2.exceptions import VerificationError

from echo_masque.auth import AuthService
from echo_masque.config import Settings
from echo_masque.credentials import CredentialStore
from echo_masque.persistence import (
    AuthRepository,
    Repository,
    TargetAccessRepository,
    WorkspaceRepository,
)
from echo_masque.persistence.models import CharacterCardRecord, UserRecord
from echo_masque.workspace import (
    PackItemInput,
    ScenarioCreate,
    ScenarioUpdate,
    ScenarioView,
    TestPackCreate,
    TestPackUpdate,
    TestPackView,
)

logger = logging.getLogger(__name__)

PUBLIC_DEMO_USER_ID = "public-demo"
PUBLIC_DEMO_EMAIL = "demo@echo-masque.app"
PUBLIC_DEMO_PASSWORD = "EchoMasqueDemo2026!"
PUBLIC_DEMO_DISPLAY_NAME = "Echo Masque Demo"

_PREFERRED_CARD_NAMES = (
    "LIVE DEMO — Stable Ann",
    "LIVE DEMO — Drift Ann (OOC Control)",
)


@dataclass(frozen=True, slots=True)
class PublicDemoSyncResult:
    user_id: str
    character_count: int
    scenario_count: int
    test_pack_count: int


def is_public_demo_email(value: str) -> bool:
    return value.casefold().strip() == PUBLIC_DEMO_EMAIL


class PublicDemoService:
    """Keep a low-privilege shared account aligned with the Admin demo workspace."""

    def __init__(
        self,
        *,
        settings: Settings,
        auth_service: AuthService,
        auth_repository: AuthRepository,
        repository: Repository,
        workspace_repository: WorkspaceRepository,
        target_access_repository: TargetAccessRepository,
        credential_store: CredentialStore,
    ) -> None:
        self.settings = settings
        self.auth_service = auth_service
        self.auth_repository = auth_repository
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.target_access_repository = target_access_repository
        self.credential_store = credential_store

    def synchronize(self) -> PublicDemoSyncResult | None:
        if not self.settings.public_demo_enabled:
            return None
        source_email = self.settings.bootstrap_admin_email
        if source_email is None:
            logger.warning("Public Demo sync skipped because no Bootstrap Admin is configured.")
            return None
        source = self.auth_repository.get_user_by_email(source_email)
        if source is None or not source.is_active:
            logger.warning("Public Demo sync skipped because the Bootstrap Admin is unavailable.")
            return None

        demo = self._ensure_demo_user()
        character_count = self._sync_characters(source.id, demo.id)
        scenario_ids = self._sync_scenarios(source.id, demo.id)
        pack_count = self._sync_test_packs(source.id, demo.id, scenario_ids)
        result = PublicDemoSyncResult(
            user_id=demo.id,
            character_count=character_count,
            scenario_count=len(scenario_ids),
            test_pack_count=pack_count,
        )
        self.auth_repository.audit(
            actor_user_id=source.id,
            action="public_demo.synchronized",
            resource_type="workspace",
            resource_id=demo.id,
            metadata={
                "characters": result.character_count,
                "scenarios": result.scenario_count,
                "test_packs": result.test_pack_count,
            },
        )
        return result

    def _ensure_demo_user(self) -> UserRecord:
        record = self.auth_repository.get_user_by_email(PUBLIC_DEMO_EMAIL)
        if record is None:
            return self.auth_repository.create_user(
                user_id=PUBLIC_DEMO_USER_ID,
                email=PUBLIC_DEMO_EMAIL,
                display_name=PUBLIC_DEMO_DISPLAY_NAME,
                password_hash=self.auth_service.passwords.hash(PUBLIC_DEMO_PASSWORD),
                role="user",
            )

        password_valid = False
        try:
            password_valid = bool(
                self.auth_service.passwords.verify(
                    record.password_hash,
                    PUBLIC_DEMO_PASSWORD,
                )
            )
        except VerificationError:
            password_valid = False

        with self.auth_repository.database.session() as session:
            stored = session.get(UserRecord, record.id)
            if stored is None:
                raise RuntimeError("Public Demo account disappeared during synchronization.")
            stored.email = PUBLIC_DEMO_EMAIL
            stored.display_name = PUBLIC_DEMO_DISPLAY_NAME
            stored.role = "user"
            stored.is_active = True
            if not password_valid:
                stored.password_hash = self.auth_service.passwords.hash(PUBLIC_DEMO_PASSWORD)
            session.commit()
            session.refresh(stored)
            return stored

    def _sync_characters(self, source_owner_id: str, demo_owner_id: str) -> int:
        source_cards = self._selected_source_cards(
            self.repository.list_character_cards(source_owner_id)
        )
        demo_cards = {
            item.display_name: item
            for item in self.repository.list_character_cards(demo_owner_id)
        }

        synchronized = 0
        for source_card in source_cards:
            source_target = self.repository.get_target(source_card.target_id)
            if source_target is None:
                logger.warning(
                    "Public Demo skipped Character %s because its Target is missing.",
                    source_card.id,
                )
                continue
            config = _json_object(source_target.config_json)
            demo_card = demo_cards.get(source_card.display_name)
            if demo_card is None:
                demo_target = self.repository.create_target(
                    name=source_target.name,
                    target_kind=source_target.target_kind,
                    config=config,
                )
                self.target_access_repository.assign(
                    owner_id=demo_owner_id,
                    target_id=demo_target.id,
                )
                demo_card = self.repository.create_character_card(
                    owner_id=demo_owner_id,
                    target_id=demo_target.id,
                    display_name=source_card.display_name,
                    subtitle=source_card.subtitle,
                    subject_type=source_card.subject_type,
                    persona_summary=source_card.persona_summary,
                    traits=_json_list(source_card.traits_json),
                    tags=_json_list(source_card.tags_json),
                    expected_tone=source_card.expected_tone,
                    forbidden_behaviors=_json_list(source_card.forbidden_behaviors_json),
                    memory_summary=source_card.memory_summary,
                    preferred_suites=_json_list(source_card.preferred_suites_json),
                    portrait_variant=source_card.portrait_variant,
                )
                demo_cards[demo_card.display_name] = demo_card
            else:
                demo_target = self.repository.get_target(demo_card.target_id)
                if demo_target is None:
                    demo_target = self.repository.create_target(
                        name=source_target.name,
                        target_kind=source_target.target_kind,
                        config=config,
                    )
                    with self.auth_repository.database.session() as session:
                        stored_card = session.get(CharacterCardRecord, demo_card.id)
                        if stored_card is None:
                            raise RuntimeError(
                                "Public Demo Character disappeared during Target repair."
                            )
                        stored_card.target_id = demo_target.id
                        session.commit()
                        session.refresh(stored_card)
                        demo_card = stored_card
                else:
                    self.repository.update_target(
                        demo_target.id,
                        name=source_target.name,
                        config=config,
                    )
                self.target_access_repository.assign(
                    owner_id=demo_owner_id,
                    target_id=demo_target.id,
                )
                updated = self.repository.update_character_card(
                    demo_card.id,
                    demo_owner_id,
                    display_name=source_card.display_name,
                    subtitle=source_card.subtitle,
                    subject_type=source_card.subject_type,
                    persona_summary=source_card.persona_summary,
                    traits=_json_list(source_card.traits_json),
                    tags=_json_list(source_card.tags_json),
                    expected_tone=source_card.expected_tone,
                    forbidden_behaviors=_json_list(source_card.forbidden_behaviors_json),
                    memory_summary=source_card.memory_summary,
                    preferred_suites=_json_list(source_card.preferred_suites_json),
                    portrait_variant=source_card.portrait_variant,
                )
                if updated is None:
                    raise RuntimeError("Public Demo Character update failed.")
                demo_card = updated

            self._sync_credential(
                source_owner_id=source_owner_id,
                source_card_id=source_card.id,
                demo_owner_id=demo_owner_id,
                demo_card_id=demo_card.id,
            )
            synchronized += 1
        return synchronized

    def _selected_source_cards(
        self,
        cards: list[CharacterCardRecord],
    ) -> list[CharacterCardRecord]:
        by_name = {item.display_name: item for item in cards}
        selected = [by_name[name] for name in _PREFERRED_CARD_NAMES if name in by_name]
        selected_ids = {item.id for item in selected}
        for item in cards:
            if item.id in selected_ids:
                continue
            tags = _json_list(item.tags_json)
            if "live-demo" in tags or item.display_name.startswith("LIVE DEMO —"):
                selected.append(item)
                selected_ids.add(item.id)
            if len(selected) >= 2:
                return selected[:2]
        for item in cards:
            if item.id not in selected_ids:
                selected.append(item)
            if len(selected) >= 2:
                break
        if len(selected) < 2:
            logger.warning(
                "Public Demo found only %s source Character Card(s); expected two.",
                len(selected),
            )
        return selected[:2]

    def _sync_credential(
        self,
        *,
        source_owner_id: str,
        source_card_id: str,
        demo_owner_id: str,
        demo_card_id: str,
    ) -> None:
        source_value = self.credential_store.get(source_owner_id, source_card_id)
        demo_value = self.credential_store.get(demo_owner_id, demo_card_id)
        if source_value is None:
            if demo_value is not None:
                self.credential_store.delete(demo_owner_id, demo_card_id)
            return
        if (
            demo_value is None
            or demo_value.get_secret_value() != source_value.get_secret_value()
        ):
            self.credential_store.set(demo_owner_id, demo_card_id, source_value)

    def _sync_scenarios(
        self,
        source_owner_id: str,
        demo_owner_id: str,
    ) -> dict[str, str]:
        existing = {
            item.name: item
            for item in self.workspace_repository.list_scenarios(demo_owner_id)
        }
        mapped: dict[str, str] = {}
        for source in self.workspace_repository.list_scenarios(source_owner_id):
            payload = _scenario_payload(source)
            demo = existing.get(source.name)
            if demo is None:
                demo = self.workspace_repository.create_scenario(demo_owner_id, payload)
                existing[demo.name] = demo
            elif _scenario_payload(demo).model_dump(mode="json") != payload.model_dump(
                mode="json"
            ):
                updated = self.workspace_repository.update_scenario(
                    demo.id,
                    demo_owner_id,
                    ScenarioUpdate.model_validate(payload.model_dump()),
                )
                if updated is None:
                    raise RuntimeError("Public Demo Scenario update failed.")
                demo = updated
            mapped[source.id] = demo.id
        return mapped

    def _sync_test_packs(
        self,
        source_owner_id: str,
        demo_owner_id: str,
        scenario_ids: dict[str, str],
    ) -> int:
        existing = {
            item.name: item
            for item in self.workspace_repository.list_packs(demo_owner_id)
        }
        synchronized = 0
        for source in self.workspace_repository.list_packs(source_owner_id):
            items = [
                PackItemInput(
                    scenario_id=scenario_ids[item.scenario.id],
                    enabled=item.enabled,
                )
                for item in sorted(source.items, key=lambda value: value.position)
                if item.scenario.id in scenario_ids
            ]
            payload = TestPackCreate(
                name=source.name,
                description=source.description,
                items=items,
            )
            demo = existing.get(source.name)
            if demo is None:
                demo = self.workspace_repository.create_pack(demo_owner_id, payload)
                existing[demo.name] = demo
            elif _pack_payload(demo).model_dump(mode="json") != payload.model_dump(
                mode="json"
            ):
                updated = self.workspace_repository.update_pack(
                    demo.id,
                    demo_owner_id,
                    TestPackUpdate.model_validate(payload.model_dump()),
                )
                if updated is None:
                    raise RuntimeError("Public Demo Test Pack update failed.")
            synchronized += 1
        return synchronized


def _scenario_payload(item: ScenarioView) -> ScenarioCreate:
    return ScenarioCreate.model_validate(
        item.model_dump(
            exclude={"id", "owner_id", "created_at", "updated_at", "kind"}
        )
    )


def _pack_payload(item: TestPackView) -> TestPackCreate:
    return TestPackCreate(
        name=item.name,
        description=item.description,
        items=[
            PackItemInput(
                scenario_id=pack_item.scenario.id,
                enabled=pack_item.enabled,
            )
            for pack_item in sorted(item.items, key=lambda value: value.position)
        ],
    )


def _json_object(value: str) -> dict[str, object]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("Expected a JSON object.")
    return {str(key): item for key, item in decoded.items()}


def _json_list(value: str) -> list[str]:
    decoded = json.loads(value)
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded]


__all__ = [
    "PUBLIC_DEMO_DISPLAY_NAME",
    "PUBLIC_DEMO_EMAIL",
    "PUBLIC_DEMO_PASSWORD",
    "PUBLIC_DEMO_USER_ID",
    "PublicDemoService",
    "PublicDemoSyncResult",
    "is_public_demo_email",
]
