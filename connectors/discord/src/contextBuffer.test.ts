import { describe, expect, it } from "vitest";

import { ContextBuffer } from "./contextBuffer.js";
import type { DiscordContextMessage } from "./types.js";

function message(id: string, text = id): DiscordContextMessage {
  return { message_id: id, author_id: "member-1", author_display_name: "Member",
    text, emojis: [], stickers: [], is_bot: false };
}

describe("group-chat context snapshots", () => {
  it("updates a duplicate in place instead of presenting it as the latest utterance", () => {
    const buffer = new ContextBuffer(3);
    buffer.push("room", message("first"));
    buffer.push("room", message("second"));
    buffer.push("room", message("first", "enriched"));
    expect(buffer.get("room").map((item) => item.message_id)).toEqual(["first", "second"]);
    expect(buffer.get("room")[0]?.text).toBe("enriched");
  });

  it("isolates stored messages from producer and consumer mutations", () => {
    const buffer = new ContextBuffer(3);
    const input = message("first");
    buffer.push("room", input);
    input.text = "producer mutation";
    const firstSnapshot = buffer.get("room");
    firstSnapshot[0]!.text = "consumer mutation";
    firstSnapshot[0]!.stickers.push({ sticker_id: "fake" } as DiscordContextMessage["stickers"][number]);
    firstSnapshot.push(message("not delivered"));
    expect(buffer.get("room")).toEqual([message("first")]);
  });

  it("keeps in-flight snapshots stable when later content arrives", () => {
    const buffer = new ContextBuffer(2);
    buffer.push("room", message("first"));
    const snapshot = buffer.get("room");
    buffer.push("room", message("first", "edited"));
    buffer.push("room", message("second"));
    expect(snapshot).toEqual([message("first")]);
    expect(buffer.get("room")).toEqual([message("first", "edited"), message("second")]);
  });

  it("bounds each room without mixing scopes or resurrecting cleared content", () => {
    const buffer = new ContextBuffer(2);
    buffer.push("public", message("one"));
    buffer.push("private", message("private"));
    buffer.push("public", message("two"));
    buffer.push("public", message("three"));
    expect(buffer.get("public").map((item) => item.message_id)).toEqual(["two", "three"]);
    expect(buffer.get("private")).toEqual([message("private")]);
    buffer.clear("public");
    expect(buffer.get("public")).toEqual([]);
    expect(buffer.get("private")).toHaveLength(1);
    buffer.clear();
    expect(buffer.get("private")).toEqual([]);
  });
});
