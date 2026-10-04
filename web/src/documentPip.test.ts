import { describe, expect, it, vi } from "vitest";
import {
  bindRoomPipLifecycle,
  DocumentPipUnavailableError,
  requestRoomPip,
  sameOriginStylesheetUrl,
  supportsDocumentPip
} from "./documentPip";

class ElementFixture {
  readonly attrs = new Map<string, string>();
  readonly children: ElementFixture[] = [];
  readonly style = { minWidth: "" };
  href = "";
  rel = "";
  nonce = "";
  disabled = false;
  textContent: string | null = null;
  constructor(readonly tagName: string) {}
  getAttribute(name: string): string | null { return this.attrs.get(name) ?? null; }
  setAttribute(name: string, value: string): void { this.attrs.set(name, value); }
  appendChild(child: ElementFixture): ElementFixture { this.children.push(child); return child; }
}

function windowFixture(sources: ElementFixture[] = []) {
  const events = new EventTarget();
  const head = new ElementFixture("HEAD");
  const body = new ElementFixture("BODY");
  const fixture = {
    document: {
      head, body, title: "",
      createElement: (tag: string) => new ElementFixture(tag.toUpperCase()),
      querySelectorAll: () => sources
    },
    location: { href: "https://relay.example/rooms?r=1" },
    closed: false,
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    close: vi.fn(() => { fixture.closed = true; events.dispatchEvent(new Event("pagehide")); })
  };
  return { fixture, window: fixture as unknown as Window, events, head, body };
}

describe("Document PiP application boundary", () => {
  it("allows relative and absolute same-origin HTTP(S) styles only", () => {
    const parent = "https://relay.example/rooms";
    expect(sameOriginStylesheetUrl("/assets/room.css", parent)).toBe("https://relay.example/assets/room.css");
    expect(sameOriginStylesheetUrl("https://relay.example/room.css?v=2", parent)).toBe("https://relay.example/room.css?v=2");
    for (const href of ["https://cdn.example/room.css", "http://relay.example/room.css", "https://relay.example:8443/room.css", "data:text/css,body{}", "javascript:alert(1)", "blob:https://relay.example/abc", "http://["]) {
      expect(sameOriginStylesheetUrl(href, parent)).toBeNull();
    }
    expect(sameOriginStylesheetUrl("file:///room.css", "file:///room.html")).toBeNull();
    expect(sameOriginStylesheetUrl("/room.css", "invalid parent")).toBeNull();
  });

  it("reports unsupported browsers without opening an ordinary popup", async () => {
    const parent = windowFixture();
    expect(supportsDocumentPip(parent.window)).toBe(false);
    await expect(requestRoomPip(parent.window)).rejects.toBeInstanceOf(DocumentPipUnavailableError);
  });

  it("calls the native API immediately and preserves user-activation denial", async () => {
    const parent = windowFixture();
    const error = new DOMException("Requires user activation", "NotAllowedError");
    const requestWindow = vi.fn().mockRejectedValue(error);
    Object.assign(parent.fixture, { documentPictureInPicture: { requestWindow } });
    expect(supportsDocumentPip(parent.window)).toBe(true);
    const pending = requestRoomPip(parent.window);
    expect(requestWindow).toHaveBeenCalledExactlyOnceWith({ width: 380, height: 480 });
    await expect(pending).rejects.toBe(error);
  });

  it("copies CSS in source order, preserves integrity/nonce, and excludes event attributes and remote links", async () => {
    const style = new ElementFixture("STYLE");
    style.textContent = ".room { color: purple }";
    style.nonce = "synthetic-csp-nonce";
    style.setAttribute("media", "screen");
    style.setAttribute("onclick", "bad()");
    const local = new ElementFixture("LINK");
    local.href = "https://relay.example/assets/room.css";
    local.setAttribute("integrity", "sha384-synthetic");
    local.setAttribute("crossorigin", "anonymous");
    local.setAttribute("onload", "bad()");
    const remote = new ElementFixture("LINK");
    remote.href = "https://cdn.example/foreign.css";
    const parent = windowFixture([style, local, remote]);
    const pip = windowFixture();
    Object.assign(parent.fixture, { documentPictureInPicture: { requestWindow: vi.fn().mockResolvedValue(pip.window) } });
    await expect(requestRoomPip(parent.window)).resolves.toBe(pip.window);
    expect(pip.head.children.map(node => node.tagName)).toEqual(["BASE", "STYLE", "LINK"]);
    const [base, copiedStyle, copiedLink] = pip.head.children;
    expect(base.href).toBe(parent.fixture.location.href);
    expect(copiedStyle.textContent).toBe(style.textContent);
    expect(copiedStyle.nonce).toBe(style.nonce);
    expect(copiedStyle.getAttribute("media")).toBe("screen");
    expect(copiedStyle.getAttribute("onclick")).toBeNull();
    expect(copiedLink.href).toBe(local.href);
    expect(copiedLink.rel).toBe("stylesheet");
    expect(copiedLink.getAttribute("integrity")).toBe("sha384-synthetic");
    expect(copiedLink.getAttribute("crossorigin")).toBe("anonymous");
    expect(copiedLink.getAttribute("onload")).toBeNull();
    expect(pip.body.style.minWidth).toBe("0");
  });

  it("closes an unusable PiP window when document access fails", async () => {
    const parent = windowFixture();
    const pip = windowFixture();
    const error = new DOMException("Document blocked", "SecurityError");
    Object.defineProperty(pip.fixture, "document", { get() { throw error; } });
    Object.assign(parent.fixture, { documentPictureInPicture: { requestWindow: vi.fn().mockResolvedValue(pip.window) } });
    await expect(requestRoomPip(parent.window)).rejects.toBe(error);
    expect(pip.fixture.close).toHaveBeenCalledOnce();
  });
});

