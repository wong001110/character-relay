import { describe, expect, it } from "vitest";

import {
  consumeTurnJob,
  TurnJobTerminalError,
  type TurnJobTransport
} from "./turnJobs.js";
import type { DiscordTurnJobView } from "./types.js";

function job(status: DiscordTurnJobView["status"]): DiscordTurnJobView {
  return {
    job_id: "job-1",
    status,
    progress: [],
    reply:
      status === "succeeded"
        ? {
            action: "reply",
            reason: "done",
            text: "final reply",
            expression: { action: "none", reason: "done" },
            tool_calls: [],
            generated_artifact_ids: []
          }
        : null,
    social_step: null,
    error_code: status === "failed" ? "provider_unavailable" : null
  };
}

describe("consumeTurnJob", () => {
  it("delivers and acknowledges claimed progress before returning the final reply once", async () => {
    const events: string[] = [];
    let claimed = false;
    const transport: TurnJobTransport = {
      poll: async () => {
        events.push("poll");
        return job("succeeded");
      },
      claimProgress: async (_jobId, nonce) => {
        events.push(`claim:${nonce}`);
        if (claimed) return null;
        claimed = true;
        return { id: 7, nonce, text: "I’m checking that now." };
      },
      acknowledgeProgress: async (_jobId, id, nonce) => {
        events.push(`ack:${id}:${nonce}`);
      }
    };

    const result = await consumeTurnJob(job("running"), transport, {
      onProgress: async (text) => {
        events.push(`deliver:${text}`);
      },
      pollIntervalMs: 0,
      sleep: async () => undefined,
      nonce: () => "claim-1"
    });

    expect(result.reply?.text).toBe("final reply");
    expect(events).toEqual([
      "claim:claim-1",
      "deliver:I’m checking that now.",
      "ack:7:claim-1",
      "claim:claim-1",
      "poll",
      "claim:claim-1"
    ]);
    expect(events.filter((item) => item.startsWith("deliver:"))).toHaveLength(1);
  });

  it("surfaces a failed job as an actionable terminal outcome", async () => {
    const transport: TurnJobTransport = {
      poll: async () => job("failed"),
      claimProgress: async () => null,
      acknowledgeProgress: async () => undefined
    };

    await expect(
      consumeTurnJob(job("failed"), transport, { onProgress: async () => undefined })
    ).rejects.toMatchObject({
      name: "TurnJobTerminalError",
      status: "failed",
      errorCode: "provider_unavailable"
    } satisfies Partial<TurnJobTerminalError>);
  });

  it("drains every available progress event before returning a completed job", async () => {
    const delivered: string[] = [];
    const acknowledgements: number[] = [];
    const events = [
      { id: 1, nonce: "nonce-1", text: "One moment." },
      { id: 2, nonce: "nonce-2", text: "Almost there." }
    ];
    const transport: TurnJobTransport = {
      poll: async () => job("succeeded"),
      claimProgress: async () => events.shift() ?? null,
      acknowledgeProgress: async (_jobId, id) => { acknowledgements.push(id); }
    };

    const result = await consumeTurnJob(job("succeeded"), transport, {
      onProgress: async (text) => { delivered.push(text); }
    });

    expect(result.reply?.text).toBe("final reply");
    expect(delivered).toEqual(["One moment.", "Almost there."]);
    expect(acknowledgements).toEqual([1, 2]);
  });

  it("does not resend uncertain progress and still returns the final job result", async () => {
    let claimCount = 0;
    const errors: unknown[] = [];
    const transport: TurnJobTransport = {
      poll: async () => job("succeeded"),
      claimProgress: async (_jobId, nonce) => {
        claimCount += 1;
        return { id: 1, nonce, text: "Working on it." };
      },
      acknowledgeProgress: async () => undefined
    };

    const result = await consumeTurnJob(job("running"), transport, {
      onProgress: async () => { throw new Error("Discord response was lost"); },
      onProgressDeliveryError: (error) => { errors.push(error); },
      pollIntervalMs: 0,
      sleep: async () => undefined
    });

    expect(result.reply?.text).toBe("final reply");
    expect(claimCount).toBe(1);
    expect(errors).toHaveLength(1);
  });

  it("ends polling when the connector budget is exhausted", async () => {
    let clock = 0;
    const transport: TurnJobTransport = {
      poll: async () => job("running"),
      claimProgress: async () => null,
      acknowledgeProgress: async () => undefined
    };

    await expect(
      consumeTurnJob(job("queued"), transport, {
        onProgress: async () => undefined,
        pollIntervalMs: 1,
        timeoutMs: 2,
        now: () => clock,
        sleep: async () => {
          clock += 2;
        }
      })
    ).rejects.toMatchObject({
      name: "TurnJobTerminalError",
      status: "timed_out",
      errorCode: "connector_poll_budget_exhausted"
    } satisfies Partial<TurnJobTerminalError>);
  });

  it("stops without another claim or poll after connector shutdown", async () => {
    const controller = new AbortController();
    controller.abort();
    const transport: TurnJobTransport = {
      poll: async () => {
        throw new Error("poll must not run after shutdown");
      },
      claimProgress: async () => {
        throw new Error("claim must not run after shutdown");
      },
      acknowledgeProgress: async () => undefined
    };

    await expect(
      consumeTurnJob(job("running"), transport, {
        onProgress: async () => undefined,
        signal: controller.signal
      })
    ).rejects.toMatchObject({
      name: "TurnJobTerminalError",
      status: "stopped",
      errorCode: "connector_shutdown"
    } satisfies Partial<TurnJobTerminalError>);
  });
});
