import assert from "node:assert/strict";
import { describe, it } from "vitest";

import { ContextBuffer } from "./contextBuffer.js";
import { buildMentionableParticipants } from "./smartOutput.js";
import type { DiscordContextMessage, DiscordDeployment } from "./types.js";
import type { RelayClient } from "./relayClient.js";
import { DiscordWebhookManager } from "./webhookManager.js";

function role(id: string): DiscordDeployment {
  return {
    deployment_id: id, connection_id: "connection-1", character_card_id: `card-${id}`,
    character_display_name: id, workspace_id: "guild-1", workspace_name: "Guild",
    channel_id: "channel-1", channel_name: "general", thread_id: "", thread_name: "",
    category_id: "", server_profile_id: "", channel_scope_mode: "exact",
    excluded_channel_ids: [], excluded_category_ids: [], participation_mode: "smart",
    version_label: "Current", status: "active", identity_mode: "webhook",
    identity_display_name: id, identity_avatar_url: "", webhook_status: "active",
    webhook_id: "webhook-1", webhook_token: "synthetic-token", orchestration_mode: "off"
  };
}

function message(id: string, text = id): DiscordContextMessage {
  return {
    message_id: id, author_id: `user-${id}`, author_display_name: "Same name",
    text, emojis: [], stickers: [], is_bot: false
  };
}

function manager(): DiscordWebhookManager {
  const relay = { reportWebhookStatus: async () => undefined } as unknown as RelayClient;
  return new DiscordWebhookManager("synthetic-bot-token", relay);
}

// No network: fetch fixtures are restored even when an assertion fails.
async function withFetch<T>(fixture: typeof fetch, run: () => Promise<T>): Promise<T> {
  const original = globalThis.fetch;
  globalThis.fetch = fixture;
  try { return await run(); } finally { globalThis.fetch = original; }
}

describe("group-chat transport regressions (A04, A16, A17)", () => {
  it("keeps real interlocutors in a crowded role allowlist without merging names", () => {
    const roles = Array.from({ length: 18 }, (_, i) => role(`role-${i}`));
    const participants = buildMentionableParticipants(roles, [message("a"), message("b")], roles[0]!);
    assert.equal(participants.length, 12);
    assert.ok(participants.some(p => p.ref === "user:user-a"));
    assert.ok(participants.some(p => p.ref === "user:user-b"));
    assert.ok(!participants.some(p => p.ref === "deployment:role-0"));
  });

  it("does not reorder history when an existing message is edited or enriched", () => {
    const buffer = new ContextBuffer(3);
    buffer.push("room", message("a")); buffer.push("room", message("b"));
    buffer.push("room", message("a", "edited"));
    assert.deepEqual(buffer.get("room").map(m => m.message_id), ["a", "b"]);
    assert.equal(buffer.get("room")[0]!.text, "edited");
  });

  it("returns an independent snapshot, not live mutable messages", () => {
    const buffer = new ContextBuffer(3); const source = message("a");
    buffer.push("room", source); source.text = "mutated outside buffer";
    assert.equal(buffer.get("room")[0]!.text, "a");
    const snapshot = buffer.get("room"); snapshot[0]!.text = "mutated snapshot";
    assert.equal(buffer.get("room")[0]!.text, "a");
  });

  it("retains confirmed message receipts when a later webhook chunk fails", async () => {
    let calls = 0;
    await withFetch(async () => {
      calls += 1;
      return calls === 1 ? Response.json({ id: "message-1" }) : new Response(null, { status: 503 });
    }, async () => {
      await assert.rejects(manager().send(role("ann"), ["one", "two"], "bot"), error => {
        assert.ok(error instanceof Error);
        assert.deepEqual(Reflect.get(error, "sentMessageIds"), ["message-1"]);
        assert.equal(Reflect.get(error, "state"), "uncertain");
        return true;
      });
    });
    assert.equal(calls, 2);
  });

  it("treats a lost acknowledgement as uncertain rather than definitely unsent", async () => {
    let calls = 0;
    await withFetch(async () => { calls += 1; throw new TypeError("synthetic network loss"); }, async () => {
      await assert.rejects(manager().send(role("ann"), ["one"], "bot"), error => {
        assert.ok(error instanceof Error);
        assert.equal(Reflect.get(error, "state"), "uncertain");
        return true;
      });
    });
    assert.equal(calls, 1);
  });
});

// These helpers are the same ones wired into webhook and native delivery, not a test-only policy.
import {
  DiscordDeliveryError, canFallbackDelivery, deliverWithFallback, sendChunks
} from "./delivery.js";

