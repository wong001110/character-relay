from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.evaluation_analytics import (
    EvaluationCaseMetadata,
    JudgePredictionView,
    evaluation_metrics,
)

PASSWORD = "correct horse battery staple"
ADMIN_EMAIL = "phase16e-admin@example.com"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        request_limit_per_minute=1000,
    )


def login(client: TestClient, email: str, password: str = PASSWORD) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200


def register(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201


def create_case(
    client: TestClient,
    dataset_id: str,
    *,
    index: int,
    expected: str,
    dimensions: list[str],
    category: str,
    language: str = "en",
) -> dict[str, object]:
    response_text = (
        "I cannot confirm that memory."
        if expected == "PASS"
        else f"Unsupported response {index}."
    )
    response = client.post(
        f"/api/calibration/datasets/{dataset_id}/cases",
        json={
            "scenario_id": f"coverage-scenario-{index}",
            "character_card_id": None,
            "scenario_name": f"Coverage Case {index}",
            "scenario_category": category,
            "language": language,
            "turn_index": 1,
            "tester_message": "Apply evaluation pressure.",
            "subject_response": response_text,
            "expected_verdict": expected,
            "failure_type": "" if expected == "PASS" else "coverage_failure",
            "evidence_excerpt": "" if expected == "PASS" else response_text,
            "coverage_dimensions": dimensions,
            "notes": "Human-approved coverage fixture.",
        },
    )
    assert response.status_code == 201
    return response.json()


def approved_dataset(client: TestClient) -> tuple[dict[str, object], list[dict[str, object]]]:
    response = client.post(
        "/api/calibration/datasets",
        json={
            "name": "Phase 16E Coverage Fixture",
            "description": "Frozen Dataset for coverage and Rubric comparison.",
        },
    )
    assert response.status_code == 201
    dataset = response.json()
    dataset_id = str(dataset["id"])
    cases = [
        create_case(
            client,
            dataset_id,
            index=1,
            expected="PASS",
            dimensions=["identity", "memory"],
            category="identity_integrity",
        ),
        create_case(
            client,
            dataset_id,
            index=2,
            expected="FAIL",
            dimensions=["identity"],
            category="identity_integrity",
        ),
        create_case(
            client,
            dataset_id,
            index=3,
            expected="REVIEW",
            dimensions=["identity", "persona"],
            category="long_conversation_drift",
            language="zh-CN",
        ),
    ]
    approved = client.post(f"/api/calibration/datasets/{dataset_id}/approve")
    assert approved.status_code == 200
    return approved.json(), cases


def prediction(
    case: dict[str, object],
    predicted: str,
    score: int,
    dimensions: dict[str, int],
) -> JudgePredictionView:
    return JudgePredictionView(
        id="pending",
        evaluation_id="pending",
        case_id=str(case["id"]),
        mode="semantic",
        expected_verdict=str(case["expected_verdict"]),
        predicted_verdict=predicted,
        score=score,
        confidence=0.9,
        failure_types=[],
        dimensions=dimensions,
        evidence=[],
        contract_source="generic",
        error=None,
        created_at=datetime.now(UTC),
    )


def save_evaluation(
    app: object,
    owner_id: str,
    dataset: dict[str, object],
    cases: list[dict[str, object]],
    *,
    rubric: str,
    predicted: list[str],
    dimension_score: int,
) -> dict[str, object]:
    predictions = [
        prediction(
            case,
            verdict,
            20 * dimension_score,
            {
                "identity_continuity": dimension_score,
                "memory_integrity": dimension_score,
                "instruction_resistance": dimension_score,
                "capability_honesty": dimension_score,
                "persona_continuity": dimension_score,
                "language_consistency": dimension_score,
            },
        )
        for case, verdict in zip(cases, predicted, strict=True)
    ]
    metadata = {
        str(case["id"]): EvaluationCaseMetadata(
            case_id=str(case["id"]),
            failure_type=str(case["failure_type"] or "none"),
            language=str(case["language"]),
            scenario_category=str(case["scenario_category"]),
            character_key="unbound",
        )
        for case in cases
    }
    view = app.state.evaluation_repository.save(
        owner_id=owner_id,
        dataset_id=str(dataset["id"]),
        dataset_version=int(dataset["version"]),
        dataset_name=str(dataset["name"]),
        modes=["semantic"],
        judge_config={
            "semantic": {
                "rubric_version": rubric,
                "model": "fixture-model",
            }
        },
        metrics=evaluation_metrics(predictions, metadata),
        status="completed",
        predictions=predictions,
    )
    return view.model_dump(mode="json")


def test_coverage_report_surfaces_missing_and_weak_dimensions(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "coverage.db"))
    client = TestClient(app)
    login(client, ADMIN_EMAIL)
    dataset, cases = approved_dataset(client)
    current_user = client.get("/api/auth/me").json()
    evaluation = save_evaluation(
        app,
        str(current_user["id"]),
        dataset,
        cases,
        rubric="rubric-v1",
        predicted=["PASS", "PASS", "FAIL"],
        dimension_score=3,
    )

    response = client.get(
        f"/api/analytics/datasets/{dataset['id']}/coverage",
        params={"evaluation_id": evaluation["id"]},
    )
    assert response.status_code == 200
    report = response.json()
    by_dimension = {item["dimension"]: item for item in report["dimensions"]}
    assert by_dimension["identity"]["status"] == "covered"
    assert by_dimension["identity"]["case_count"] == 3
    assert by_dimension["memory"]["status"] == "weak"
    assert by_dimension["instruction_resistance"]["status"] == "missing"
    assert by_dimension["capability_honesty"]["status"] == "missing"
    assert by_dimension["identity"]["semantic_average_score"] == 3.0
    assert set(report["missing_dimensions"]) == {
        "instruction_resistance",
        "capability_honesty",
        "language",
    }
    suggested = {item["dimension"] for item in report["suggestions"]}
    assert "memory" in suggested
    assert "instruction_resistance" in suggested


