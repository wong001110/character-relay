from datetime import UTC, datetime
from os import environ
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import inspect, select
from sqlalchemy.engine import make_url

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
)
from echo_masque.knowledge_fabric_policy import (
    corpus_is_effectively_available,
    may_access_server_scope,
    may_manage_global_library,
    overlay_mode_or_inherit,
)
from echo_masque.knowledge_fabric_query import (
    KnowledgeQueryHit,
    KnowledgeQueryRequest,
    KnowledgeQueryResult,
)
from echo_masque.knowledge_fabric_rendered_collection import RenderedCollectionAnalysis
from echo_masque.knowledge_fabric_website_sync import WebsiteSyncResult
from echo_masque.persistence import Database
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCorpusRecord,
    KnowledgeSourceRecord,
)
from echo_masque.persistence.knowledge_fabric_repository import (
    OWNER_SERVER,
    OWNER_SYSTEM,
    OWNER_USER,
    VISIBILITY_GLOBAL,
)
from echo_masque.persistence.models import AuditEventRecord
from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord
from echo_masque.persistence.server_access_models import DiscordServerAccessRecord
from echo_masque.public_demo import PUBLIC_DEMO_EMAIL, PUBLIC_DEMO_PASSWORD

PASSWORD = "KnowledgeFabric2026!"
SUPER_EMAIL = "fabric-super@example.com"


def settings(path: Path, *, public_demo_enabled: bool = False) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=SUPER_EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        public_demo_enabled=public_demo_enabled,
        request_limit_per_minute=1000,
    )


def _destructive_postgres_test_url() -> str:
    postgres_url = environ.get("ECHO_MASQUE_TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("ECHO_MASQUE_TEST_POSTGRES_URL is not configured")
    parsed = make_url(postgres_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "echo_masque_test":
        pytest.fail("PostgreSQL Fabric tests only reset echo_masque_test.")
    if environ.get("ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS") != "yes":
        pytest.fail("Set ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS=yes.")
    return postgres_url


def login(client: TestClient, email: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def test_api_lifespan_does_not_start_fabric_background_workers_by_default(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "background-default-off.db"))

    with TestClient(app):
        assert app.state.knowledge_fabric_external_sync_report_retention._task is None
        assert app.state.knowledge_fabric_external_sync_scheduler._task is None
        assert app.state.knowledge_fabric_invalidation_worker._task is None


def register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["user"]["id"])


def test_retired_knowledge_routes_and_runtime_state_are_absent(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "retired-knowledge.db"))
    client = TestClient(app)

    assert client.get("/api/knowledge/bases").status_code == 404
    assert not hasattr(app.state, "knowledge_repository")
    assert not hasattr(app.state, "server_wiki_v3_repository")
    assert not hasattr(app.state, "knowledge_checkpoint_v3_repository")
    assert not hasattr(app.state, "knowledge_consolidation_v3_service")


def test_postgresql_app_uses_fabric_and_has_no_legacy_knowledge_surface() -> None:
    database_url = _destructive_postgres_test_url()
    database = Database(database_url)
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    app = create_app(
        Settings(
            environment="test",
            database_url=database_url,
            legacy_local_user_enabled=False,
            public_registration_enabled=True,
            bootstrap_admin_email=SUPER_EMAIL,
            bootstrap_admin_password=SecretStr(PASSWORD),
            credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
            request_limit_per_minute=1000,
        )
    )
    client = TestClient(app)
    login(client, SUPER_EMAIL)

    scope = bootstrap_scope(client, workspace_id="postgres-guild")
    assert scope["workspace_id"] == "postgres-guild"
    assert client.get("/api/knowledge/bases").status_code == 404
    assert not hasattr(app.state, "knowledge_repository")
    assert not hasattr(app.state, "server_wiki_v3_repository")


