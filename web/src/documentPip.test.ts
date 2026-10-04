import { describe, expect, it, vi } from "vitest";
import {
  bindRoomPipLifecycle,
  DEFAULT_ROOM_PIP_SIZE,
  DocumentPipUnavailableError,
  isRoomPipSize,
  readRoomPipSize,
  requestRoomPip,
  resizeRoomPip,
  ROOM_PIP_SIZE_LIMITS,
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
    innerWidth: 380,
    innerHeight: 480,
    outerWidth: 388,
    outerHeight: 518,
    screen: { availWidth: 1364, availHeight: 1024 },
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    resizeTo: vi.fn((width: number, height: number) => {
      const frameWidth = Math.max(0, fixture.outerWidth - fixture.innerWidth);
      const frameHeight = Math.max(0, fixture.outerHeight - fixture.innerHeight);
      fixture.outerWidth = width;
      fixture.outerHeight = height;
      fixture.innerWidth = width - frameWidth;
      fixture.innerHeight = height - frameHeight;
    }),
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

  it("rejects invalid sizes before invoking the native API", async () => {
    const parent = windowFixture();
    const requestWindow = vi.fn();
    Object.assign(parent.fixture, { documentPictureInPicture: { requestWindow } });
    await expect(requestRoomPip(parent.window, { width: 0, height: 480 })).rejects.toBeInstanceOf(RangeError);
    expect(requestWindow).not.toHaveBeenCalled();
  });

  it("corrects an oversized native open with its measured frame, once", async () => {
    const parent = windowFixture();
    const pip = windowFixture();
    Object.assign(pip.fixture, { innerWidth: 1083, innerHeight: 781, outerWidth: 1091, outerHeight: 819 });
    const requestWindow = vi.fn().mockResolvedValue(pip.window);
    Object.assign(parent.fixture, { documentPictureInPicture: { requestWindow } });
    await expect(requestRoomPip(parent.window)).resolves.toBe(pip.window);
    expect(requestWindow).toHaveBeenCalledExactlyOnceWith(DEFAULT_ROOM_PIP_SIZE);
    expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(388, 518);
    expect(readRoomPipSize(pip.window)).toEqual({ width: 380, height: 480 });
    expect(pip.fixture.close).not.toHaveBeenCalled();
    // A user's later manual resize is not fought by an automatic resize listener.
    Object.assign(pip.fixture, { innerWidth: 612, innerHeight: 494, outerWidth: 620, outerHeight: 532 });
    pip.events.dispatchEvent(new Event("resize"));
    expect(pip.fixture.resizeTo).toHaveBeenCalledOnce();
    expect(readRoomPipSize(pip.window)).toEqual({ width: 612, height: 494 });
  });

  it("requests custom content dimensions immediately and applies them after native open", async () => {
    const parent = windowFixture();
    const pip = windowFixture();
    const requestWindow = vi.fn().mockResolvedValue(pip.window);
    Object.assign(parent.fixture, { documentPictureInPicture: { requestWindow } });
    const pending = requestRoomPip(parent.window, { width: 640, height: 560 });
    expect(requestWindow).toHaveBeenCalledExactlyOnceWith({ width: 640, height: 560 });
    await expect(pending).resolves.toBe(pip.window);
    expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(648, 598);
    expect(readRoomPipSize(pip.window)).toEqual({ width: 640, height: 560 });
  });

  it("keeps a prepared PiP usable when native resize throws or is unavailable", async () => {
    for (const resize of [undefined, vi.fn(() => { throw new DOMException("Resize blocked", "NotAllowedError"); })]) {
      const parent = windowFixture();
      const pip = windowFixture();
      Object.assign(pip.fixture, { resizeTo: resize });
      Object.assign(parent.fixture, { documentPictureInPicture: { requestWindow: vi.fn().mockResolvedValue(pip.window) } });
      await expect(requestRoomPip(parent.window)).resolves.toBe(pip.window);
      expect(pip.fixture.document.title).toBe("Room Companion — Character Relay");
      expect(pip.fixture.close).not.toHaveBeenCalled();
    }
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

describe("Document PiP native sizing", () => {
  it("accepts only integer content sizes inside the supplied limits", () => {
    expect(DEFAULT_ROOM_PIP_SIZE).toEqual({ width: 380, height: 480 });
    expect(ROOM_PIP_SIZE_LIMITS).toEqual({ minWidth: 320, minHeight: 320, maxWidth: 2000, maxHeight: 1600 });
    for (const size of [DEFAULT_ROOM_PIP_SIZE, { width: 320, height: 320 }, { width: 2000, height: 1600 }]) {
      expect(isRoomPipSize(size)).toBe(true);
    }
    for (const value of [0, -1, 319, 380.5, NaN, Infinity, -Infinity]) {
      expect(isRoomPipSize({ width: value, height: 480 })).toBe(false);
      expect(isRoomPipSize({ width: 380, height: value })).toBe(false);
    }
    expect(isRoomPipSize({ width: 2001, height: 480 })).toBe(false);
    expect(isRoomPipSize({ width: 380, height: 1601 })).toBe(false);
  });

  it("reads actual inner size including a browser clamp below form limits", () => {
    const pip = windowFixture();
    Object.assign(pip.fixture, { innerWidth: 280, innerHeight: 190 });
    expect(readRoomPipSize(pip.window)).toEqual({ width: 280, height: 190 });
    pip.fixture.closed = true;
    expect(readRoomPipSize(pip.window)).toBeNull();
  });

  it("returns no measurement for invalid or inaccessible native geometry", () => {
    for (const field of ["innerWidth", "innerHeight"]) {
      for (const value of [undefined, 0, -1, 380.5, NaN, Infinity]) {
        const pip = windowFixture();
        Object.assign(pip.fixture, { [field]: value });
        expect(readRoomPipSize(pip.window)).toBeNull();
      }
    }
    const pip = windowFixture();
    Object.defineProperty(pip.fixture, "innerWidth", { get() { throw new Error("Geometry blocked"); } });
    expect(readRoomPipSize(pip.window)).toBeNull();
  });

  it("resizes custom content while including the measured frame", () => {
    const pip = windowFixture();
    expect(resizeRoomPip(pip.window, { width: 620, height: 532 })).toBe(true);
    expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(628, 570);
    expect(readRoomPipSize(pip.window)).toEqual({ width: 620, height: 532 });
  });

  it("treats negative frame differences as zero", () => {
    const pip = windowFixture();
    Object.assign(pip.fixture, { outerWidth: 375, outerHeight: 460 });
    expect(resizeRoomPip(pip.window, DEFAULT_ROOM_PIP_SIZE)).toBe(true);
    expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(380, 480);
  });

  it("bounds outer dimensions by available screen space without a browser-specific ratio", () => {
    const pip = windowFixture();
    expect(resizeRoomPip(pip.window, { width: 1200, height: 900 })).toBe(true);
    expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(1208, 938);
    pip.fixture.resizeTo.mockClear();
    Object.assign(pip.fixture.screen, { availWidth: 600, availHeight: 400 });
    expect(resizeRoomPip(pip.window, { width: 2000, height: 1600 })).toBe(true);
    expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(600, 400);
    expect(readRoomPipSize(pip.window)).toEqual({ width: 592, height: 362 });
  });

  it("uses valid screen limits independently and tolerates missing screen geometry", () => {
    for (const screen of [undefined, { availWidth: 0, availHeight: NaN }, { availWidth: Infinity, availHeight: -1 }]) {
      const pip = windowFixture();
      Object.assign(pip.fixture, { screen });
      expect(resizeRoomPip(pip.window, DEFAULT_ROOM_PIP_SIZE)).toBe(true);
      expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(388, 518);
    }
    const pip = windowFixture();
    Object.assign(pip.fixture.screen, { availWidth: 360, availHeight: 0 });
    expect(resizeRoomPip(pip.window, DEFAULT_ROOM_PIP_SIZE)).toBe(true);
    expect(pip.fixture.resizeTo).toHaveBeenCalledExactlyOnceWith(360, 518);
  });

  it("does not invent actual geometry when a browser clamps the requested resize", () => {
    const pip = windowFixture();
    pip.fixture.resizeTo.mockImplementation(() => {
      Object.assign(pip.fixture, { outerWidth: 350, outerHeight: 318, innerWidth: 342, innerHeight: 280 });
    });
    expect(resizeRoomPip(pip.window, DEFAULT_ROOM_PIP_SIZE)).toBe(true);
    expect(readRoomPipSize(pip.window)).toEqual({ width: 342, height: 280 });
  });

  it("fails safely for invalid requests, closed windows, unavailable geometry and resize errors", () => {
    const invalid = windowFixture();
    expect(resizeRoomPip(invalid.window, { width: NaN, height: 480 })).toBe(false);
    expect(invalid.fixture.resizeTo).not.toHaveBeenCalled();
    for (const dimensions of [{ closed: true }, { innerWidth: 0 }, { outerWidth: undefined }, { outerHeight: 0 }, { outerWidth: 388.5 }]) {
      const pip = windowFixture();
      Object.assign(pip.fixture, dimensions);
      expect(resizeRoomPip(pip.window, DEFAULT_ROOM_PIP_SIZE)).toBe(false);
      expect(pip.fixture.resizeTo).not.toHaveBeenCalled();
    }
    const inaccessible = windowFixture();
    Object.defineProperty(inaccessible.fixture, "closed", { get() { throw new Error("Window blocked"); } });
    expect(resizeRoomPip(inaccessible.window, DEFAULT_ROOM_PIP_SIZE)).toBe(false);
    const denied = windowFixture();
    denied.fixture.resizeTo.mockImplementation(() => { throw new Error("Resize blocked"); });
    expect(resizeRoomPip(denied.window, DEFAULT_ROOM_PIP_SIZE)).toBe(false);
    expect(denied.fixture.close).not.toHaveBeenCalled();
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
