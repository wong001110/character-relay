from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise RuntimeError(f"Expected text was not found in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new))


# API import formatting and module-level FastAPI marker.
replace(
    "src/echo_masque/api/routes/matrices.py",
    "from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Response, status",
    "from fastapi import (\n"
    "    APIRouter,\n"
    "    BackgroundTasks,\n"
    "    Header,\n"
    "    HTTPException,\n"
    "    Query,\n"
    "    Request,\n"
    "    Response,\n"
    "    status,\n"
    ")",
)
replace(
    "src/echo_masque/api/routes/matrices.py",
    'OwnerHeader = Annotated[str, Header(alias="X-Echo-User")]\n',
    'OwnerHeader = Annotated[str, Header(alias="X-Echo-User")]\n'
    'ExportFormatQuery = Query("json", alias="format")\n',
)
replace(
    "src/echo_masque/api/routes/matrices.py",
    '    export_format: ExportFormat = Query("json", alias="format"),',
    "    export_format: ExportFormat = ExportFormatQuery,",
)

# Repository imports and SQLAlchemy typed updates.
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    "from sqlalchemy import delete, func, select",
    "from sqlalchemy import delete, func, select, update",
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    "from echo_masque.domain import TrialStatus, TrialSuiteResult",
    "from echo_masque.domain import TrialSuiteResult",
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    "    RunSnapshotRecord,\n",
    "",
)
for model in ("PromptVersionRecord", "ExperimentMatrixTaskRecord", "ExperimentMatrixRecord"):
    replace(
        "src/echo_masque/persistence/matrix_repository.py",
        f"{model}.__table__.update()",
        f"update({model})",
    )

# Make active Prompt state ORM-driven instead of a Core bulk-update side effect.
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '''            session.execute(\n                update(PromptVersionRecord)\n                .where(\n                    PromptVersionRecord.owner_id == owner_id,\n                    PromptVersionRecord.character_card_id == character_card_id,\n                )\n                .values(is_active=False)\n            )\n            if existing is not None:\n                existing.is_active = True\n''',
    '''            versions = list(\n                session.scalars(\n                    select(PromptVersionRecord).where(\n                        PromptVersionRecord.owner_id == owner_id,\n                        PromptVersionRecord.character_card_id == character_card_id,\n                    )\n                )\n            )\n            for item in versions:\n                item.is_active = False\n            if existing is not None:\n                existing.is_active = True\n''',
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '''            session.execute(\n                update(PromptVersionRecord)\n                .where(\n                    PromptVersionRecord.owner_id == owner_id,\n                    PromptVersionRecord.character_card_id == character_card_id,\n                )\n                .values(is_active=False)\n            )\n            version.is_active = True\n''',
    '''            versions = list(\n                session.scalars(\n                    select(PromptVersionRecord).where(\n                        PromptVersionRecord.owner_id == owner_id,\n                        PromptVersionRecord.character_card_id == character_card_id,\n                    )\n                )\n            )\n            for item in versions:\n                item.is_active = item.id == version_id\n''',
)

# Type-safe Matrix expansion.
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '''        models: list[str | None] = definition.model_overrides or [None]\n        temperatures: list[float | None] = definition.temperatures or [None]\n''',
    '''        models: list[str | None] = (\n            [*definition.model_overrides]\n            if definition.model_overrides\n            else [None]\n        )\n        temperatures: list[float | None] = (\n            [*definition.temperatures]\n            if definition.temperatures\n            else [None]\n        )\n''',
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '''        for (\n            subject,\n            model,\n            temperature,\n            pack_id,\n            language,\n            tester_mode,\n            judge_mode,\n            repeat_index,\n        ) in product(\n''',
    '''        for (\n            subject_variant,\n            model,\n            temperature,\n            pack_id,\n            language,\n            tester_mode,\n            judge_mode,\n            repeat_index,\n        ) in product(\n''',
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    "                    character_card_id=subject[0],\n                    prompt_version_id=subject[1],",
    "                    character_card_id=subject_variant[0],\n"
    "                    prompt_version_id=subject_variant[1],",
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '        classification = "incompatible"\n',
    '        classification: Literal[\n'
    '            "improved",\n'
    '            "no_meaningful_change",\n'
    '            "regression",\n'
    '            "incompatible",\n'
    '        ] = "incompatible"\n',
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    "from typing import Any",
    "from typing import Any, Literal",
)

