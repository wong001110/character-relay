from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "src/echo_masque/context_layer.py"
RESOLVER = ROOT / "src/echo_masque/api/routes/smart_participation_v4.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def patch_context() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "            ):\n                if mode == \"off\":\n                    no_hit_gate = self._route_decision(\n",
        "            ):\n                no_hit_gate: KnowledgeRouteDecision | None\n                if mode == \"off\":\n                    no_hit_gate = self._route_decision(\n",
        "context no-hit optional annotation",
    )
    CONTEXT.write_text(text, encoding="utf-8")


def patch_resolver() -> None:
    text = RESOLVER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import hmac\nimport logging\nfrom typing import Annotated, cast\n",
        "import hmac\nimport logging\nfrom collections.abc import Mapping\nfrom typing import Annotated, cast\n",
        "mapping import",
    )
    text = replace_once(
        text,
        "    ParticipationContextCandidate,\n    ParticipationContextResult,\n    ParticipationContextReranker,\n",
        "    ParticipationContextCandidate,\n    ParticipationContextPlanItem,\n    ParticipationContextResult,\n    ParticipationContextReranker,\n",
        "context plan item import",
    )
    text = replace_once(
        text,
        "from echo_masque.persistence.conversation_graph_repository import ConversationGraphRepository\n",
        "from echo_masque.persistence.conversation_graph_repository import ConversationGraphRepository\n"
        "from echo_masque.persistence.deployment_models import CharacterDeploymentRecord\n",
        "deployment record import",
    )
    text = replace_once(
        text,
        "    records_by_id: dict[str, object],\n",
        "    records_by_id: Mapping[str, CharacterDeploymentRecord],\n",
        "durable mapping type",
    )
    text = replace_once(
        text,
        "def _plan_views(\n    plan: tuple[ParticipationShadowPlanItem, ...] | tuple[object, ...],\n) -> list[SmartParticipationSpeakerPlanItem]:\n",
        "def _plan_views(\n    plan: tuple[ParticipationShadowPlanItem, ...]\n    | tuple[ParticipationContextPlanItem, ...],\n) -> list[SmartParticipationSpeakerPlanItem]:\n",
        "plan views union",
    )
    insertion_marker = "\n\n@router.post(\n    \"/resolve\",\n"
    helper = '''\n\ndef _normalize_shadow_plan(\n    plan: tuple[ParticipationShadowPlanItem, ...],\n) -> tuple[ParticipationContextPlanItem, ...]:\n    return tuple(\n        ParticipationContextPlanItem(\n            deployment_id=item.deployment_id,\n            turn_role=item.turn_role,\n            reason=item.reason,\n        )\n        for item in plan\n    )\n'''
    if "def _normalize_shadow_plan(" not in text:
        text = replace_once(
            text,
            insertion_marker,
            helper + insertion_marker,
            "normalize shadow plan helper",
        )
    text = replace_once(
        text,
        "    effective_plan = context_result.plan if context_active else shadow_result.plan\n\n"
        "    utility_result = ParticipationFinalUtilityResult(\n        tuple(effective_plan),\n",
        "    effective_plan: tuple[ParticipationContextPlanItem, ...] = (\n"
        "        context_result.plan\n"
        "        if context_active\n"
        "        else _normalize_shadow_plan(shadow_result.plan)\n"
        "    )\n\n"
        "    utility_result = ParticipationFinalUtilityResult(\n        effective_plan,\n",
        "effective plan normalization",
    )
    text = replace_once(
        text,
        "            plan=tuple(\n                # Both plan types expose the same bounded fields.\n"
        "                cast(object, item) for item in effective_plan\n"
        "            ),  # type: ignore[arg-type]\n",
        "            plan=effective_plan,\n",
        "final utility normalized plan",
    )
    text = replace_once(
        text,
        "            effective_plan = utility_result.plan\n\n"
        "    speaker_authoritative = settings.smart_participation_v4_speaker_mode == \"active\"\n"
        "    shadow_plan = context_result.plan if (graph_enabled or learned_enabled) else shadow_result.plan\n",
        "            effective_plan = utility_result.plan\n\n"
        "    speaker_authoritative = settings.smart_participation_v4_speaker_mode == \"active\"\n"
        "    shadow_plan: tuple[ParticipationContextPlanItem, ...] = (\n"
        "        context_result.plan\n"
        "        if (graph_enabled or learned_enabled)\n"
        "        else _normalize_shadow_plan(shadow_result.plan)\n"
        "    )\n",
        "shadow plan normalization",
    )
    RESOLVER.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_context()
    patch_resolver()