def bootstrap_scope(admin: TestClient, *, workspace_id: str = "guild-a") -> dict[str, object]:
    response = admin.post(
        "/api/knowledge-fabric/admin/server-scopes",
        json={
            "platform": "discord",
            "connection_id": "connection-a",
            "workspace_id": workspace_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_global_corpus(admin: TestClient) -> dict[str, object]:
    response = admin.post(
        "/api/knowledge-fabric/admin/corpora",
        json={"name": "World Canon", "description": "Shared, one physical corpus."},
    )
    assert response.status_code == 201, response.text
    return response.json()


def effective_corpus_ids(manager: TestClient, scope_id: object) -> set[object]:
    response = manager.get(f"/api/knowledge-fabric/server-scopes/{scope_id}/corpora")
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


class _QueryInspectorEngine:
    def __init__(self) -> None:
        self.requests: list[KnowledgeQueryRequest] = []

    def query(self, request: KnowledgeQueryRequest) -> KnowledgeQueryResult:
        self.requests.append(request)
        return KnowledgeQueryResult(
            mode=request.mode,
            accessible_corpus_count=1,
            freshness_status="not_requested",
            hits=(
                KnowledgeQueryHit(
                    evidence_unit_id="evidence-1",
                    corpus_id="corpus-1",
                    source_version_id="version-1",
                    evidence_locator="https://example.test/source#p1",
                    document_title="Safe title",
                    text_content="Scoped evidence only.",
                    authority_profile="standard",
                    channels=("sparse",),
                ),
            ),
        )


class _RenderedCollectionAnalyzer:
    def __init__(self, hosts: tuple[str, ...]) -> None:
        self.hosts = hosts
        self.calls: list[tuple[str, str]] = []

    async def analyze(self, *, source_id: str, locator: str) -> RenderedCollectionAnalysis:
        self.calls.append((source_id, locator))
        return RenderedCollectionAnalysis(source_id=source_id, candidate_hosts=self.hosts)


def test_scope_authority_is_explicit_and_never_inferred_from_legacy_access(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "scope-authority.db"))
    admin = TestClient(app)
    manager = TestClient(app)
    legacy_only = TestClient(app)
    generic_admin = TestClient(app)
    login(admin, SUPER_EMAIL)
    manager_id = register(manager, "scope-manager@example.com")
    legacy_id = register(legacy_only, "legacy-only@example.com")
    login(manager, "scope-manager@example.com")
    login(legacy_only, "legacy-only@example.com")

    app.state.auth_repository.create_user(
        email="ordinary-admin@example.com",
        display_name="Ordinary Admin",
        password_hash=app.state.auth_service.passwords.hash(PASSWORD),
        role="admin",
    )
    login(generic_admin, "ordinary-admin@example.com")
    assert (
        generic_admin.post(
            "/api/knowledge-fabric/admin/server-scopes",
            json={
                "platform": "discord",
                "connection_id": "connection-a",
                "workspace_id": "guild-a",
            },
        ).status_code
        == 403
    )

    scope = bootstrap_scope(admin)
    repeated = bootstrap_scope(admin)
    assert repeated["id"] == scope["id"]
    granted = admin.put(
        f"/api/knowledge-fabric/admin/server-scopes/{scope['id']}/administrators/{manager_id}"
    )
    assert granted.status_code == 200, granted.text

    # The old join-code access table contains a known matching Discord tuple but it is not
    # an authorization input to the Knowledge Fabric scope.
    with app.state.database.session() as session:
        session.add(
            DiscordServerAccessRecord(
                id="legacy-access",
                user_id=legacy_id,
                connection_id="connection-a",
                guild_id="guild-a",
                access_source="join_code",
            )
        )
        session.commit()

    assert [item["id"] for item in manager.get("/api/knowledge-fabric/server-scopes").json()] == [
        scope["id"]
    ]
    assert legacy_only.get("/api/knowledge-fabric/server-scopes").json() == []
    known = legacy_only.get(f"/api/knowledge-fabric/server-scopes/{scope['id']}/corpora")
    random = legacy_only.get("/api/knowledge-fabric/server-scopes/no-such-scope/corpora")
    assert known.status_code == random.status_code == 404
    assert known.json() == random.json()

    removed = admin.delete(
        f"/api/knowledge-fabric/admin/server-scopes/{scope['id']}/administrators/{manager_id}"
    )
    assert removed.status_code == 204
    assert (
        manager.get(f"/api/knowledge-fabric/server-scopes/{scope['id']}/corpora").status_code
        == 404
    )


def test_global_grants_and_overlay_are_scope_bound_without_corpus_copy(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "grant-overlay.db"))
    admin = TestClient(app)
    manager = TestClient(app)
    second_manager = TestClient(app)
    login(admin, SUPER_EMAIL)
    manager_id = register(manager, "manager-a@example.com")
    second_manager_id = register(second_manager, "manager-b@example.com")
    login(manager, "manager-a@example.com")
    login(second_manager, "manager-b@example.com")

    scope_a = bootstrap_scope(admin, workspace_id="guild-a")
    scope_b = bootstrap_scope(admin, workspace_id="guild-b")
    for scope, user_id in ((scope_a, manager_id), (scope_b, second_manager_id)):
        response = admin.put(
            f"/api/knowledge-fabric/admin/server-scopes/{scope['id']}/administrators/{user_id}"
        )
        assert response.status_code == 200
    corpus = create_global_corpus(admin)

    local = manager.post(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/corpora",
        json={"name": "Guild A AU", "description": "Private scope overlay material."},
    )
    assert local.status_code == 201, local.text
    assert local.json()["owner_type"] == OWNER_SERVER
    assert local.json()["owner_id"] == scope_a["id"]
    assert local.json()["visibility"] == "private"
    assert (
        manager.post(
            f"/api/knowledge-fabric/server-scopes/{scope_b['id']}/corpora",
            json={"name": "Forbidden", "description": ""},
        ).status_code
        == 404
    )

    available = manager.get(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/available-global-corpora"
    )
    assert [item["id"] for item in available.json()] == [corpus["id"]]
    access = manager.get(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/access"
    )
    assert access.status_code == 200, access.text
    assert access.json() == [
        {"corpus_id": corpus["id"], "enabled": False, "overlay_mode": "inherit"}
    ]
    grant = manager.put(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/{corpus['id']}/grant",
        json={"enabled": True},
    )
    assert grant.status_code == 200, grant.text
    assert manager.get(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/access"
    ).json() == [{"corpus_id": corpus["id"], "enabled": True, "overlay_mode": "inherit"}]
    effective = manager.get(f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/corpora")
    assert {item["id"] for item in effective.json()} == {corpus["id"], local.json()["id"]}
    with app.state.database.session() as session:
        global_record = session.scalar(
            select(KnowledgeCorpusRecord).where(KnowledgeCorpusRecord.id == corpus["id"])
        )
        server_record = session.scalar(
            select(KnowledgeCorpusRecord).where(
                KnowledgeCorpusRecord.owner_id == scope_a["id"]
            )
        )
        assert global_record is not None
        assert server_record is not None
        assert len(
            list(
                session.scalars(
                    select(KnowledgeCorpusRecord).where(KnowledgeCorpusRecord.name == "World Canon")
                )
            )
        ) == 1

    disabled = manager.put(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/{corpus['id']}/grant",
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert corpus["id"] not in effective_corpus_ids(manager, scope_a["id"])
    assert (
        manager.put(
            f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/{corpus['id']}/grant",
            json={"enabled": True},
        ).status_code
        == 200
    )
    denied = manager.put(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/{corpus['id']}/overlay",
        json={"mode": "deny"},
    )
    assert denied.status_code == 200
    assert corpus["id"] not in effective_corpus_ids(manager, scope_a["id"])
    assert manager.get(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/access"
    ).json() == [{"corpus_id": corpus["id"], "enabled": True, "overlay_mode": "deny"}]
    restored = manager.put(
        f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/{corpus['id']}/overlay",
        json={"mode": "override"},
    )
    assert restored.status_code == 200
    assert corpus["id"] in effective_corpus_ids(manager, scope_a["id"])
    assert (
        second_manager.put(
            f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/{corpus['id']}/overlay",
            json={"mode": "augment"},
        ).status_code
        == 404
    )
    assert (
        second_manager.get(
            f"/api/knowledge-fabric/server-scopes/{scope_a['id']}/global-corpora/access"
        ).status_code
        == 404
    )


def test_source_privacy_audit_and_public_demo_boundary(tmp_path: Path) -> None:
    database_path = tmp_path / "sources-demo.db"
    normal_settings = settings(database_path)
    app = create_app(normal_settings)
    admin = TestClient(app)
    manager = TestClient(app)
    login(admin, SUPER_EMAIL)
    manager_id = register(manager, "source-manager@example.com")
    login(manager, "source-manager@example.com")
    scope = bootstrap_scope(admin)
    assert (
        admin.put(
            f"/api/knowledge-fabric/admin/server-scopes/{scope['id']}/administrators/{manager_id}"
        ).status_code
        == 200
    )
    corpus = create_global_corpus(admin)
    source = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/sources",
        json={
            "source_type": "website",
            "locator": "https://docs.example.test/guide#introduction",
            "parser_profile": {"format": "html"},
        },
    )
    assert source.status_code == 201, source.text
    assert source.json()["locator"] == "https://docs.example.test/guide#introduction"
    assert (
        admin.post(
            f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/sources",
            json={"source_type": "website", "locator": "https://key:secret@example.test/private"},
        ).status_code
        == 422
    )
    assert (
        manager.get(f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/sources").status_code
        == 403
    )
    with app.state.database.session() as session:
        metadata = [record.metadata_json for record in session.scalars(select(AuditEventRecord))]
    assert all("docs.example.test" not in item for item in metadata)

    demo_app = create_app(settings(database_path, public_demo_enabled=True))
    demo = TestClient(demo_app)
    response = demo.post(
        "/api/auth/login",
        json={"email": PUBLIC_DEMO_EMAIL, "password": PUBLIC_DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert demo.get("/api/knowledge-fabric/server-scopes").json() == []
    blocked = demo.post(
        "/api/knowledge-fabric/admin/server-scopes",
        json={"platform": "discord", "connection_id": "demo", "workspace_id": "demo"},
    )
    assert blocked.status_code == 403
    assert demo.get(f"/api/knowledge-fabric/server-scopes/{scope['id']}/corpora").status_code == 404
    assert (
        demo.get(
            f"/api/knowledge-fabric/server-scopes/{scope['id']}/global-corpora/access"
        ).status_code
        == 404
    )
    assert (
        demo.post(
            f"/api/knowledge-fabric/admin/sources/{source.json()['id']}/derived-work/retry"
        ).status_code
        == 403
    )


def test_lifecycle_keeps_system_and_server_scope_data_but_removes_user_membership(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "lifecycle.db"))
    fabric = app.state.knowledge_fabric_repository
    user = app.state.auth_repository.create_user(
        email="fabric-delete@example.com",
        display_name="Fabric Delete",
        password_hash=app.state.auth_service.passwords.hash(PASSWORD),
    )
    other = app.state.auth_repository.create_user(
        email="fabric-other@example.com",
        display_name="Fabric Other",
        password_hash=app.state.auth_service.passwords.hash(PASSWORD),
    )
    scope = fabric.ensure_server_scope(
        platform="discord", connection_id="connection-a", workspace_id="guild-a"
    )
    fabric.add_server_administrator(server_scope_id=scope.id, user_id=user.id)
    fabric.add_server_administrator(server_scope_id=scope.id, user_id=other.id)
    system_corpus = fabric.create_system_global_corpus(
        name="System", description="", default_authority_profile="standard", status="active"
    )
    server_corpus = fabric.create_server_local_corpus(
        server_scope_id=scope.id,
        name="Server",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    user_corpus = KnowledgeCorpusRecord(
        id="user-corpus",
        name="User",
        description="",
        owner_type=OWNER_USER,
        owner_id=user.id,
        visibility="private",
        default_authority_profile="standard",
        status="active",
    )
    with app.state.database.session() as session:
        session.add(user_corpus)
        session.add(
            KnowledgeSourceRecord(
                id="user-source",
                corpus_id=user_corpus.id,
                source_type="website",
                locator="https://user.example.test/",
            )
        )
        session.commit()

    deleted = app.state.account_lifecycle_service.delete_account(
        user.id,
        email=user.email,
        actor_user_id=None,
    )
    assert deleted["knowledge_fabric_corpora"] == 1
    assert fabric.get_server_scope(scope.id) is not None
    assert fabric.get_corpus(system_corpus.id) is not None
    assert fabric.get_corpus(server_corpus.id) is not None
    assert fabric.get_corpus(user_corpus.id) is None
    assert not fabric.is_server_administrator(server_scope_id=scope.id, user_id=user.id)
    assert fabric.is_server_administrator(server_scope_id=scope.id, user_id=other.id)


def test_super_admin_operational_source_view_is_redacted_and_source_backed(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "operational-source.db"))
    admin = TestClient(app)
    ordinary = TestClient(app)
    login(admin, SUPER_EMAIL)
    register(ordinary, "ordinary-operator@example.com")
    login(ordinary, "ordinary-operator@example.com")
    corpus = create_global_corpus(admin)
    source = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/sources",
        json={
            "source_type": "website_public_https",
            "locator": "https://example.test/guide",
            "authority_profile": "official",
        },
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    schedule = admin.put(
        f"/api/knowledge-fabric/admin/sources/{source_id}/external-sync-schedule",
        json={"enabled": True, "interval_seconds": 900},
    )
    assert schedule.status_code == 200, schedule.text
    app.state.knowledge_fabric_external_sync_repository.record_outcome(
        source_id=source_id,
        outcome="unchanged",
        checked_at=datetime(2026, 8, 26, tzinfo=UTC),
    )

    response = admin.get(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/operational-sources"
    )
    assert response.status_code == 200, response.text
    [operational] = response.json()
    assert operational["id"] == source_id
    assert operational["corpus_id"] == corpus["id"]
    assert operational["source_type"] == "website_public_https"
    assert operational["authority_profile"] == "official"
    assert operational["enabled"] is True
    assert operational["status"] == "registered"
    assert operational["last_checked_at"].startswith("2026-08-26T00:00:00")
    assert operational["last_changed_at"] is None
    assert operational["external_sync"] is not None
    assert operational["external_sync"]["last_outcome"] == "unchanged"
    assert operational["external_sync"]["last_error_code"] is None
    assert operational["external_schedule"] is not None
    assert operational["external_schedule"]["enabled"] is True
    assert operational["external_schedule"]["interval_seconds"] == 900
    assert operational["external_schedule"]["last_error_code"] is None
    assert operational["site_collection_summary"] is None
    assert operational["sync_run_reports"] == []
    assert operational["derived_work"] == {"pending": 0, "running": 0, "failed": 0}
    assert "locator" not in operational
    assert "access_profile" not in operational
    assert (
        ordinary.get(
            f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/operational-sources"
        ).status_code
        == 403
    )
    retry = admin.post(f"/api/knowledge-fabric/admin/sources/{source_id}/derived-work/retry")
    assert retry.status_code == 200, retry.text
    assert retry.json() == {"pending": 0, "running": 0, "failed": 0}
    with app.state.database.session() as session:
        retry_event = session.scalar(
            select(AuditEventRecord).where(
                AuditEventRecord.action == "knowledge_fabric.derived_work_retry_requested"
            )
        )
    assert retry_event is not None
    assert retry_event.resource_id == source_id
    assert retry_event.metadata_json == '{"requeued_count":0}'
    assert (
        ordinary.post(f"/api/knowledge-fabric/admin/sources/{source_id}/derived-work/retry").status_code
        == 403
    )


def test_rendered_collection_recipe_requires_bootstrap_observed_hosts(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "rendered-collection-api.db"))
    admin = TestClient(app)
    ordinary = TestClient(app)
    login(admin, SUPER_EMAIL)
    register(ordinary, "rendered-collection-reader@example.com")
    login(ordinary, "rendered-collection-reader@example.com")
    corpus = create_global_corpus(admin)
    source = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/sources",
        json={
            "source_type": WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
            "locator": "https://example.test/wiki",
            "authority_profile": "official",
        },
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    analyzer = _RenderedCollectionAnalyzer(("api.example.test", "cdn.example.test"))
    app.state.knowledge_fabric_rendered_collection_analyzer = analyzer

    analysis = admin.post(
        f"/api/knowledge-fabric/admin/sources/{source_id}/rendered-collection-analysis"
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json() == {
        "source_id": source_id,
        "candidate_hosts": ["api.example.test", "cdn.example.test"],
    }
    configured = admin.put(
        f"/api/knowledge-fabric/admin/sources/{source_id}/rendered-collection-profile",
        json={
            "enabled": True,
            "allowed_hosts": ["api.example.test"],
            "page_limit": 12,
            "max_depth": 2,
        },
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["parser_profile"] == {
        "collection_render_hosts": "api.example.test",
        "collection_render_max_depth": "2",
        "collection_render_page_limit": "12",
        "collection_renderer": "browser",
    }
    rejected = admin.put(
        f"/api/knowledge-fabric/admin/sources/{source_id}/rendered-collection-profile",
        json={
            "enabled": True,
            "allowed_hosts": ["unseen.example.test"],
            "page_limit": 12,
            "max_depth": 2,
        },
    )
    assert rejected.status_code == 422
    assert "observed" in rejected.json()["detail"]
    assert len(analyzer.calls) == 3
    assert (
        ordinary.post(
            f"/api/knowledge-fabric/admin/sources/{source_id}/rendered-collection-analysis"
        ).status_code
        == 403
    )
    with app.state.database.session() as session:
        audit_metadata = [
            event.metadata_json
            for event in session.scalars(
                select(AuditEventRecord).where(
                    AuditEventRecord.action
                    == "knowledge_fabric.rendered_collection_profile_updated"
                )
            )
        ]
    assert audit_metadata == [
        '{"approved_external_host_count":1,"enabled":true,"max_depth":2,"page_limit":12}'
    ]


def test_global_operational_source_view_exposes_safe_site_collection_sync_summary(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "collection-summary.db"))
    admin = TestClient(app)
    login(admin, SUPER_EMAIL)
    corpus = create_global_corpus(admin)
    source = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/sources",
        json={
            "source_type": WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
            "locator": "https://example.test/wiki",
            "authority_profile": "official",
        },
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    collections = app.state.knowledge_fabric_site_collection_repository
    generation = collections.begin_generation(source_id)
    collections.reconcile_discovered_pages(
        source_id=source_id,
        generation=generation,
        pages=(
            ("https://example.test/wiki", "root_link", "https://example.test/wiki"),
            ("https://example.test/amber", "root_link", "https://example.test/wiki"),
        ),
    )
    collections.record_page_outcome(
        source_id=source_id,
        locator="https://example.test/wiki",
        outcome="changed",
        checked_at=datetime(2026, 8, 28, tzinfo=UTC),
    )
    collections.record_page_outcome(
        source_id=source_id,
        locator="https://example.test/amber",
        outcome="failed",
        error_code="fetch_failed",
        checked_at=datetime(2026, 8, 28, tzinfo=UTC),
    )
    collections.complete_generation(source_id=source_id, generation=generation)

    response = admin.get(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/operational-sources"
    )

    assert response.status_code == 200, response.text
    [operational] = response.json()
    summary = operational["site_collection_summary"]
    assert summary is not None
    assert summary["source_id"] == source_id
    assert summary["last_completed_at"] is not None
    assert summary["available_page_count"] == 2
    assert summary["removed_page_count"] == 0
    assert summary["checked_page_count"] == 2
    assert summary["failed_page_count"] == 1
    assert "locator" not in summary


def test_global_operational_source_view_exposes_expiring_redacted_sync_reports(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "sync-report-view.db"))
    admin = TestClient(app)
    login(admin, SUPER_EMAIL)
    corpus = create_global_corpus(admin)
    source = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/sources",
        json={
            "source_type": WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
            "locator": "https://example.test/wiki",
            "authority_profile": "official",
        },
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    app.state.knowledge_fabric_external_sync_run_repository.record_completed(
        source_id=source_id,
        started_at=datetime(2026, 8, 28, tzinfo=UTC),
        completed_at=datetime(2026, 8, 28, 0, 0, 9, tzinfo=UTC),
        result=WebsiteSyncResult(
            outcome="changed",
            discovered_page_count=2,
            changed_page_count=1,
            unchanged_page_count=1,
            admitted_image_count=1,
        ),
    )

    response = admin.get(
        f"/api/knowledge-fabric/admin/corpora/{corpus['id']}/operational-sources"
    )

    assert response.status_code == 200, response.text
    [operational] = response.json()
    [report] = operational["sync_run_reports"]
    assert report == {
        "id": report["id"],
        "source_id": source_id,
        "outcome": "changed",
        "error_code": None,
        "started_at": "2026-08-28T00:00:00Z",
        "completed_at": "2026-08-28T00:00:09Z",
        "discovered_page_count": 2,
        "changed_page_count": 1,
        "unchanged_page_count": 1,
        "failed_page_count": 0,
        "removed_page_count": 0,
        "admitted_image_count": 1,
    }
    assert "locator" not in report
    assert "etag" not in report


def test_query_inspector_is_scope_bound_bounded_and_public_demo_denied(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "query-inspector.db", public_demo_enabled=True))
    admin = TestClient(app)
    manager = TestClient(app)
    demo = TestClient(app)
    login(admin, SUPER_EMAIL)
    manager_id = register(manager, "query-manager@example.com")
    login(manager, "query-manager@example.com")
    response = demo.post(
        "/api/auth/login",
        json={"email": PUBLIC_DEMO_EMAIL, "password": PUBLIC_DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    scope = bootstrap_scope(admin)
    assert (
        admin.put(
            f"/api/knowledge-fabric/admin/server-scopes/{scope['id']}/administrators/{manager_id}"
        ).status_code
        == 200
    )
    engine = _QueryInspectorEngine()
    app.state.knowledge_query_engine = engine

    response = manager.post(
        f"/api/knowledge-fabric/server-scopes/{scope['id']}/query-inspector",
        json={"query": "Klee", "mode": "overview", "as_of": "2026-08-26T00:00:00Z"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["hits"] == [
        {
            "evidence_unit_id": "evidence-1",
            "corpus_id": "corpus-1",
            "source_version_id": "version-1",
            "evidence_locator": "https://example.test/source#p1",
            "document_title": "Safe title",
            "text_content": "Scoped evidence only.",
            "authority_profile": "standard",
            "channels": ["sparse"],
        }
    ]
    assert engine.requests == [
        KnowledgeQueryRequest(
            server_scope_id=str(scope["id"]),
            query="Klee",
            mode="overview",
            candidate_limit=4,
            result_limit=4,
            as_of=datetime(2026, 8, 26, tzinfo=UTC),
        )
    ]
    assert (
        manager.post(
            f"/api/knowledge-fabric/server-scopes/{scope['id']}/query-inspector",
            json={"query": "Klee", "mode": "invented"},
        ).status_code
        == 422
    )
    assert (
        demo.post(
            f"/api/knowledge-fabric/server-scopes/{scope['id']}/query-inspector",
            json={"query": "Klee", "mode": "overview"},
        ).status_code
        == 403
    )


def test_database_bootstrap_registers_all_phase2_models_and_records_revision(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "fresh-fabric.db"
    database = Database(f"sqlite:///{database_path}")
    database.initialize()
    expected = {
        "knowledge_server_scopes",
        "knowledge_server_administrators",
        "knowledge_corpora",
        "knowledge_sources",
        "knowledge_access_grants",
        "knowledge_overlay_policies",
    }
    assert expected <= set(inspect(database.engine).get_table_names())
    with database.session() as session:
        assert session.get(DatabaseSchemaMigrationRecord, "knowledge-fabric-scope-v1") is not None
    database.initialize()
    with database.session() as session:
        assert len(
            list(
                session.scalars(
                    select(DatabaseSchemaMigrationRecord).where(
                        DatabaseSchemaMigrationRecord.revision == "knowledge-fabric-scope-v1"
                    )
                )
            )
        ) == 1


def test_pure_policy_fails_closed_and_preserves_precedence_contract() -> None:
    assert may_manage_global_library(is_super_admin=True, is_public_demo=False)
    assert not may_manage_global_library(is_super_admin=False, is_public_demo=False)
    assert not may_manage_global_library(is_super_admin=True, is_public_demo=True)
    assert may_access_server_scope(
        is_super_admin=False, is_explicit_administrator=True, is_public_demo=False
    )
    assert not may_access_server_scope(
        is_super_admin=False, is_explicit_administrator=True, is_public_demo=True
    )
    for mode in ("inherit", "augment", "override", "deny"):
        assert overlay_mode_or_inherit(mode) == mode
    assert corpus_is_effectively_available(
        owner_type=OWNER_SYSTEM,
        owner_id="system",
        visibility=VISIBILITY_GLOBAL,
        status="active",
        server_scope_id="scope-a",
        global_grant_enabled=True,
        overlay_mode="override",
    )
    assert not corpus_is_effectively_available(
        owner_type=OWNER_SYSTEM,
        owner_id="system",
        visibility=VISIBILITY_GLOBAL,
        status="active",
        server_scope_id="scope-a",
        global_grant_enabled=True,
        overlay_mode="deny",
    )
    assert corpus_is_effectively_available(
        owner_type=OWNER_SERVER,
        owner_id="scope-a",
        visibility="private",
        status="active",
        server_scope_id="scope-a",
        global_grant_enabled=False,
        overlay_mode=None,
    )
    assert not corpus_is_effectively_available(
        owner_type=OWNER_SERVER,
        owner_id="scope-b",
        visibility="private",
        status="active",
        server_scope_id="scope-a",
        global_grant_enabled=False,
        overlay_mode=None,
    )