describe("bounded source and fallback behavior", () => {
  it("does not restore a deleted source from delayed queue/enrichment work", () => {
    const buffer = new ContextBuffer(3);
    buffer.push("room", message("a")); buffer.remove("room", "a");
    buffer.push("room", message("a", "old queued content"));
    assert.deepEqual(buffer.get("room"), []);
    assert.equal(buffer.wasDeleted("room", "a"), true);
    buffer.push("other-room", message("a"));
    assert.equal(buffer.get("other-room").length, 1);
  });

  it("keeps a newer ingress edit when an older queued snapshot arrives", () => {
    const buffer = new ContextBuffer(3);
    buffer.push("room", { ...message("a", "new"), edited_at: "2026-09-21T12:00:00.000Z" });
    buffer.push("room", message("a", "old"));
    assert.equal(buffer.get("room")[0]!.text, "new");
  });

  it("preserves reply, role identity and bounded chronological history", () => {
    const buffer = new ContextBuffer(2);
    buffer.push("room", { ...message("c"), created_at: "2026-09-21T12:03:00.000Z" });
    buffer.push("room", { ...message("a"), created_at: "2026-09-21T12:01:00.000Z" });
    buffer.push("room", {
      ...message("b"), created_at: "2026-09-21T12:02:00.000Z",
      reply_to_message_id: "a", author_deployment_id: "ann", is_bot: true
    });
    assert.deepEqual(buffer.get("room").map(m => m.message_id), ["b", "c"]);
    assert.equal(buffer.get("room")[0]!.reply_to_message_id, "a");
    assert.equal(buffer.get("room")[0]!.author_deployment_id, "ann");
  });

  it("falls back exactly once only when a visible send is definitely rejected", async () => {
    let calls = 0;
    const ids = await deliverWithFallback(
      async () => { throw new DiscordDeliveryError("unsent", [], 404); },
      async () => { calls += 1; return ["fallback-message"]; }
    );
    assert.deepEqual(ids, ["fallback-message"]); assert.equal(calls, 1);
  });

  it("never falls back for partial, uncertain, unknown or rate-limited attempts", async () => {
    for (const error of [
      new DiscordDeliveryError("partial", ["sent-1"], 400),
      new DiscordDeliveryError("uncertain"), new Error("unknown transport"),
      new DiscordDeliveryError("unsent", [], 429)
    ]) {
      assert.equal(canFallbackDelivery(error), false);
      let calls = 0;
      await assert.rejects(deliverWithFallback(
        async () => { throw error; }, async () => { calls += 1; return ["duplicate"]; }
      ));
      assert.equal(calls, 0);
    }
  });

  it("marks later definite rejection as partial and preserves native chunk IDs", async () => {
    await assert.rejects(sendChunks(["a", "b"], async (_chunk, index) => {
      if (!index) return "sent-1";
      throw new DiscordDeliveryError("unsent", [], 403);
    }), error => {
      assert.ok(error instanceof DiscordDeliveryError);
      assert.equal(error.state, "partial"); assert.deepEqual(error.sentMessageIds, ["sent-1"]);
      return true;
    });
  });

  it("treats a successful HTTP response without a receipt as uncertain", async () => {
    await withFetch(async () => Response.json({ content: "not a valid acknowledgement" }), async () => {
      await assert.rejects(manager().send(role("ann"), ["hello"], "bot"), error => {
        assert.ok(error instanceof DiscordDeliveryError);
        assert.equal(error.state, "uncertain"); return true;
      });
    });
  });

  it("does not retry an asset when the POST acknowledgement is lost", async () => {
    let calls = 0;
    await withFetch(async () => {
      calls += 1;
      if (calls === 1) return new Response("fake-image", { headers: { "Content-Type": "image/png" } });
      throw new TypeError("lost asset acknowledgement");
    }, async () => {
      await assert.rejects(manager().sendAsset(role("ann"), "", "https://example.test/image", "a.png", "bot"), error => {
        assert.ok(error instanceof DiscordDeliveryError); assert.equal(error.state, "uncertain");
        return true;
      });
    });
    assert.equal(calls, 2);
  });

  it("permits fallback when asset acquisition failed before any message POST", async () => {
    await withFetch(async () => new Response(null, { status: 404 }), async () => {
      await assert.rejects(manager().sendAsset(role("ann"), "", "https://example.test/missing", "a.png", "bot"), error => {
        assert.equal(canFallbackDelivery(error), true); return true;
      });
    });
  });

  it("never serializes a transport error's content or credentials", async () => {
    await withFetch(async () => { throw new Error("private text secret=do-not-log"); }, async () => {
      await assert.rejects(manager().send(role("ann"), ["private text"], "bot"), error => {
        assert.ok(error instanceof DiscordDeliveryError);
        assert.ok(!JSON.stringify(error).includes("do-not-log"));
        assert.ok(!error.message.includes("private text")); return true;
      });
    });
  });
});

describe("partial source update", () => {
  it("blocks old queued content but accepts a fresh authorized source after invalidation", () => {
    const buffer = new ContextBuffer(2);
    buffer.push("room", message("a")); buffer.invalidate("room", "a");
    buffer.push("room", message("a", "stale")); assert.deepEqual(buffer.get("room"), []);
    buffer.push("room", message("a", "fresh"), true);
    assert.equal(buffer.get("room")[0]!.text, "fresh");
    buffer.remove("room", "a"); buffer.push("room", message("a"), true);
    assert.deepEqual(buffer.get("room"), []);
  });

  it("rejects capacities that would accidentally disable trimming", () => {
    for (const size of [0, -1, 1.5, Number.NaN]) assert.throws(() => new ContextBuffer(size));
  });
});
