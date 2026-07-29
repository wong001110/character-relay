"""Application service for persisted trial execution."""

import asyncio
import json
import os
from collections.abc import Callable
from typing import Literal, cast

from pydantic import SecretStr

from echo_masque.admin_runtime import JudgeRuntimeProfile
from echo_masque.config import Settings
from echo_masque.credentials import CredentialStore
from echo_masque.domain import (
    JudgeMode,
    TestKind,
    TestLanguage,
    TrialScenario,
    TrialStatus,
)
from echo_masque.judges import SemanticJudge
from echo_masque.persistence import (
    Repository,
    WorkspaceRepository,
    decode_trial_metadata,
    encode_trial_request,
)
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.providers import (
    ChatProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from echo_masque.services.runtime import RuntimeService
from echo_masque.suites import scenarios_for
from echo_masque.targets import (
    HttpTarget,
    HttpTargetConfig,
    PromptModelConfig,
    PromptModelTarget,
    fragile_target,
    stable_target,
)
from echo_masque.targets.base import TargetAdapter
from echo_masque.testers import AdaptiveTester, AdaptiveTesterConfig
from echo_masque.trials import FAST_PACING, WATCH_PACING, TrialRunner
from echo_masque.workspace import RunSnapshotView, TestPackView

type ProviderFactory = Callable[[str, SecretStr], ChatProvider]


def default_provider_factory(base_url: str, api_key: SecretStr) -> ChatProvider:
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key)


