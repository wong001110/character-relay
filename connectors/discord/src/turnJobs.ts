import { randomUUID } from "node:crypto";

import type {
  DiscordTurnJobView,
  DiscordTurnProgressEvent
} from "./types.js";

const DEFAULT_POLL_INTERVAL_MS = 1_000;
const DEFAULT_TIMEOUT_MS = 330_000;
const MAX_PROGRESS_EVENTS_PER_DRAIN = 3;

export interface TurnJobTransport {
  poll(jobId: string): Promise<DiscordTurnJobView>;
  claimProgress(
    jobId: string,
    nonce: string
  ): Promise<DiscordTurnProgressEvent | null>;
  acknowledgeProgress(
    jobId: string,
    progressId: number,
    nonce: string
  ): Promise<void>;
}

export interface TurnJobConsumeOptions {
  onProgress: (text: string) => Promise<void>;
  pollIntervalMs?: number;
  timeoutMs?: number;
  now?: () => number;
  sleep?: (milliseconds: number) => Promise<void>;
  nonce?: () => string;
  signal?: AbortSignal;
  onProgressDeliveryError?: (error: unknown) => void;
}

export class TurnJobTerminalError extends Error {
  constructor(
    readonly status: "failed" | "timed_out" | "stopped" | "cancelled",
    readonly errorCode: string | null,
    readonly jobId: string
  ) {
    super(`Character turn job ${status}${errorCode ? ` (${errorCode})` : ""}.`);
    this.name = "TurnJobTerminalError";
  }
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function visibleProgress(text: string): string {
  return text.trim().slice(0, 500);
}

function reportProgressDeliveryError(
  onError: ((error: unknown) => void) | undefined,
  error: unknown
): void {
  try {
    onError?.(error);
  } catch {
    // Progress observation must not prevent the durable final result from arriving.
  }
}

async function drainClaimedProgress(
  jobId: string,
  transport: TurnJobTransport,
  onProgress: (text: string) => Promise<void>,
  nonce: () => string,
  onError?: (error: unknown) => void
): Promise<boolean> {
  for (let count = 0; count < MAX_PROGRESS_EVENTS_PER_DRAIN; count += 1) {
    let event: DiscordTurnProgressEvent | null;
    try {
      event = await transport.claimProgress(jobId, nonce());
    } catch (error) {
      reportProgressDeliveryError(onError, error);
      return false;
    }
    if (!event) return true;

    const text = visibleProgress(event.text);
    try {
      if (text) await onProgress(text);
      await transport.acknowledgeProgress(jobId, event.id, event.nonce);
    } catch (error) {
      // A failed delivery or acknowledgement can be uncertain. Do not claim this
      // event again with a different nonce, but keep waiting for the final result.
      reportProgressDeliveryError(onError, error);
      return false;
    }
  }
  return true;
}

/**
 * Waits for a server-owned Character turn without holding an HTTP request open.
 * Progress is claimed and acknowledged one event at a time so a completed reply
 * cannot overtake visible work already delivered to Discord.
 */
export async function consumeTurnJob(
  initial: DiscordTurnJobView,
  transport: TurnJobTransport,
  options: TurnJobConsumeOptions
): Promise<DiscordTurnJobView> {
  const now = options.now ?? Date.now;
  const pause = options.sleep ?? sleep;
  const nonce = options.nonce ?? randomUUID;
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const deadline = now() + timeoutMs;
  let view = initial;
  let progressAvailable = true;

  for (;;) {
    if (options.signal?.aborted) {
      throw new TurnJobTerminalError("stopped", "connector_shutdown", view.job_id);
    }
    if (progressAvailable) {
      progressAvailable = await drainClaimedProgress(
        view.job_id,
        transport,
        options.onProgress,
        nonce,
        options.onProgressDeliveryError
      );
    }
    if (view.status === "succeeded") return view;
    if (
      view.status === "failed" ||
      view.status === "timed_out" ||
      view.status === "stopped" ||
      view.status === "cancelled"
    ) {
      throw new TurnJobTerminalError(view.status, view.error_code, view.job_id);
    }
    if (now() >= deadline) {
      throw new TurnJobTerminalError(
        "timed_out",
        "connector_poll_budget_exhausted",
        view.job_id
      );
    }
    await pause(pollIntervalMs);
    if (options.signal?.aborted) {
      throw new TurnJobTerminalError("stopped", "connector_shutdown", view.job_id);
    }
    view = await transport.poll(view.job_id);
  }
}