describe("Document PiP presentation lifecycle", () => {
  it("notifies once on child close while leaving the parent alive", () => {
    const parent = windowFixture();
    const pip = windowFixture();
    const onClose = vi.fn();
    bindRoomPipLifecycle(parent.window, pip.window, onClose);
    pip.fixture.close();
    pip.events.dispatchEvent(new Event("pagehide"));
    parent.events.dispatchEvent(new Event("pagehide"));
    expect(onClose).toHaveBeenCalledOnce();
    expect(parent.fixture.close).not.toHaveBeenCalled();
    expect(pip.fixture.close).toHaveBeenCalledOnce();
  });

  it("closes the child and cleans up when the parent unloads", () => {
    const parent = windowFixture();
    const pip = windowFixture();
    const onClose = vi.fn();
    bindRoomPipLifecycle(parent.window, pip.window, onClose);
    parent.events.dispatchEvent(new Event("pagehide"));
    parent.events.dispatchEvent(new Event("pagehide"));
    expect(pip.fixture.close).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("disposes observers without closing either surface or invoking the callback", () => {
    const parent = windowFixture();
    const pip = windowFixture();
    const onClose = vi.fn();
    const dispose = bindRoomPipLifecycle(parent.window, pip.window, onClose);
    dispose();
    dispose();
    parent.events.dispatchEvent(new Event("pagehide"));
    pip.events.dispatchEvent(new Event("pagehide"));
    expect(onClose).not.toHaveBeenCalled();
    expect(pip.fixture.close).not.toHaveBeenCalled();
    expect(parent.fixture.close).not.toHaveBeenCalled();
  });

  it("handles a window already closed before observers attach", () => {
    const parent = windowFixture();
    const pip = windowFixture();
    pip.fixture.closed = true;
    const onClose = vi.fn();
    bindRoomPipLifecycle(parent.window, pip.window, onClose);
    parent.events.dispatchEvent(new Event("pagehide"));
    expect(onClose).toHaveBeenCalledOnce();
    expect(pip.fixture.close).not.toHaveBeenCalled();
  });
});
