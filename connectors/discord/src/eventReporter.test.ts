import { describe, expect, it, vi } from "vitest";

import {
  DiscordEventReporter,
  type DiscordConnectorEventInput
} from "./eventReporter.js";
import type { DiscordConnectorEvent } from "./types.js";

function fixture(eventType: string): DiscordConnectorEventInput {
  return {
    level: "info" as const,
    event_type: eventType,
    message: "Diagnostic event",
    guild_id: "guild-1",
    guild_name: "Test Guild",
    channel_id: "channel-1",
    channel_name: "general",
    thread_id: "",
    thread_name: "",
    source_message_id: "message-1",
    deployment_id: "",
    character_name: "",
    details: { mentioned_bot: true }
  };
}

describe("DiscordEventReporter", () => {
  it("retains a failed batch and retries it without duplicating events", async () => {
    const delivered: DiscordConnectorEvent[][] = [];
    let attempts = 0;
    const reporter = new DiscordEventReporter(async (events) => {
      attempts += 1;
      delivered.push(events.map((item) => ({ ...item })));
      if (attempts === 1) {
        throw Object.assign(new Error("API unavailable with private Discord text"), {
          code: "ECONNRESET",
          status: 503
        });
      }
    });

    reporter.record(fixture("mention_received"));
    reporter.record(fixture("ignored_no_deployment"));

    await reporter.flush();
    expect(reporter.pendingCount).toBe(2);
    expect(reporter.lastError).toBe("kind=Error code=ECONNRESET status=503");
    expect(reporter.lastError).not.toContain("private Discord text");

    await reporter.flush();
    expect(reporter.pendingCount).toBe(0);
    expect(reporter.lastError).toBeNull();
    expect(reporter.lastSuccessAt).not.toBeNull();
    expect(reporter.lastRecordedAt).not.toBeNull();
    expect(reporter.lastRecordedType).toBe("ignored_no_deployment");
    expect(reporter.sentCount).toBe(2);
    expect(delivered).toHaveLength(2);
    expect(delivered[1]?.map((item) => item.id)).toEqual(
      delivered[0]?.map((item) => item.id)
    );
  });

  it("bounds pending events when the API remains unavailable", () => {
    const reporter = new DiscordEventReporter(vi.fn(), 1_000, 50, 2);
    reporter.record(fixture("one"));
    reporter.record(fixture("two"));
    reporter.record(fixture("three"));
    expect(reporter.pendingCount).toBe(2);
  });

  it("recursively removes content-bearing detail fields without removing diagnostics", async () => {
    const delivered: DiscordConnectorEvent[][] = [];
    const reporter = new DiscordEventReporter(async (events) => {
      delivered.push(events);
    });
    const event = fixture("structured_diagnostic");
    event.details = {
      operation_id: "operation-1",
      candidate_count: 2,
      selected: true,
      trigger_preview: "private preview",
      error: "private error containing message text",
      providerErrorMessage: "private provider error",
      errorDetail: "private combined error detail",
      detail: "private response detail",
      nested: {
        Text: "private text",
        description: "private description",
        rawContent: "private combined raw content",
        descriptionText: "private combined description text",
        planningText: "private camel plan",
        responseBody: "private response body",
        sourceMessageId: "source-safe-id",
        payload_id: "payload-1",
        Planning_Text: "private plan",
        scores: [{ deployment_id: "deployment-1", RESPONSE: "private response" }]
      },
      items: [{ Raw: "private raw", reason: "selected" }]
    };

    reporter.record(event);
    await reporter.flush();

    expect(delivered).toHaveLength(1);
    expect(delivered[0]?.[0]?.details).toEqual({
      operation_id: "operation-1",
      candidate_count: 2,
      selected: true,
      nested: {
        payload_id: "payload-1",
        sourceMessageId: "source-safe-id",
        scores: [{ deployment_id: "deployment-1" }]
      },
      items: [{ reason: "selected" }]
    });
    expect(JSON.stringify(delivered)).not.toContain("private");
  });
});
