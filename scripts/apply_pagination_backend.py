from pathlib import Path
from textwrap import dedent


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise SystemExit(f"Expected snippet not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1))


def append_once(path: str, marker: str, content: str) -> None:
    target = Path(path)
    text = target.read_text()
    if marker in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    target.write_text(text + "\n" + dedent(content).lstrip())


Path("src/echo_masque/pagination.py").write_text(
    dedent(
        '''
        """Stable opaque cursors for time-ordered administrative lists."""

        from __future__ import annotations

        import base64
        import binascii
        import json
        from datetime import UTC, datetime


        def encode_time_cursor(created_at: datetime, identifier: str) -> str:
            value = created_at
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            payload = json.dumps(
                {"created_at": value.astimezone(UTC).isoformat(), "id": identifier},
                separators=(",", ":"),
            ).encode("utf-8")
            return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


        def decode_time_cursor(cursor: str) -> tuple[datetime, str]:
            try:
                padded = cursor + "=" * (-len(cursor) % 4)
                raw = base64.urlsafe_b64decode(padded.encode("ascii"))
                payload = json.loads(raw.decode("utf-8"))
                created_at = datetime.fromisoformat(str(payload["created_at"]))
                identifier = str(payload["id"]).strip()
            except (
                binascii.Error,
                KeyError,
                TypeError,
                ValueError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                raise ValueError("Invalid pagination cursor.") from exc
            if not identifier:
                raise ValueError("Invalid pagination cursor.")
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            return created_at.astimezone(UTC), identifier
        '''
    ).lstrip()
)

# Matrix task pagination while retaining the existing full-list endpoint.
replace_once(
    "src/echo_masque/matrix.py",
    dedent(
        '''
        class MatrixListPage(BaseModel):
            items: list[MatrixView]
            page: int
            page_size: int
            total: int
            pages: int


        class DistributionItem(BaseModel):
        '''
    ).lstrip(),
    dedent(
        '''
        class MatrixListPage(BaseModel):
            items: list[MatrixView]
            page: int
            page_size: int
            total: int
            pages: int


        class MatrixTaskListPage(BaseModel):
            items: list[MatrixTaskView]
            page: int
            page_size: int
            total: int
            pages: int


        class DistributionItem(BaseModel):
        '''
    ).lstrip(),
)
replace_once(
    "src/echo_masque/persistence/matrix_repository.py",
    "    MatrixTaskStatus,\n    MatrixTaskView,\n    MatrixUpdate,",
    "    MatrixTaskListPage,\n    MatrixTaskStatus,\n    MatrixTaskView,\n    MatrixUpdate,",
)
replace_once(
    "src/echo_masque/persistence/matrix_repository.py",
    "    def pending_tasks(self, matrix_id: str, limit: int) -> list[MatrixTaskView]:\n",
    dedent(
        '''
            def list_tasks_page(
                self,
                matrix_id: str,
                owner_id: str,
                *,
                page: int = 1,
                page_size: int = 50,
                status: MatrixTaskStatus | None = None,
            ) -> MatrixTaskListPage | None:
                if self.get_matrix(matrix_id, owner_id) is None:
                    return None
                with self.database.session() as session:
                    conditions = [ExperimentMatrixTaskRecord.matrix_id == matrix_id]
                    if status is not None:
                        conditions.append(
                            ExperimentMatrixTaskRecord.status == status.value
                        )
                    total = int(
                        session.scalar(
                            select(func.count())
                            .select_from(ExperimentMatrixTaskRecord)
                            .where(*conditions)
                        )
                        or 0
                    )
                    pages = max(1, math.ceil(total / page_size))
                    safe_page = min(max(1, page), pages)
                    records = session.scalars(
                        select(ExperimentMatrixTaskRecord)
                        .where(*conditions)
                        .order_by(ExperimentMatrixTaskRecord.ordinal)
                        .offset((safe_page - 1) * page_size)
                        .limit(page_size)
                    )
                    return MatrixTaskListPage(
                        items=[self._task_view(item) for item in records],
                        page=safe_page,
                        page_size=page_size,
                        total=total,
                        pages=pages,
                    )

            def pending_tasks(self, matrix_id: str, limit: int) -> list[MatrixTaskView]:
        '''
    ).lstrip(),
)
replace_once(
    "src/echo_masque/api/routes/matrices.py",
    "    MatrixListPage,\n    MatrixPreview,\n    MatrixTaskView,",
    "    MatrixListPage,\n    MatrixPreview,\n    MatrixTaskListPage,\n    MatrixTaskStatus,\n    MatrixTaskView,",
)
replace_once(
    "src/echo_masque/api/routes/matrices.py",
    dedent(
        '''
            return items


        @router.get("/api/matrices/{matrix_id}/analytics", response_model=MatrixAnalytics)
        '''
    ).lstrip(),
    dedent(
        '''
            return items


        @router.get(
            "/api/matrices/{matrix_id}/tasks/page",
            response_model=MatrixTaskListPage,
        )
        def matrix_tasks_page(
            matrix_id: str,
            request: Request,
            user: CurrentUserDependency,
            page: int = Query(1, ge=1),
            page_size: int = Query(50, ge=1, le=100),
            task_status: MatrixTaskStatus | None = Query(default=None, alias="status"),
        ) -> MatrixTaskListPage:
            result = matrix_repository(request).list_tasks_page(
                matrix_id,
                user.id,
                page=page,
                page_size=page_size,
                status=task_status,
            )
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail="Experiment Matrix not found.",
                )
            return result


        @router.get("/api/matrices/{matrix_id}/analytics", response_model=MatrixAnalytics)
        '''
    ).lstrip(),
)

# Provider Trace cursor pagination.
replace_once(
    "src/echo_masque/persistence/provider_trace_repository.py",
    "from sqlalchemy import delete, func, select\n",
    "from sqlalchemy import and_, delete, func, or_, select\n",
)
replace_once(
    "src/echo_masque/persistence/provider_trace_repository.py",
    "from echo_masque.persistence.database import Database\n",
    "from echo_masque.pagination import decode_time_cursor, encode_time_cursor\nfrom echo_masque.persistence.database import Database\n",
)
replace_once(
    "src/echo_masque/persistence/provider_trace_repository.py",
    "    def clear(self) -> int:\n",
    dedent(
        '''
            def list_traces_page(
                self,
                *,
                limit: int = 50,
                cursor: str | None = None,
                status: str | None = None,
                model: str | None = None,
                trace_id: str | None = None,
            ) -> tuple[list[ProviderTraceRecord], str | None]:
                bounded_limit = max(1, min(limit, 100))
                with self.database.session() as session:
                    query = select(ProviderTraceRecord)
                    if status:
                        query = query.where(ProviderTraceRecord.status == status)
                    if model:
                        query = query.where(
                            func.lower(ProviderTraceRecord.request_model).contains(
                                model.casefold()
                            )
                        )
                    if trace_id:
                        query = query.where(ProviderTraceRecord.trace_id == trace_id)
                    if cursor:
                        created_at, identifier = decode_time_cursor(cursor)
                        query = query.where(
                            or_(
                                ProviderTraceRecord.created_at < created_at,
                                and_(
                                    ProviderTraceRecord.created_at == created_at,
                                    ProviderTraceRecord.trace_id < identifier,
                                ),
                            )
                        )
                    records = list(
                        session.scalars(
                            query.order_by(
                                ProviderTraceRecord.created_at.desc(),
                                ProviderTraceRecord.trace_id.desc(),
                            ).limit(bounded_limit + 1)
                        )
                    )
                    has_more = len(records) > bounded_limit
                    items = records[:bounded_limit]
                    next_cursor = (
                        encode_time_cursor(items[-1].created_at, items[-1].trace_id)
                        if has_more and items
                        else None
                    )
                    return items, next_cursor

            def clear(self) -> int:
        '''
    ).lstrip(),
)
append_once(
    "src/echo_masque/api/provider_trace_schemas.py",
    "class ProviderTracePage(BaseModel):",
    '''
    class ProviderTracePage(BaseModel):
        items: list[ProviderTraceView]
        next_cursor: str | None
        has_more: bool
    ''',
)
replace_once(
    "src/echo_masque/api/routes/provider_traces.py",
    "from fastapi import APIRouter, Query, Request\n",
    "from fastapi import APIRouter, HTTPException, Query, Request\n",
)
replace_once(
    "src/echo_masque/api/routes/provider_traces.py",
    "    ProviderTraceClearResult,\n    ProviderTraceView,",
    "    ProviderTraceClearResult,\n    ProviderTracePage,\n    ProviderTraceView,",
)
replace_once(
    "src/echo_masque/api/routes/provider_traces.py",
    '@router.delete("", response_model=ProviderTraceClearResult)\n',
    dedent(
        '''
        @router.get("/page", response_model=ProviderTracePage)
        def paginate_provider_traces(
            request: Request,
            user: SuperAdminUserDependency,
            limit: int = Query(default=50, ge=1, le=100),
            cursor: str | None = Query(default=None, max_length=1000),
            status_filter: Literal["pending", "succeeded", "error"] | None = Query(
                default=None,
                alias="status",
            ),
            model: str | None = Query(default=None, max_length=200),
            trace_id: str | None = Query(default=None, max_length=64),
        ) -> ProviderTracePage:
            del user
            try:
                records, next_cursor = trace_repository(request).list_traces_page(
                    limit=limit,
                    cursor=cursor,
                    status=status_filter,
                    model=model.strip() if model else None,
                    trace_id=trace_id.strip() if trace_id else None,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return ProviderTracePage(
                items=[ProviderTraceView.from_record(item) for item in records],
                next_cursor=next_cursor,
                has_more=next_cursor is not None,
            )


        @router.delete("", response_model=ProviderTraceClearResult)
        '''
    ).lstrip(),
)

# Audit Event cursor pagination.
replace_once(
    "src/echo_masque/account_lifecycle.py",
    "from sqlalchemy import delete, func, select, update\n",
    "from sqlalchemy import and_, delete, func, or_, select, update\n",
)
replace_once(
    "src/echo_masque/account_lifecycle.py",
    "from echo_masque.auth import SYSTEM_RUNTIME_USER_ID\n",
    "from echo_masque.auth import SYSTEM_RUNTIME_USER_ID\nfrom echo_masque.pagination import decode_time_cursor, encode_time_cursor\n",
)
replace_once(
    "src/echo_masque/account_lifecycle.py",
    "    def claim_local_workspace(self, *, actor_user_id: str) -> dict[str, int]:\n",
    dedent(
        '''
            def list_audit_events_page(
                self,
                *,
                limit: int = 50,
                cursor: str | None = None,
            ) -> tuple[list[AuditEventRecord], str | None]:
                bounded_limit = max(1, min(limit, 100))
                with self.database.session() as session:
                    query = select(AuditEventRecord)
                    if cursor:
                        created_at, identifier = decode_time_cursor(cursor)
                        query = query.where(
                            or_(
                                AuditEventRecord.created_at < created_at,
                                and_(
                                    AuditEventRecord.created_at == created_at,
                                    AuditEventRecord.id < identifier,
                                ),
                            )
                        )
                    records = list(
                        session.scalars(
                            query.order_by(
                                AuditEventRecord.created_at.desc(),
                                AuditEventRecord.id.desc(),
                            ).limit(bounded_limit + 1)
                        )
                    )
                    has_more = len(records) > bounded_limit
                    items = records[:bounded_limit]
                    next_cursor = (
                        encode_time_cursor(items[-1].created_at, items[-1].id)
                        if has_more and items
                        else None
                    )
                    return items, next_cursor

            def claim_local_workspace(self, *, actor_user_id: str) -> dict[str, int]:
        '''
    ).lstrip(),
)
replace_once(
    "src/echo_masque/api/routes/accounts.py",
    "from fastapi import APIRouter, HTTPException, Request, Response, status\n",
    "from fastapi import APIRouter, HTTPException, Query, Request, Response, status\n",
)
replace_once(
    "src/echo_masque/api/routes/accounts.py",
    "class LocalWorkspaceClaim(BaseModel):\n",
    dedent(
        '''
        class AuditEventPage(BaseModel):
            items: list[AuditEventView]
            next_cursor: str | None
            has_more: bool


        class LocalWorkspaceClaim(BaseModel):
        '''
    ).lstrip(),
)
replace_once(
    "src/echo_masque/api/routes/accounts.py",
    '@router.post("/api/admin/workspace/claim-local", response_model=LifecycleResult)\n',
    dedent(
        '''
        @router.get("/api/admin/audit/page", response_model=AuditEventPage)
        def paginate_audit_events(
            request: Request,
            admin: AdminUserDependency,
            limit: int = Query(default=50, ge=1, le=100),
            cursor: str | None = Query(default=None, max_length=1000),
        ) -> AuditEventPage:
            del admin
            service = lifecycle_service(request)
            try:
                records, next_cursor = service.list_audit_events_page(
                    limit=limit,
                    cursor=cursor,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return AuditEventPage(
                items=[AuditEventView.from_record(item, service) for item in records],
                next_cursor=next_cursor,
                has_more=next_cursor is not None,
            )


        @router.post("/api/admin/workspace/claim-local", response_model=LifecycleResult)
        '''
    ).lstrip(),
)

# Deployment list pagination with server-side filters and global status totals.
append_once(
    "src/echo_masque/api/deployment_schemas.py",
    "class CharacterDeploymentPage(BaseModel):",
    '''
    class CharacterDeploymentPage(BaseModel):
        items: list[CharacterDeploymentView]
        page: int
        page_size: int
        total: int
        pages: int
        active: int
        paused: int
        attention: int
    ''',
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "import json\nfrom uuid import uuid4\n\nfrom sqlalchemy import delete, select, update\n",
    "import json\nimport math\nfrom uuid import uuid4\n\nfrom sqlalchemy import delete, func, select, update\n",
)
replace_once(
    "src/echo_masque/persistence/deployment_repository.py",
    "    def list_connector_deployments(\n",
    dedent(
        '''
            def list_deployments_page(
                self,
                owner_id: str,
                *,
                page: int = 1,
                page_size: int = 20,
                character_card_id: str | None = None,
                platform: str | None = None,
                status: str | None = None,
            ) -> tuple[
                list[CharacterDeploymentRecord],
                int,
                int,
                int,
                dict[str, int],
            ]:
                with self.database.session() as session:
                    conditions = [CharacterDeploymentRecord.owner_id == owner_id]
                    if character_card_id is not None:
                        conditions.append(
                            CharacterDeploymentRecord.character_card_id == character_card_id
                        )
                    if platform is not None:
                        conditions.append(CharacterDeploymentRecord.platform == platform)
                    if status is not None:
                        conditions.append(CharacterDeploymentRecord.status == status)
                    total = int(
                        session.scalar(
                            select(func.count())
                            .select_from(CharacterDeploymentRecord)
                            .where(*conditions)
                        )
                        or 0
                    )
                    pages = max(1, math.ceil(total / page_size))
                    safe_page = min(max(1, page), pages)
                    records = list(
                        session.scalars(
                            select(CharacterDeploymentRecord)
                            .where(*conditions)
                            .order_by(
                                CharacterDeploymentRecord.updated_at.desc(),
                                CharacterDeploymentRecord.id.desc(),
                            )
                            .offset((safe_page - 1) * page_size)
                            .limit(page_size)
                        )
                    )
                    counts = {
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
                    return records, safe_page, total, pages, counts

            def list_connector_deployments(
        '''
    ).lstrip(),
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    "    CharacterDeploymentCreate,\n    CharacterDeploymentStatusUpdate,",
    "    CharacterDeploymentCreate,\n    CharacterDeploymentPage,\n    CharacterDeploymentStatusUpdate,",
)
replace_once(
    "src/echo_masque/api/routes/deployments.py",
    '@router.post(\n    "/deployments",\n',
    dedent(
        '''
        @router.get("/deployments/page", response_model=CharacterDeploymentPage)
        def paginate_deployments(
            request: Request,
            user: CurrentUserDependency,
            page: int = Query(default=1, ge=1),
            page_size: int = Query(default=20, ge=1, le=100),
            character_card_id: str | None = Query(default=None),
            platform: str | None = Query(default=None, max_length=24),
            deployment_status: str | None = Query(
                default=None,
                alias="status",
                max_length=24,
            ),
        ) -> CharacterDeploymentPage:
            records, safe_page, total, pages, counts = deployment_repository(
                request
            ).list_deployments_page(
                user.id,
                page=page,
                page_size=page_size,
                character_card_id=character_card_id,
                platform=platform,
                status=deployment_status,
            )
            return CharacterDeploymentPage(
                items=[
                    deployment_view(request, owner_id=user.id, record=record)
                    for record in records
                ],
                page=safe_page,
                page_size=page_size,
                total=total,
                pages=pages,
                active=counts["active"],
                paused=counts["paused"],
                attention=counts["attention"],
            )


        @router.post(
            "/deployments",
        '''
    ).lstrip(),
)

append_once(
    "tests/test_phase14.py",
    "def test_matrix_task_page_supports_status_filters",
    '''
    def test_matrix_task_page_supports_status_filters(tmp_path: Path) -> None:
        client = TestClient(create_app(settings(tmp_path / "matrix-pagination.db")))
        card, pack = create_workspace(client)
        definition = matrix_definition(
            str(card["id"]),
            str(pack["id"]),
            repeat_count=6,
        )
        matrix = client.post(
            "/api/matrices",
            json={"name": "Paged Matrix", "description": "", "definition": definition},
        ).json()
        launched = client.post(
            f"/api/matrices/{matrix['id']}/launch",
            json={"confirmed_task_count": 6},
        )
        assert launched.status_code == 202

        first = client.get(
            f"/api/matrices/{matrix['id']}/tasks/page",
            params={"page": 1, "page_size": 2},
        )
        assert first.status_code == 200, first.text
        assert first.json()["total"] == 6
        assert first.json()["pages"] == 3
        assert [item["ordinal"] for item in first.json()["items"]] == [1, 2]

        completed = client.get(
            f"/api/matrices/{matrix['id']}/tasks/page",
            params={"page": 2, "page_size": 2, "status": "completed"},
        )
        assert completed.status_code == 200
        assert completed.json()["page"] == 2
        assert all(item["status"] == "completed" for item in completed.json()["items"])
    ''',
)
append_once(
    "tests/test_provider_trace_portal.py",
    "def test_provider_trace_cursor_pagination",
    '''
    def test_provider_trace_cursor_pagination(tmp_path: Path) -> None:
        app = create_app(settings(tmp_path / "provider-trace-pagination.db"))
        repository = app.state.provider_trace_repository
        for index in range(1, 6):
            repository.record_event(
                {
                    "event": "provider.request",
                    "trace_id": f"trace-{index:03d}",
                    "endpoint": "https://api.deepseek.com/v1/chat/completions",
                    "model": "deepseek-v4-flash",
                    "trace_mode": "metadata",
                }
            )
        client = TestClient(app)
        login(client, SUPER_EMAIL, SUPER_PASSWORD)

        first = client.get("/api/admin/provider-traces/page", params={"limit": 2})
        assert first.status_code == 200, first.text
        first_payload = first.json()
        assert len(first_payload["items"]) == 2
        assert first_payload["has_more"] is True

        second = client.get(
            "/api/admin/provider-traces/page",
            params={"limit": 2, "cursor": first_payload["next_cursor"]},
        )
        assert second.status_code == 200, second.text
        first_ids = {item["trace_id"] for item in first_payload["items"]}
        second_ids = {item["trace_id"] for item in second.json()["items"]}
        assert first_ids.isdisjoint(second_ids)

        invalid = client.get(
            "/api/admin/provider-traces/page",
            params={"cursor": "not-a-valid-cursor"},
        )
        assert invalid.status_code == 422
    ''',
)
append_once(
    "tests/test_deployments.py",
    "def test_deployment_page_filters_and_reports_global_counts",
    '''
    def test_deployment_page_filters_and_reports_global_counts(tmp_path: Path) -> None:
        client = TestClient(create_app(settings(tmp_path / "deployment-pagination.db")))
        login(client)
        character = create_character(client)
        connection = client.post(
            "/api/connections",
            json={
                "platform": "discord",
                "display_name": "Pagination Discord",
                "connection_mode": "managed",
                "external_account_id": "bot-pagination",
                "status": "connected",
                "metadata": {},
            },
        ).json()
        for index in range(5):
            created = client.post(
                "/api/deployments",
                json={
                    "character_card_id": character["id"],
                    "connection_id": connection["id"],
                    "workspace_id": "guild-pagination",
                    "workspace_name": "Pagination Guild",
                    "channel_id": f"channel-{index}",
                    "channel_name": f"#channel-{index}",
                    "thread_id": "",
                    "thread_name": "",
                    "participation_mode": "mention_and_reply",
                    "memory_scope": "channel_isolated",
                    "version_label": "Current",
                    "sticker_count": 0,
                    "status": "active" if index < 3 else "paused",
                },
            )
            assert created.status_code == 201, created.text

        first = client.get(
            "/api/deployments/page",
            params={"page": 1, "page_size": 2},
        )
        assert first.status_code == 200, first.text
        payload = first.json()
        assert payload["total"] == 5
        assert payload["pages"] == 3
        assert len(payload["items"]) == 2
        assert payload["active"] == 3
        assert payload["paused"] == 2
        assert payload["attention"] == 0

        paused = client.get(
            "/api/deployments/page",
            params={"page_size": 10, "status": "paused"},
        )
        assert paused.status_code == 200
        assert paused.json()["total"] == 2
        assert all(item["status"] == "paused" for item in paused.json()["items"])
    ''',
)
Path("tests/test_list_pagination.py").write_text(
    dedent(
        '''
        from pathlib import Path

        from cryptography.fernet import Fernet
        from fastapi.testclient import TestClient
        from pydantic import SecretStr

        from echo_masque.api import create_app
        from echo_masque.config import Settings

        ADMIN_EMAIL = "pagination-admin@example.com"
        ADMIN_PASSWORD = "PaginationAdmin2026!"


        def settings(path: Path) -> Settings:
            return Settings(
                environment="test",
                database_url=f"sqlite:///{path}",
                legacy_local_user_enabled=False,
                bootstrap_admin_email=ADMIN_EMAIL,
                bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
                bootstrap_admin_display_name="Pagination Admin",
                credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
            )


        def test_audit_cursor_pagination_has_no_duplicates(tmp_path: Path) -> None:
            app = create_app(settings(tmp_path / "audit-pagination.db"))
            client = TestClient(app)
            login = client.post(
                "/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            assert login.status_code == 200, login.text
            for index in range(5):
                app.state.auth_repository.audit(
                    actor_user_id=None,
                    action=f"pagination.event_{index}",
                    resource_type="pagination",
                    resource_id=str(index),
                )

            first = client.get("/api/admin/audit/page", params={"limit": 2})
            assert first.status_code == 200, first.text
            first_payload = first.json()
            assert len(first_payload["items"]) == 2
            assert first_payload["has_more"] is True

            second = client.get(
                "/api/admin/audit/page",
                params={"limit": 2, "cursor": first_payload["next_cursor"]},
            )
            assert second.status_code == 200, second.text
            first_ids = {item["id"] for item in first_payload["items"]}
            second_ids = {item["id"] for item in second.json()["items"]}
            assert first_ids.isdisjoint(second_ids)

            invalid = client.get(
                "/api/admin/audit/page",
                params={"cursor": "invalid"},
            )
            assert invalid.status_code == 422
        '''
    ).lstrip()
)

Path(".github/workflows/apply-pagination-backend.yml").unlink(missing_ok=True)
Path(__file__).unlink()
