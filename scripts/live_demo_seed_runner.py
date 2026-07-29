"""Run the permanent Live Demo seed with safe runtime fallback.

When Admin-managed Adaptive Tester and Semantic Judge are both ready, the runner
keeps Adaptive + Hybrid results. Otherwise it still creates all permanent demo
content and runs the real Subject models through Benchmark + Rules. Re-running the
workflow after Admin enables both runtimes adds new Adaptive + Hybrid history
without deleting the earlier Runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import live_demo_seed as seed


def select_modes(runtime: dict[str, Any]) -> tuple[str, str, str]:
    adaptive = runtime.get("adaptive")
    judge = runtime.get("judge")
    adaptive_ready = isinstance(adaptive, dict) and adaptive.get("configured") is True
    judge_ready = isinstance(judge, dict) and judge.get("configured") is True
    if adaptive_ready and judge_ready:
        return "adaptive", "hybrid", "Admin Adaptive Tester and Semantic Judge are ready."
    return (
        "benchmark",
        "rules",
        "Admin runtimes are not both enabled; retained Runs use real Subjects with Benchmark + Rules.",
    )


def run_character_trial(
    base_url: str,
    card: dict[str, Any],
    pack: dict[str, Any],
    *,
    tester_mode: str,
    judge_mode: str,
) -> dict[str, Any]:
    started = seed.request_json(
        base_url,
        "/api/trials",
        method="POST",
        payload={
            "character_card_id": card["id"],
            "test_pack_id": pack["id"],
            "mode": "fast",
            "tester_mode": tester_mode,
            "judge_mode": judge_mode,
            "test_language": "zh-CN",
        },
    )
    if not isinstance(started, dict) or not isinstance(started.get("id"), str):
        raise RuntimeError(f"Trial creation failed for {card.get('display_name')}: {started}")
    return seed.wait_for_trial(base_url, started["id"])


def seed_live_demo(base_url: str) -> dict[str, object]:
    runtime = seed.request_json(base_url, "/api/runtime/status")
    if not isinstance(runtime, dict):
        raise RuntimeError("Runtime status returned an invalid payload.")
    tester_mode, judge_mode, mode_note = select_modes(runtime)

    targets = seed.request_json(base_url, "/api/targets")
    cards = seed.request_json(base_url, "/api/characters")
    if not isinstance(targets, list) or not isinstance(cards, list):
        raise RuntimeError("Target or Character list returned an invalid payload.")

    kept_cards: list[dict[str, Any]] = []
    for spec in seed.CHARACTERS:
        target = seed.ensure_target(base_url, targets, spec)
        card = seed.ensure_card(base_url, cards, spec, str(target["id"]))
        credential = seed.request_json(base_url, f"/api/characters/{card['id']}/credential")
        if not isinstance(credential, dict) or credential.get("configured") is not True:
            raise RuntimeError(
                f"{spec.display_name} cannot resolve {seed.MODEL_KEY_ENV}: {credential}"
            )
        kept_cards.append(card)

    scenarios = seed.ensure_scenarios(base_url)
    pack = seed.ensure_pack(base_url, scenarios)
    runs = [
        run_character_trial(
            base_url,
            card,
            pack,
            tester_mode=tester_mode,
            judge_mode=judge_mode,
        )
        for card in kept_cards
    ]

    return {
        "base_url": base_url,
        "kept": True,
        "runtime": runtime,
        "used_modes": {
            "tester_mode": tester_mode,
            "judge_mode": judge_mode,
            "note": mode_note,
        },
        "characters": [
            {
                "id": card["id"],
                "display_name": card["display_name"],
                "target_id": card["target_id"],
            }
            for card in kept_cards
        ],
        "test_pack": {
            "id": pack["id"],
            "name": pack["name"],
            "version": pack["version"],
        },
        "scenarios": [{"id": item["id"], "name": item["name"]} for item in scenarios],
        "runs": [seed.result_summary(run) for run in runs],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Public Echo Masque URL")
    parser.add_argument("--output", type=Path, default=Path("live-demo-result.json"))
    args = parser.parse_args()

    result = seed_live_demo(seed.normalized_base_url(args.base_url))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
