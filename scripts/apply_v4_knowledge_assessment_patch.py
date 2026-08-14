from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src/echo_masque/knowledge_route_gate.py"
TEST = ROOT / "tests/test_knowledge_route_assessment_v4.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'KnowledgeRouteStatus = Literal[\n'
        '    "no_eligible_bases",\n'
        '    "disabled",\n'
        '    "matched",\n'
        '    "not_relevant",\n'
        '    "unavailable",\n'
        ']\n\n\n',
        'KnowledgeRouteStatus = Literal[\n'
        '    "no_eligible_bases",\n'
        '    "disabled",\n'
        '    "matched",\n'
        '    "not_relevant",\n'
        '    "unavailable",\n'
        ']\n'
        'KnowledgeAssessmentRoute = Literal["on", "off", "gray"]\n\n\n',
        "assessment route alias",
    )
    marker = '@dataclass(frozen=True, slots=True)\nclass KnowledgeRouteDecision:'
    if text.count(marker) != 1:
        raise RuntimeError("decision marker changed")
    assessment_class = '''@dataclass(frozen=True, slots=True)
class KnowledgeRouteAssessment:
    """Deterministic/sparse/E5 Knowledge evidence with no LLM side effect."""

    status: KnowledgeRouteStatus
    route: KnowledgeAssessmentRoute
    fallback_should_retrieve: bool
    eligible_base_count: int
    best_sparse_score: float = 0.0
    best_dense_score: float = 0.0
    matched_knowledge_base_id: str = ""
    route_labels: tuple[str, ...] = ()
    current_message: str = ""
    normalized_query: str = ""
    is_contextual: bool = False

    @property
    def gray_zone(self) -> bool:
        return self.route == "gray"


'''
    text = text.replace(marker, assessment_class + marker, 1)

    start = text.index('    def decide(\n')
    end = text.index('\n\n__all__ = ', start)
    replacement = '''    def assess(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        query: str,
    ) -> KnowledgeRouteAssessment:
        """Return route evidence without invoking any model Judge."""

        raw_lines = [item.strip() for item in query.splitlines() if item.strip()]
        current_message = raw_lines[-1] if raw_lines else " ".join(query.split())
        is_contextual = len(raw_lines) > 1
        normalized = " ".join(query.split())[:4000]
        eligible = self._eligible_bases(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
        )
        if not self._semantic_enabled:
            return KnowledgeRouteAssessment(
                "disabled",
                "on",
                True,
                len(eligible),
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )
        if not eligible:
            return KnowledgeRouteAssessment(
                "no_eligible_bases",
                "off",
                False,
                0,
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )
        if not normalized:
            return KnowledgeRouteAssessment(
                "not_relevant",
                "off",
                False,
                len(eligible),
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )

        routes = [(base, self._route_text(base)) for base in eligible]
        route_labels = tuple(
            (
                f"{base.name}: {base.description.strip()}"
                if base.description.strip()
                else base.name
            )[:500]
            for base, _ in routes
        )
        sparse_scores = [
            (self._sparse_score(base, route_text, normalized), base)
            for base, route_text in routes
        ]
        best_sparse, sparse_base = max(sparse_scores, key=lambda item: item[0])
        if best_sparse >= _ROUTE_SPARSE_STRONG and not is_contextual:
            return KnowledgeRouteAssessment(
                "matched",
                "on",
                True,
                len(eligible),
                best_sparse_score=round(best_sparse, 6),
                matched_knowledge_base_id=sparse_base.id,
                route_labels=route_labels,
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=False,
            )

        routing = self._routing_judge.runtime.semantic_routing_config()
        try:
            encoder = self._get_encoder()
            query_vector = encoder.embed_query(normalized)
            dense_scores: list[tuple[float, KnowledgeBaseRecord]] = []
            for base, route_text in routes:
                vector = self._route_vector(
                    base=base,
                    route_text=route_text,
                    encoder=encoder,
                )
                dense_scores.append((_cosine(query_vector, vector), base))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            fallback = (
                False
                if routing.enabled and routing.rag_enabled and is_contextual
                else best_sparse >= _ROUTE_SPARSE_STRONG
                if routing.enabled and routing.rag_enabled
                else True
            )
            return KnowledgeRouteAssessment(
                "unavailable",
                "on" if fallback else "off",
                fallback,
                len(eligible),
                best_sparse_score=round(best_sparse, 6),
                matched_knowledge_base_id=sparse_base.id if fallback else "",
                route_labels=route_labels,
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )

        best_dense, dense_base = max(dense_scores, key=lambda item: item[0])
        legacy_matched = best_dense >= _ROUTE_DENSE_MINIMUM or (
            best_dense >= _ROUTE_DENSE_WITH_SPARSE_MINIMUM
            and best_sparse >= _ROUTE_SPARSE_SUPPORT
        )
        common = dict(
            eligible_base_count=len(eligible),
            best_sparse_score=round(best_sparse, 6),
            best_dense_score=round(best_dense, 6),
            matched_knowledge_base_id=dense_base.id,
            route_labels=route_labels,
            current_message=current_message,
            normalized_query=normalized,
            is_contextual=is_contextual,
        )
        if not routing.enabled or not routing.rag_enabled:
            return KnowledgeRouteAssessment(
                "matched" if legacy_matched else "not_relevant",
                "on" if legacy_matched else "off",
                legacy_matched,
                **common,
            )
        if is_contextual:
            return KnowledgeRouteAssessment(
                "not_relevant",
                "gray",
                False,
                **common,
            )
        if best_dense >= routing.rag_on_threshold:
            return KnowledgeRouteAssessment(
                "matched",
                "on",
                True,
                **common,
            )
        if best_dense <= routing.rag_off_threshold and best_sparse < _ROUTE_SPARSE_SUPPORT:
            return KnowledgeRouteAssessment(
                "not_relevant",
                "off",
                False,
                **common,
            )
        return KnowledgeRouteAssessment(
            "matched" if legacy_matched else "not_relevant",
            "gray",
            legacy_matched,
            **common,
        )

    @staticmethod
    def _decision_from_assessment(
        assessment: KnowledgeRouteAssessment,
        *,
        should_retrieve: bool | None = None,
        judge: RagJudgeDecision | None = None,
    ) -> KnowledgeRouteDecision:
        retrieve = (
            assessment.route == "on"
            if should_retrieve is None
            else bool(should_retrieve)
        )
        status: KnowledgeRouteStatus
        if assessment.status in {"disabled", "no_eligible_bases", "unavailable"}:
            status = assessment.status
        else:
            status = "matched" if retrieve else "not_relevant"
        return KnowledgeRouteDecision(
            status,
            retrieve,
            assessment.eligible_base_count,
            best_sparse_score=assessment.best_sparse_score,
            best_dense_score=assessment.best_dense_score,
            matched_knowledge_base_id=(
                assessment.matched_knowledge_base_id if retrieve else ""
            ),
            **KnowledgeRouteGate._judge_values(judge),
        )

    def decide(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        query: str,
    ) -> KnowledgeRouteDecision:
        assessment = self.assess(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
            query=query,
        )
        if not assessment.gray_zone:
            return self._decision_from_assessment(assessment)

        judge = self._routing_judge.decide(
            current_message=assessment.current_message,
            contextual_query=assessment.normalized_query,
            route_labels=assessment.route_labels,
            dense_score=assessment.best_dense_score,
            sparse_score=assessment.best_sparse_score,
        )
        matched = (
            judge.need_knowledge
            if judge is not None
            else assessment.fallback_should_retrieve
        )
        return self._decision_from_assessment(
            assessment,
            should_retrieve=matched,
            judge=judge,
        )
'''
    text = text[:start] + replacement + text[end:]
    text = text.replace(
        '__all__ = ["KnowledgeRouteDecision", "KnowledgeRouteGate", "KnowledgeRouteStatus"]',
        '__all__ = [\n'
        '    "KnowledgeAssessmentRoute",\n'
        '    "KnowledgeRouteAssessment",\n'
        '    "KnowledgeRouteDecision",\n'
        '    "KnowledgeRouteGate",\n'
        '    "KnowledgeRouteStatus",\n'
        ']',
    )
    TARGET.write_text(text, encoding="utf-8")

    TEST.write_text(
        '''from __future__ import annotations\n\nfrom echo_masque.admin_runtime import SemanticRoutingJudgeProfile\nfrom echo_masque.knowledge_route_gate import KnowledgeRouteGate\nfrom echo_masque.persistence import Database, KnowledgeRepository\n\n\nclass GrayEncoder:\n    model_name = "test/gray-e5"\n    dimension = 2\n\n    def embed_query(self, _text: str) -> list[float]:\n        return [1.0, 0.0]\n\n    def embed_passage(self, _text: str) -> list[float]:\n        return [0.5, 0.8660254038]\n\n\nclass FakeRuntime:\n    @staticmethod\n    def semantic_routing_config() -> SemanticRoutingJudgeProfile:\n        return SemanticRoutingJudgeProfile(enabled=True)\n\n\nclass FailingJudge:\n    runtime = FakeRuntime()\n\n    def __init__(self) -> None:\n        self.calls = 0\n\n    def decide(self, **_kwargs):  # type: ignore[no-untyped-def]\n        self.calls += 1\n        raise AssertionError("assess() must never invoke the model Judge")\n\n\ndef repository() -> KnowledgeRepository:\n    database = Database("sqlite://")\n    database.initialize()\n    repo = KnowledgeRepository(database, semantic_enabled=False)\n    base = repo.create_base(\n        owner_id="owner-1",\n        name="Docs",\n        description="Character Relay architecture",\n        scope_type="server",\n        connection_id="connection-1",\n        guild_id="guild-1",\n    )\n    repo.create_document(\n        owner_id="owner-1",\n        knowledge_base_id=base.id,\n        title="Architecture",\n        content="Character Relay runtime architecture and knowledge routing.",\n    )\n    return repo\n\n\ndef gate() -> tuple[KnowledgeRouteGate, FailingJudge]:\n    value = KnowledgeRouteGate(\n        repository(),\n        encoder=GrayEncoder(),\n        semantic_enabled=True,\n    )\n    judge = FailingJudge()\n    value._routing_judge = judge  # type: ignore[assignment]\n    return value, judge\n\n\ndef test_assess_returns_gray_evidence_without_calling_judge() -> None:\n    value, judge = gate()\n    assessment = value.assess(\n        owner_id="owner-1",\n        connection_id="connection-1",\n        guild_id="guild-1",\n        channel_id="channel-1",\n        thread_id="",\n        character_card_id="card-ann",\n        query="How does this architecture work?",\n    )\n\n    assert assessment.route == "gray"\n    assert assessment.gray_zone is True\n    assert assessment.best_dense_score == 0.5\n    assert assessment.route_labels\n    assert assessment.current_message == "How does this architecture work?"\n    assert judge.calls == 0\n\n\ndef test_contextual_assessment_is_one_gray_evidence_record_without_judge() -> None:\n    value, judge = gate()\n    assessment = value.assess(\n        owner_id="owner-1",\n        connection_id="connection-1",\n        guild_id="guild-1",\n        channel_id="channel-1",\n        thread_id="",\n        character_card_id="card-ann",\n        query="previous architecture question\\nwhat about that part?",\n    )\n\n    assert assessment.route == "gray"\n    assert assessment.is_contextual is True\n    assert assessment.fallback_should_retrieve is False\n    assert judge.calls == 0\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
