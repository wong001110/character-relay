import type { TrialEvent } from "./api";

export function visibleEvents(events: TrialEvent[]): TrialEvent[] {
  return events.filter((event) => {
    if (event.event_type === "subject_typing") {
      return !events.some(
        (candidate) =>
          candidate.sequence > event.sequence &&
          candidate.event_type === "subject_response" &&
          candidate.scenario_id === event.scenario_id &&
          candidate.turn_index === event.turn_index
      );
    }
    if (event.event_type === "tester_thinking") {
      return !events.some(
        (candidate) =>
          candidate.sequence > event.sequence &&
          candidate.event_type === "tester_message" &&
          candidate.scenario_id === event.scenario_id &&
          candidate.turn_index === event.turn_index
      );
    }
    return true;
  });
}

export function payloadText(event: TrialEvent, key: string): string {
  const value = event.payload[key];
  return typeof value === "string" ? value : "";
}

export function payloadNumber(event: TrialEvent, key: string): number | null {
  const value = event.payload[key];
  return typeof value === "number" ? value : null;
}

export function latestScenarioName(events: TrialEvent[]): string {
  const current = [...events].reverse().find((item) => item.event_type === "scenario_started");
  return current ? payloadText(current, "name") : "Waiting room";
}
