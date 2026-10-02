import { afterEach, describe, expect, it, vi } from "vitest";
import { characterNotesApi, type CharacterNote } from "./characterNotesApi";
import { roomRequest } from "./roomHttp";
const note: CharacterNote = { id: "n/1", character_card_id: "card", text: "clear", kind: "note", subject_ref: "self", authored: true, scope: null, actor_id: "u", source_message_id: "", version: 3, updated_at: "2026-10-02T00:00:00Z" };
describe("explicit notes transport", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("binds edit and forget to an exact version and escaped IDs", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 })); vi.stubGlobal("fetch", fetcher);
    await characterNotesApi.update("a/b", note, { text: "corrected", subject_ref: "self", kind: "note" });
    expect(fetcher.mock.calls[0][0]).toBe("/api/characters/a%2Fb/notes/n%2F1");
    expect(JSON.parse(fetcher.mock.calls[0][1].body).expected_version).toBe(3);
    await characterNotesApi.forget("card", note);
    expect(fetcher.mock.calls[1][0]).toContain("expected_version=3");
  });
  it("never falls back from a scoped room query to global notes", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify([]))); vi.stubGlobal("fetch", fetcher);
    await characterNotesApi.list("card", { connection_id: "c", guild_id: "g", channel_id: "ch", thread_id: "t" });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toContain("thread_id=t");
    expect(fetcher.mock.calls[0][1].credentials).toBe("same-origin");
  });
  it("does not render HTML failures or invent a successful response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<script>unsafe</script>", { status: 403, statusText: "Forbidden" })));
    await expect(roomRequest("/api/test")).rejects.toThrow("403 Forbidden");
  });
});
