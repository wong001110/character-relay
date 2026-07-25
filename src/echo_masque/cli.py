"""Command-line interface."""

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from echo_masque.comparison import RegressionPolicy, compare_results
from echo_masque.config import get_settings
from echo_masque.domain import TestKind, TrialSuiteResult
from echo_masque.suites import scenarios_for
from echo_masque.targets import fragile_target, stable_target
from echo_masque.trials import TrialRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="echo-masque")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("info", help="Print non-secret configuration.")

    serve = subparsers.add_parser("serve", help="Run the FastAPI server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    demo = subparsers.add_parser("run-demo", help="Run deterministic trials.")
    demo.add_argument("--target", choices=("stable", "fragile"), default="fragile")
    demo.add_argument(
        "--suite",
        choices=("all", *(item.value for item in TestKind)),
        default="all",
    )

    compare = subparsers.add_parser(
        "compare-results", help="Compare two saved TrialSuiteResult JSON files."
    )
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--max-score-drop", type=float, default=5.0)
    compare.add_argument("--max-latency-increase-percent", type=float, default=50.0)
    compare.add_argument("--allow-new-failures", action="store_true")
    return parser


async def _run_demo(target_name: str, suite_name: str) -> int:
    target = stable_target() if target_name == "stable" else fragile_target()
    kind = None if suite_name == "all" else TestKind(suite_name)
    result = await TrialRunner().run_suite(target, scenarios_for(kind))
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.passed else 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "info":
        settings = get_settings()
        print(
            json.dumps(
                {
                    "name": settings.app_name,
                    "version": settings.app_version,
                    "environment": settings.environment,
                    "debug": settings.debug,
                    "log_level": settings.log_level,
                },
                indent=2,
            )
        )
        return 0
    if args.command == "serve":
        import uvicorn

        uvicorn.run("echo_masque.main:app", host=args.host, port=args.port, reload=args.reload)
        return 0
    if args.command == "run-demo":
        return asyncio.run(_run_demo(args.target, args.suite))
    if args.command == "compare-results":
        baseline = TrialSuiteResult.model_validate_json(args.baseline.read_text())
        candidate = TrialSuiteResult.model_validate_json(args.candidate.read_text())
        comparison = compare_results(
            baseline,
            candidate,
            RegressionPolicy(
                max_score_drop=args.max_score_drop,
                max_latency_increase_percent=args.max_latency_increase_percent,
                allow_new_failures=args.allow_new_failures,
            ),
        )
        print(comparison.model_dump_json(indent=2))
        return 0 if comparison.gate_passed else 3
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