# Wrap lines identified by Ruff.
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '                    raise ValueError("Prompt versions can only be selected for Prompt + Model cards.")',
    '                    raise ValueError(\n'
    '                        "Prompt versions can only be selected for Prompt + Model cards."\n'
    '                    )',
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '''            ("Test Packs", baseline_matrix.definition.test_pack_ids, candidate_matrix.definition.test_pack_ids),\n            ("Languages", baseline_matrix.definition.test_languages, candidate_matrix.definition.test_languages),\n            ("Tester Modes", baseline_matrix.definition.tester_modes, candidate_matrix.definition.tester_modes),\n            ("Judge Modes", baseline_matrix.definition.judge_modes, candidate_matrix.definition.judge_modes),\n''',
    '''            (\n                "Test Packs",\n                baseline_matrix.definition.test_pack_ids,\n                candidate_matrix.definition.test_pack_ids,\n            ),\n            (\n                "Languages",\n                baseline_matrix.definition.test_languages,\n                candidate_matrix.definition.test_languages,\n            ),\n            (\n                "Tester Modes",\n                baseline_matrix.definition.tester_modes,\n                candidate_matrix.definition.tester_modes,\n            ),\n            (\n                "Judge Modes",\n                baseline_matrix.definition.judge_modes,\n                candidate_matrix.definition.judge_modes,\n            ),\n''',
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '            elif score_delta is not None and (\n                score_delta <= -3 or candidate.pass_rate < baseline.pass_rate - 0.05\n            ):',
    '            elif score_delta is not None and (\n'
    '                score_delta <= -3\n'
    '                or candidate.pass_rate < baseline.pass_rate - 0.05\n'
    '            ):',
)
replace(
    "src/echo_masque/persistence/matrix_repository.py",
    '    return [_variant(f"{prefix}:{key}", key, items) for key, items in sorted(groups.items())]',
    '    return [\n'
    '        _variant(f"{prefix}:{key}", key, items)\n'
    '        for key, items in sorted(groups.items())\n'
    '    ]',
)

# Service import, suppressible exception, and loop-variable mypy collision.
replace(
    "src/echo_masque/services/matrix.py",
    "import asyncio\n",
    "import asyncio\nimport contextlib\n",
)
replace(
    "src/echo_masque/services/matrix.py",
    "from echo_masque.domain import TestKind, TrialStatus",
    "from echo_masque.domain import TrialStatus",
)
replace(
    "src/echo_masque/services/matrix.py",
    '''                try:\n                    self.trial_service.cancel(task.run_id)\n                except KeyError:\n                    pass\n''',
    '''                with contextlib.suppress(KeyError):\n                    self.trial_service.cancel(task.run_id)\n''',
)
replace(
    "src/echo_masque/services/matrix.py",
    '''        for item in analytics.by_temperature + analytics.by_model + analytics.by_language:\n            lines.append(\n                f"| {item.label} | {item.run_count} | {_display(item.mean_score)} | "\n                f"{item.pass_rate:.1%} | {item.review_rate:.1%} | {item.failure_rate:.1%} |"\n            )\n''',
    '''        variants = (\n            analytics.by_temperature\n            + analytics.by_model\n            + analytics.by_language\n        )\n        for variant in variants:\n            lines.append(\n                f"| {variant.label} | {variant.run_count} | "\n                f"{_display(variant.mean_score)} | {variant.pass_rate:.1%} | "\n                f"{variant.review_rate:.1%} | {variant.failure_rate:.1%} |"\n            )\n''',
)

# TypeScript async state update.
replace(
    "web/src/MatrixWorkspace.tsx",
    '''      try {\n        setVersions((current) => ({ ...current, [cardId]: await workspaceApi.listPromptVersions(cardId) }));\n      } catch {\n''',
    '''      try {\n        const loaded = await workspaceApi.listPromptVersions(cardId);\n        setVersions((current) => ({ ...current, [cardId]: loaded }));\n      } catch {\n''',
)

# Remove this one-shot patch mechanism from the resulting commit.
Path("scripts/phase14_autofix.py").unlink()
Path(".github/workflows/phase14-autofix.yml").unlink()
