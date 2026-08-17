from __future__ import annotations

from dataclasses import dataclass

from echo_masque.character_recall import CharacterRecallBundle, CharacterRecallItem
from echo_masque.recall_media_connector_runtime import RecallAwareMediaDiscordConnectorRuntime


@dataclass
class _Freshness:
    freshness_status: str


class _FreshnessRepo:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, memory_id: str) -> _Freshness | None:
        value = self.values.get(memory_id)
        return _Freshness(value) if value is not None else None


def test_stale_synthesized_memory_is_removed_from_auto_recall() -> None:
    runtime = object.__new__(RecallAwareMediaDiscordConnectorRuntime)
    runtime.memory_freshness = _FreshnessRepo({"synth-stale": "stale"})  # type: ignore[assignment]
    bundle = CharacterRecallBundle(
        items=(
            CharacterRecallItem(
                origin="core",
                ref="core-1",
                content="Durable preference.",
                score=0.9,
                reason="core_priority",
            ),
            CharacterRecallItem(
                origin="synthesized",
                ref="synth-stale",
                content="A time-sensitive old plan.",
                score=0.8,
                reason="high_confidence_semantic_memory",
            ),
            CharacterRecallItem(
                origin="synthesized",
                ref="synth-untracked",
                content="A still-usable synthesized fact.",
                score=0.75,
                reason="high_confidence_semantic_memory",
            ),
        )
    )

    filtered = runtime._fresh_for_auto_recall(bundle)

    assert [item.ref for item in filtered.items] == ["core-1", "synth-untracked"]


def test_fresh_synthesized_memory_remains_eligible_for_auto_recall() -> None:
    runtime = object.__new__(RecallAwareMediaDiscordConnectorRuntime)
    runtime.memory_freshness = _FreshnessRepo({"synth-fresh": "fresh"})  # type: ignore[assignment]
    bundle = CharacterRecallBundle(
        items=(
            CharacterRecallItem(
                origin="synthesized",
                ref="synth-fresh",
                content="Current synthesized fact.",
                score=0.8,
                reason="high_confidence_semantic_memory",
            ),
        )
    )

    assert runtime._fresh_for_auto_recall(bundle).items == bundle.items
