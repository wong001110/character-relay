from __future__ import annotations

from dataclasses import replace

import pytest
import test_explicit_notes as note_tests

from echo_masque.api.expression_schemas import ExpressionIntent
from echo_masque.expression_intent import ExpressionIntentResolver
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.expression_models import ExpressionUsageRecord
from echo_masque.persistence.expression_repository import ExpressionRepository
from echo_masque.room_sources import scope_key
from echo_masque.smart_output import DiscordSmartOutputView, SmartEmojiPart, SmartTextPart


@pytest.fixture
def env(tmp_path):
    db, rooms, *_ = note_tests.note_environment(tmp_path / "expression.db")
    with db.session() as session:
        session.add(
            PlatformConnectionRecord(
                id="connection",
                owner_id="owner",
                platform="discord",
                display_name="Test",
                status="connected",
            )
        )
        session.commit()
    repository = ExpressionRepository(db)
    for id in ("agree-a", "agree-b", "unrelated"):
        repository.upsert_manual_resource(
            owner_id="owner",
            connection_id="connection",
            guild_id="guild",
            resource_type="emoji",
            resource_id=id,
            name=id,
            description="",
            tags=[],
            format_type="emoji",
            asset_url="",
            animated=False,
            available=True,
            enabled=True,
            semantic_intent="tease" if id == "unrelated" else "agree",
            semantic_emotion="amused" if id == "unrelated" else "pleased",
            semantic_description="",
            aliases=[],
            situations=[],
            avoid_when=[],
            allowed_actions=["inline", "reaction"],
        )
    return db, rooms, ExpressionIntentResolver(db)


def output(action="message", *, intent="agree", fallback=""):
    return DiscordSmartOutputView(
        action=action,
        content=[SmartTextPart(text="I agree.")] if action == "message" else [],
        expression_intent=ExpressionIntent(kind="emoji", intent=intent, emotion="pleased"),
        target_message_id="source",
        fallback_text=fallback,
    )


def test_without_intent_does_not_read_catalogue_or_call_a_model(env, monkeypatch):
    _, _, resolver = env

    def forbidden(*a, **kw):
        raise AssertionError("no catalogue or deployment lookup without expression intent")

    monkeypatch.setattr(resolver.deployments, "deployment_matches_discord_destination", forbidden)
    plain = DiscordSmartOutputView(action="message", content=[SmartTextPart(text="Hello")])
    assert resolver.resolve(plain, note_tests.context()) is plain


def test_resolve_one_scoped_resource_after_generation_and_penalize_actual_recent_use(env):
    db, _, resolver = env
    selected = resolver.resolve(output(), note_tests.context())
    assert selected.expression_resource.resource_key == "emoji:agree-a"
    assert selected.content == [
        SmartTextPart(text="I agree."),
        SmartEmojiPart(emoji="emoji:agree-a"),
    ]
    assert selected.expression_intent is None
    assert selected.expression_resolution == "resolved"
    with db.session() as session:
        session.add(
            ExpressionUsageRecord(
                step_id="delivered-step",
                owner_id="owner",
                scope_id=scope_key(note_tests.SCOPE),
                deployment_id="deployment",
                resource_key="emoji:agree-a",
            )
        )
        session.commit()
    repeated = resolver.resolve(output("react"), note_tests.context())
    assert repeated.emoji_resource_key == "emoji:agree-b"


def test_no_match_keeps_words_or_explicit_fallback_never_invents_resource(env, monkeypatch):
    _, _, resolver = env
    unknown = output(intent="nonexistent quantum pickles")
    unknown.expression_intent = ExpressionIntent(kind="emoji", intent="nonexistent quantum pickles")
    result = resolver.resolve(unknown, note_tests.context())
    assert result.content == [SmartTextPart(text="I agree.")]
    assert result.expression_resolution == "no_match"
    reaction = unknown.model_copy(
        update={"action": "react", "content": [], "fallback_text": "Okay."}
    )
    result = resolver.resolve(reaction, note_tests.context())
    assert result.action == "message" and result.content == [SmartTextPart(text="Okay.")]
    assert result.reply_to_message_id == "source"
    silent = resolver.resolve(
        reaction.model_copy(update={"fallback_text": ""}), note_tests.context()
    )
    assert silent.action == "ignore" and silent.expression_resource is None

    # A nonempty weak result is not permission to decorate with an arbitrary resource.
    import echo_masque.expression_intent as module

    original_rank = module.rank_expression_resources
    scores = []

    def record_rank(*args, **kwargs):
        ranked = original_rank(*args, **kwargs)
        scores.extend(item.score for item in ranked)
        return ranked

    monkeypatch.setattr(module, "rank_expression_resources", record_rank)
    weak = output().model_copy(
        update={
            "expression_intent": ExpressionIntent(
                kind="emoji",
                intent=(
                    "agree ax bx cx dx ex fx gx hx ix jx kx lx mx nx ox px qx rx "
                    "sx tx ux vx wx xx yx"
                ),
            )
        }
    )
    weak_result = resolver.resolve(weak, note_tests.context())
    assert scores and 0 < max(scores) < 0.2
    assert weak_result.expression_resolution == "no_match"
    assert weak_result.content == [SmartTextPart(text="I agree.")]


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "other-owner"),
        ("character_card_id", "other-card"),
        ("connection_id", "other-connection"),
        ("guild_id", "private"),
        ("channel_id", "private"),
        ("thread_id", "private"),
        ("deployment_id", "missing"),
    ],
)
def test_catalogue_never_crosses_role_or_destination_scope(env, field, value):
    _, _, resolver = env
    selected = resolver.resolve(output(), replace(note_tests.context(), **{field: value}))
    assert selected.expression_resource is None
    assert selected.expression_resolution == "scope_unavailable"


def test_revoked_permission_or_paused_role_does_not_resolve(env):
    db, rooms, resolver = env
    rooms.set_access(note_tests.SCOPE, readable=False)
    assert (
        resolver.resolve(output(), note_tests.context()).expression_resolution
        == "scope_unavailable"
    )
    rooms.set_access(note_tests.SCOPE, readable=True)
    with db.session() as session:
        session.get(CharacterDeploymentRecord, "deployment").status = "paused"
        session.commit()
    assert resolver.resolve(output(), note_tests.context()).expression_resource is None


def test_rechecks_current_role_after_ranking(env, monkeypatch):
    import echo_masque.expression_intent as module

    db, _, resolver = env
    original = module.rank_expression_resources

    def revoke(*a, **kw):
        result = original(*a, **kw)
        with db.session() as session:
            session.get(CharacterDeploymentRecord, "deployment").status = "paused"
            session.commit()
        return result

    monkeypatch.setattr(module, "rank_expression_resources", revoke)
    assert (
        resolver.resolve(output(), note_tests.context()).expression_resolution
        == "scope_unavailable"
    )
