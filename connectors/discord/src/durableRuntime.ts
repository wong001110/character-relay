import { createHash } from "node:crypto";

import type {
  DiscordSocialPendingTurn,
  DiscordSocialTurnCursor
} from "./types.js";

export type DurableOperationStatus =
  | "active"
  | "awaiting_delivery"
  | "completed"
  | "uncertain"
  | "failed";

export interface DiscordSocialOperationSource {
  deployment_id: string;
  text: string;
  sent_message_ids: string[];
}

export interface DiscordSocialOperationClaim {
  operation_id: string;
  status: DurableOperationStatus;
  cursor: DiscordSocialTurnCursor;
  next_turn: DiscordSocialPendingTurn | null;
  sources: DiscordSocialOperationSource[];
  resume_count: number;
  last_error: string;
}

export interface DiscordPendingSocialOperation {
  operation_id: string;
  status: DurableOperationStatus;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  source_message_id: string;
  updated_at: string;
}

export interface DiscordDeliveryClaim {
  claim_status: "granted" | "already_delivered" | "uncertain";
  operation_status: DurableOperationStatus;
  operation_id: string;
  step_id: string;
}

export function socialOperationId(input: {
  connectionId: string;
  guildId: string;
  channelId: string;
  threadId: string;
  sourceMessageId: string;
}): string {
  return createHash("sha256")
    .update(
      [
        "social-operation-v1",
        input.connectionId,
        input.guildId,
        input.channelId,
        input.threadId,
        input.sourceMessageId
      ].join("\u001f")
    )
    .digest("hex");
}
