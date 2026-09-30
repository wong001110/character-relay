"""Generate 24 UNREVIEWED calibration examples in eight shared template families.

These examples exercise the harness. They are NOT 24 independent conversations,
real captures, human labels, a heldout set, or the required 200-500-point benchmark.
Usage: PYTHONPATH=src python scripts/room_replay_seed.py > /tmp/room-seed.jsonl
"""

from echo_masque.room_replay import ReplayCase, validate_cases
from echo_masque.room_routing import RoomDecision, RoomInput, RoomMessage, RoomRole, RoomScope


def seeds() -> tuple[ReplayCase, ...]:
    scope = RoomScope(
        owner_id="sample", connection_id="sample", guild_id="sample", channel_id="room",
    )
    roles = (
        RoomRole(deployment_id="ann", scope=scope, public_name="Ann",
                 public_description="A concise character who enjoys arithmetic and debugging."),
        RoomRole(deployment_id="ning", scope=scope, public_name="Ning",
                 public_description="A character who enjoys cooking and food suggestions."),
    )
    texts = {
        "en": ("Let's have lunch.", "Please answer this.", 'Ann said "Ning is away".',
               "Is seven times eight fifty-six?", "Lunch is ready.", "Never mind, solved it."),
        "zh": ("我們去吃午餐吧.", "請回答這個問題.", "Ann 說 Ning 不在.",
               "七乘八是不是五十六?", "午餐準備好了.", "不用了, 已經解決了."),
        "mixed": ("Lunch 去吃飯吧.", "Please 回答這個.", "Ann said Ning 不在.",
                  "7 times 8 是 56 嗎?", "Lunch 已做好.", "Solved, 不用了."),
    }
    samples: list[ReplayCase] = []
    for language, (lunch, ask, quote, maths, food, resolved) in texts.items():
        def message(message_id: str, text: str, **kwargs: object) -> RoomMessage:
            return RoomMessage.model_validate({
                "message_id": message_id, "scope": scope, "author_id": "human",
                "text": text, "visible_to": ("ann", "ning"), **kwargs,
            })

        for family in ("lunch", "direct", "multi", "quoted", "reply", "topics", "resolved", "bot"):
            messages = (message("m1", lunch),)
            expected: tuple[RoomDecision, ...] = ()
            required: tuple[RoomDecision, ...] = ()
            if family in {"direct", "multi"}:
                addressed = ("ann", "ning") if family == "multi" else ("ann",)
                messages = (message("m1", ask, mentioned_deployment_ids=addressed),)
                expected = tuple(RoomDecision(
                    speaker=role, target_message_id="m1", mode="direct_answer",
                ) for role in addressed)
                required = expected
            elif family == "quoted":
                messages = (message("m1", quote),)
            elif family in {"reply", "bot"}:
                author = "ann" if family == "reply" else "ning"
                messages = (
                    message("m1", maths, author_deployment_id=author),
                    message("m2", ask, reply_to_id="m1",
                            author_deployment_id="ann" if family == "bot" else None),
                )
                expected = (RoomDecision(
                    speaker=author, target_message_id="m2", mode="direct_answer",
                ),)
                required = expected
            elif family == "topics":
                messages = (message("m1", maths), message("m2", food))
                expected = (RoomDecision(speaker="ann", target_message_id="m1", mode="supplement"),)
            elif family == "resolved":
                messages = (message("m1", maths), message("m2", resolved))
            snapshot = RoomInput(
                scope=scope, revision=1, roles=roles, messages=messages,
                trigger_message_id=messages[-1].message_id, remaining_turns=2,
                buffered_event_count=len(messages),
            )
            samples.append(ReplayCase(
                case_id=f"{family}-{language}", conversation_id=f"{family}-{language}",
                family_id=family, split="calibration", source_kind="synthetic",
                snapshot=snapshot, acceptable=(expected,), required_direct=required,
                tags=(family, language),
            ))
    result = tuple(samples)
    validate_cases(result)
    return result


if __name__ == "__main__":
    for case in seeds():
        print(case.model_dump_json())