class TrialService:
    def __init__(
        self,
        repository: Repository,
        credential_store: CredentialStore | None = None,
        runtime_service: RuntimeService | None = None,
        provider_factory: ProviderFactory = default_provider_factory,
        *,
        workspace_repository: WorkspaceRepository | None = None,
    ) -> None:
        self.repository = repository
        self.credential_store = credential_store or CredentialStore()
        self.runtime_service = runtime_service or RuntimeService(
            repository,
            Settings(environment="test"),
        )
        self.workspace_repository = workspace_repository or WorkspaceRepository(
            repository.database
        )
        self.provider_factory = provider_factory
        self.runner = TrialRunner()
        self._modes: dict[str, Literal["watch", "fast"]] = {}
        self._adaptive_configs: dict[str, AdaptiveTesterConfig] = {}
        self._judge_profiles: dict[str, JudgeRuntimeProfile] = {}
        self._judge_credentials: dict[str, SecretStr] = {}
        self._run_credentials: dict[str, SecretStr] = {}

    def start(
        self,
        *,
        suite: list[TestKind],
        target_id: str | None = None,
        character_card_id: str | None = None,
        test_pack_id: str | None = None,
        owner_id: str = "local-user",
        mode: Literal["watch", "fast"] = "fast",
        tester_mode: Literal["benchmark", "adaptive"] = "benchmark",
        adaptive_tester: AdaptiveTesterConfig | None = None,
        judge_mode: JudgeMode = JudgeMode.RULES,
        test_language: TestLanguage = TestLanguage.ENGLISH,
        rerun_of: str | None = None,
    ) -> str:
        card_id = character_card_id
        card: CharacterCardRecord | None = None
        if card_id is not None:
            card = self.repository.get_character_card(card_id, owner_id)
            if card is None:
                raise KeyError(card_id)
            target_id = card.target_id
        if target_id is None:
            raise KeyError("missing-target")

        target_record = self.repository.get_target(target_id)
        if target_record is None:
            raise KeyError(target_id)

        pack: TestPackView | None = None
        scenario_payloads: list[dict[str, object]]
        if test_pack_id is not None:
            pack = self.workspace_repository.get_pack(test_pack_id, owner_id)
            if pack is None:
                raise KeyError(test_pack_id)
            selected = [
                item.scenario
                for item in sorted(pack.items, key=lambda value: value.position)
                if item.enabled and item.scenario.language == test_language
            ]
            if not selected:
                raise ValueError(
                    "The selected Test Pack has no enabled scenarios for this Test Language."
                )
            scenarios = tuple(item.to_trial_scenario() for item in selected)
            scenario_payloads = [item.model_dump(mode="json") for item in selected]
            suite_values = [item.category.value for item in selected]
        else:
            scenarios = tuple(
                scenario
                for kind in suite
                for scenario in scenarios_for(kind, language=test_language)
            )
            if not scenarios:
                raise ValueError("At least one test scenario is required.")
            scenario_payloads = [
                {**item.model_dump(mode="json"), "max_turns": 8}
                for item in scenarios
            ]
            suite_values = [item.kind.value for item in scenarios]

        resolved_adaptive = adaptive_tester
        if tester_mode == "adaptive" and resolved_adaptive is None:
            resolved_adaptive = self.runtime_service.adaptive_config()
        if tester_mode == "adaptive" and resolved_adaptive is None:
            raise ValueError(
                "Adaptive Tester is unavailable until Admin configures its runtime and API key."
            )
        if resolved_adaptive is not None and scenario_payloads:
            caps = [
                int(item.get("max_turns", resolved_adaptive.max_turns))
                for item in scenario_payloads
                if isinstance(item.get("max_turns", resolved_adaptive.max_turns), int)
            ]
            if caps:
                resolved_adaptive = resolved_adaptive.model_copy(
                    update={"max_turns": max(1, min(resolved_adaptive.max_turns, min(caps)))}
                )

        judge_profile: JudgeRuntimeProfile | None = None
        judge_credential: SecretStr | None = None
        if judge_mode in {JudgeMode.SEMANTIC, JudgeMode.HYBRID}:
            runtime_config = self.runtime_service.config()
            judge_profile = runtime_config.judge
            judge_credential, _ = self.runtime_service.credential("judge")
            if not judge_profile.enabled or judge_credential is None:
                raise ValueError(
                    "Semantic Judge is unavailable until Admin configures its runtime and API key."
                )

        credential: SecretStr | None = None
        if target_record.target_kind == "prompt_model":
            config = PromptModelConfig.model_validate_json(target_record.config_json)
            if card_id is not None:
                credential = self.credential_store.get(owner_id, card_id)
            if credential is None:
                environment_key = os.getenv(config.api_key_env)
                if environment_key:
                    credential = SecretStr(environment_key)
            if credential is None:
                raise ValueError(
                    "This prompt-model Character Card needs an API key before testing."
                )

        persisted_suite = encode_trial_request(
            suite_values,
            test_language,
            tester_mode=tester_mode,
            judge_mode=judge_mode,
        )
        run = self.repository.create_run(
            target_id=target_id,
            suite=persisted_suite,
            character_card_id=card_id,
        )
        self.workspace_repository.save_run_snapshot(
            run_id=run.id,
            owner_id=owner_id,
            character_card_id=card_id,
            test_pack_id=test_pack_id,
            character=self._character_snapshot(card),
            target=self._target_snapshot(target_record),
            test_pack=(pack.model_dump(mode="json") if pack is not None else {}),
            scenarios=scenario_payloads,
            rerun_of=rerun_of,
        )
        self._modes[run.id] = mode
        if resolved_adaptive is not None:
            self._adaptive_configs[run.id] = resolved_adaptive
        if judge_profile is not None and judge_credential is not None:
            self._judge_profiles[run.id] = judge_profile
            self._judge_credentials[run.id] = judge_credential
        if credential is not None:
            self._run_credentials[run.id] = credential
        return run.id

    def rerun(self, run_id: str, *, owner_id: str = "local-user") -> str:
        source_run = self.repository.get_run(run_id)
        snapshot = self.workspace_repository.get_run_snapshot(run_id, owner_id)
        if source_run is None or snapshot is None:
            raise KeyError(run_id)
        metadata = decode_trial_metadata(source_run.suite_json)
        kinds = [TestKind(item) for item in metadata.suite]
        new_run_id = self.start(
            suite=kinds,
            target_id=source_run.target_id,
            character_card_id=snapshot.character_card_id,
            owner_id=owner_id,
            mode="fast",
            tester_mode=metadata.tester_mode,
            judge_mode=metadata.judge_mode,
            test_language=metadata.test_language,
            rerun_of=run_id,
        )
        self.workspace_repository.save_run_snapshot(
            run_id=new_run_id,
            owner_id=owner_id,
            character_card_id=snapshot.character_card_id,
            test_pack_id=snapshot.test_pack_id,
            character=snapshot.character,
            target=snapshot.target,
            test_pack=snapshot.test_pack,
            scenarios=snapshot.scenarios,
            rerun_of=run_id,
        )
        return new_run_id

    async def execute(self, run_id: str) -> None:
        mode = self._modes.pop(run_id, "fast")
        adaptive_config = self._adaptive_configs.pop(run_id, None)
        judge_profile = self._judge_profiles.pop(run_id, None)
        judge_credential = self._judge_credentials.pop(run_id, None)
        credential = self._run_credentials.pop(run_id, None)
        run = self.repository.get_run(run_id)
        if run is None or run.status == TrialStatus.CANCELLED.value:
            return
        snapshot = self.workspace_repository.get_run_snapshot(run_id)
        target_record = self.repository.get_target(run.target_id)
        if target_record is None and snapshot is None:
            self.repository.set_run_status(
                run_id,
                TrialStatus.FAILED,
                error="Target no longer exists.",
            )
            return

        async def observe(event_type: str, payload: dict[str, object]) -> None:
            scenario = payload.get("scenario_id")
            turn = payload.get("turn_index")
            await asyncio.to_thread(
                self.repository.append_trial_event,
                run_id,
                event_type,
                payload,
                scenario_id=scenario if isinstance(scenario, str) else None,
                turn_index=turn if isinstance(turn, int) else None,
            )

        try:
            self.repository.clear_trial_events(run_id)
            self.repository.set_run_status(run_id, TrialStatus.RUNNING)
            target = self._target_from_snapshot(snapshot, target_record, credential)
            metadata = decode_trial_metadata(run.suite_json)
            adaptive = None
            if metadata.tester_mode == "adaptive":
                if adaptive_config is None:
                    raise ValueError("Adaptive Tester configuration is no longer available.")
                adaptive = AdaptiveTester(
                    config=adaptive_config,
                    provider=self.provider_factory(
                        adaptive_config.base_url,
                        adaptive_config.api_key,
                    ),
                )

            semantic_judge = None
            if metadata.judge_mode in {JudgeMode.SEMANTIC, JudgeMode.HYBRID}:
                if judge_profile is None or judge_credential is None:
                    raise ValueError("Semantic Judge configuration is no longer available.")
                semantic_judge = SemanticJudge(
                    config=judge_profile,
                    provider=self.provider_factory(judge_profile.base_url, judge_credential),
                )

            scenarios = self._scenarios_from_snapshot(snapshot, metadata)
            pacing = WATCH_PACING if mode == "watch" else FAST_PACING
            result = await self.runner.run_suite(
                target,
                scenarios,
                observer=observe,
                pacing=pacing,
                adaptive_tester=adaptive,
                judge_mode=metadata.judge_mode,
                semantic_judge=semantic_judge,
                character_context=self._character_context_from_snapshot(snapshot),
            )
            latest = self.repository.get_run(run_id)
            if latest and latest.status != TrialStatus.CANCELLED.value:
                self.repository.save_result(run_id, result)
        except (ProviderError, ValueError, KeyError) as exc:
            await observe("session_failed", {"message": str(exc)})
            self.repository.set_run_status(run_id, TrialStatus.FAILED, error=str(exc))
        finally:
            self._clear_run_state(run_id)

    def _target_from_snapshot(
        self,
        snapshot: RunSnapshotView | None,
        target_record: TargetRecord | None,
        credential: SecretStr | None,
    ) -> TargetAdapter:
        if snapshot is not None and snapshot.target:
            target = snapshot.target
            return self._target(
                str(target.get("target_kind", "")),
                str(target.get("name", "Snapshot target")),
                json.dumps(target.get("config", {}), ensure_ascii=False),
                credential,
            )
        if target_record is None:
            raise ValueError("Target snapshot is unavailable.")
        return self._target(
            target_record.target_kind,
            target_record.name,
            target_record.config_json,
            credential,
        )

    def _scenarios_from_snapshot(
        self, snapshot: RunSnapshotView | None, metadata: object
    ) -> tuple[TrialScenario, ...]:
        if snapshot is not None and snapshot.scenarios:
            return tuple(TrialScenario.model_validate(item) for item in snapshot.scenarios)
        resolved = cast(object, metadata)
        suite = getattr(resolved, "suite")
        language = getattr(resolved, "test_language")
        kinds = [TestKind(item) for item in suite]
        return tuple(
            scenario
            for kind in kinds
            for scenario in scenarios_for(kind, language=language)
        )

    def _target(
        self,
        target_kind: str,
        target_name: str,
        config_json: str,
        credential: SecretStr | None,
    ) -> TargetAdapter:
        if target_kind == "stable":
            return stable_target()
        if target_kind == "fragile":
            return fragile_target()
        if target_kind == "http":
            return HttpTarget(
                name=target_name,
                config=HttpTargetConfig.model_validate_json(config_json),
            )
        if target_kind == "prompt_model":
            config = PromptModelConfig.model_validate_json(config_json)
            if credential is None:
                environment_key = os.getenv(config.api_key_env)
                if environment_key:
                    credential = SecretStr(environment_key)
            if credential is None:
                raise ValueError("The provider credential is no longer available.")
            return PromptModelTarget(
                config=config,
                provider=self.provider_factory(config.base_url, credential),
            )
        raise ValueError(f"Unsupported persisted target kind: {target_kind}")

    @staticmethod
    def _character_snapshot(card: CharacterCardRecord | None) -> dict[str, object]:
        if card is None:
            return {}
        return {
            "id": card.id,
            "display_name": card.display_name,
            "subtitle": card.subtitle,
            "subject_type": card.subject_type,
            "persona_summary": card.persona_summary,
            "traits": json.loads(card.traits_json),
            "tags": json.loads(card.tags_json),
            "expected_tone": card.expected_tone,
            "forbidden_behaviors": json.loads(card.forbidden_behaviors_json),
            "memory_summary": card.memory_summary,
            "portrait_variant": card.portrait_variant,
            "created_at": card.created_at.isoformat(),
        }

    @staticmethod
    def _target_snapshot(target: TargetRecord) -> dict[str, object]:
        return {
            "id": target.id,
            "name": target.name,
            "target_kind": target.target_kind,
            "config": json.loads(target.config_json),
            "created_at": target.created_at.isoformat(),
        }

    @staticmethod
    def _character_context_from_snapshot(snapshot: RunSnapshotView | None) -> str:
        if snapshot is None or not snapshot.character:
            return "No Character Card profile was supplied. Judge only the scenario contract."
        card = snapshot.character
        return "\n".join(
            (
                f"Name: {card.get('display_name', 'Unknown')}",
                f"Subject type: {card.get('subject_type', 'custom')}",
                f"Subtitle: {card.get('subtitle', '')}",
                f"Persona: {card.get('persona_summary', '')}",
                f"Traits: {', '.join(str(item) for item in card.get('traits', []))}",
                f"Expected tone: {card.get('expected_tone') or 'Not specified'}",
                "Forbidden behaviors: "
                f"{', '.join(str(item) for item in card.get('forbidden_behaviors', []))}",
                f"Memory boundary: {card.get('memory_summary') or 'Not specified'}",
            )
        )

    def cancel(self, run_id: str) -> bool:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status in {TrialStatus.COMPLETED.value, TrialStatus.FAILED.value}:
            return False
        self._clear_run_state(run_id)
        self.repository.set_run_status(run_id, TrialStatus.CANCELLED)
        self.repository.append_trial_event(run_id, "session_cancelled", {})
        return True

    def _clear_run_state(self, run_id: str) -> None:
        self._modes.pop(run_id, None)
        self._adaptive_configs.pop(run_id, None)
        self._judge_profiles.pop(run_id, None)
        self._judge_credentials.pop(run_id, None)
        self._run_credentials.pop(run_id, None)