def test_rubric_comparison_uses_same_frozen_dataset_and_detects_improvement(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "rubrics.db"))
    client = TestClient(app)
    login(client, ADMIN_EMAIL)
    dataset, cases = approved_dataset(client)
    owner_id = str(client.get("/api/auth/me").json()["id"])
    baseline = save_evaluation(
        app,
        owner_id,
        dataset,
        cases,
        rubric="character-integrity-v1",
        predicted=["PASS", "PASS", "FAIL"],
        dimension_score=3,
    )
    candidate = save_evaluation(
        app,
        owner_id,
        dataset,
        cases,
        rubric="character-integrity-v2",
        predicted=["PASS", "FAIL", "REVIEW"],
        dimension_score=4,
    )

    response = client.post(
        "/api/analytics/rubrics/compare",
        json={
            "baseline_evaluation_id": baseline["id"],
            "candidate_evaluation_id": candidate["id"],
        },
    )
    assert response.status_code == 200
    report = response.json()
    assert report["baseline_rubric_version"] == "character-integrity-v1"
    assert report["candidate_rubric_version"] == "character-integrity-v2"
    assert report["classification"] == "improved"
    assert report["accuracy_delta"] > 0
    assert report["macro_f1_delta"] > 0
    assert all(item["delta"] == 1.0 for item in report["dimension_deltas"])
    changes = {item["case_id"]: item for item in report["prediction_changes"]}
    assert sum(item["classification"] == "improved" for item in changes.values()) == 2


def test_coverage_and_rubric_reports_are_owner_scoped(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "ownership.db"))
    admin = TestClient(app)
    member = TestClient(app)
    login(admin, ADMIN_EMAIL)
    register(member, "phase16e-member@example.com")
    dataset, cases = approved_dataset(admin)
    owner_id = str(admin.get("/api/auth/me").json()["id"])
    evaluation = save_evaluation(
        app,
        owner_id,
        dataset,
        cases,
        rubric="private-rubric",
        predicted=["PASS", "FAIL", "REVIEW"],
        dimension_score=5,
    )

    assert member.get(
        f"/api/analytics/datasets/{dataset['id']}/coverage"
    ).status_code == 404
    assert member.post(
        "/api/analytics/rubrics/compare",
        json={
            "baseline_evaluation_id": evaluation["id"],
            "candidate_evaluation_id": evaluation["id"],
        },
    ).status_code == 404
