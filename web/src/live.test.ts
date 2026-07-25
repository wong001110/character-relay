import { describe, expect, it } from "vitest";

import type { TrialEvent } from "./api";
import { latestScenarioName, visibleEvents } from "./live";

function event(
  sequence: number,
  eventType: TrialEvent["event_type"],
  payload: Record<string, unknown> = {}
): TrialEvent {
  return {
    sequence,
    event_type: eventType,
    scenario_id: "memory-room",
    turn_index: 1,
    payload,
    created_at: "2026-07-25T00:00:00Z"
  };
}

describe("live observation helpers", () => {
  it("removes a typing marker after the response arrives", () => {
    const events = [
      event(1, "subject_typing"),
      event(2, "subject_response", { message: "I cannot confirm that memory." })
    ];
    expect(visibleEvents(events).map((item) => item.event_type)).toEqual([
      "subject_response"
    ]);
  });

  it("keeps the latest scenario label", () => {
    expect(
      latestScenarioName([
        event(1, "scenario_started", { name: "Identity Room" }),
        event(2, "scenario_started", { name: "Memory Room" })
      ])
    ).toBe("Memory Room");
  });
});
