"""Offline Room Director spike CLI. No network, model credentials, or product writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from echo_masque import room_director, room_routing, room_routing_replay
from echo_masque.room_routing_replay import (
    DirectorRecordings,
    ReplayRun,
    export_director_inputs,
    load_corpus,
    replay_director,
    run_rules,
    score_run,
)


def source_identity() -> str:
    digest = hashlib.sha256()
    for module in (room_routing, room_director, room_routing_replay):
        digest.update(Path(module.__file__).read_bytes())
    return f"sha256:{digest.hexdigest()}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("validate", "rules", "export-director", "director", "score")
    )
    parser.add_argument("corpus", type=Path)
    parser.add_argument(
        "--input", type=Path, help="Recordings for director; predictions for score."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    corpus = load_corpus(args.corpus)
    text: str
    if args.action == "validate":
        text = json.dumps(
            {
                "cases": len(corpus.cases),
                "sha256": corpus.sha256,
                "families": len({c.family_id for c in corpus.cases}),
                "human_reviewed": sum(c.label_review == "human_reviewed" for c in corpus.cases),
            },
            indent=2,
        )
    elif args.action == "rules":
        text = run_rules(corpus, source_revision=source_identity()).model_dump_json(indent=2)
    elif args.action == "export-director":
        text = "\n".join(
            json.dumps(row, ensure_ascii=False) for row in export_director_inputs(corpus)
        )
    else:
        if args.input is None:
            parser.error("--input is required for director and score.")
        if args.action == "director":
            recordings = DirectorRecordings.model_validate_json(args.input.read_bytes())
            text = replay_director(
                corpus, recordings, source_revision=source_identity()
            ).model_dump_json(indent=2)
        else:
            run = ReplayRun.model_validate_json(args.input.read_bytes())
            text = json.dumps(score_run(corpus, run), indent=2, ensure_ascii=False, allow_nan=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
