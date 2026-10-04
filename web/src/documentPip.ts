interface DocumentPictureInPictureApi {
  requestWindow(options: { width: number; height: number }): Promise<Window>;
}

type DocumentPipParent = Window & {
  documentPictureInPicture?: DocumentPictureInPictureApi;
};

export interface RoomPipSize {
  width: number;
  height: number;
}

export const DEFAULT_ROOM_PIP_SIZE: RoomPipSize = Object.freeze({ width: 380, height: 480 });
export const ROOM_PIP_SIZE_LIMITS = Object.freeze({
  minWidth: 320,
  minHeight: 320,
  maxWidth: 2000,
  maxHeight: 1600
});

export function isRoomPipSize(size: RoomPipSize): boolean {
  return !!size && Number.isInteger(size.width) && Number.isInteger(size.height)
    && size.width >= ROOM_PIP_SIZE_LIMITS.minWidth && size.width <= ROOM_PIP_SIZE_LIMITS.maxWidth
    && size.height >= ROOM_PIP_SIZE_LIMITS.minHeight && size.height <= ROOM_PIP_SIZE_LIMITS.maxHeight;
}

/** Actual content dimensions can fall below the form's limits after a browser clamp. */
export function readRoomPipSize(pipWindow: Window): RoomPipSize | null {
  try {
    if (pipWindow.closed) return null;
    const { innerWidth: width, innerHeight: height } = pipWindow;
    return Number.isInteger(width) && width > 0 && Number.isInteger(height) && height > 0
      ? { width, height }
      : null;
  } catch {
    return null;
  }
}

/** Request a content viewport; resizeTo takes outer dimensions including the native frame. */
export function resizeRoomPip(pipWindow: Window, size: RoomPipSize): boolean {
  if (!isRoomPipSize(size)) return false;
  try {
    if (pipWindow.closed || typeof pipWindow.resizeTo !== "function") return false;
    const current = readRoomPipSize(pipWindow);
    const { outerWidth, outerHeight } = pipWindow;
    if (!current || !Number.isInteger(outerWidth) || outerWidth <= 0
      || !Number.isInteger(outerHeight) || outerHeight <= 0) return false;

    let width = size.width + Math.max(0, outerWidth - current.width);
    let height = size.height + Math.max(0, outerHeight - current.height);
    const availableWidth = pipWindow.screen?.availWidth;
    const availableHeight = pipWindow.screen?.availHeight;
    if (Number.isInteger(availableWidth) && availableWidth > 0) width = Math.min(width, availableWidth);
    if (Number.isInteger(availableHeight) && availableHeight > 0) height = Math.min(height, availableHeight);
    pipWindow.resizeTo(width, height);
    return true;
  } catch {
    return false;
  }
}

export class DocumentPipUnavailableError extends Error {
  constructor() {
    super("Document Picture-in-Picture is unavailable in this browser.");
    this.name = "DocumentPipUnavailableError";
  }
}

export function supportsDocumentPip(parentWindow: Window): boolean {
  return typeof (parentWindow as DocumentPipParent).documentPictureInPicture?.requestWindow === "function";
}

/** Only reuse HTTP(S) stylesheets served by the parent application's origin. */
export function sameOriginStylesheetUrl(href: string, parentHref: string): string | null {
  try {
    const resolved = new URL(href, parentHref);
    const parent = new URL(parentHref);
    return (resolved.protocol === "http:" || resolved.protocol === "https:") && resolved.origin === parent.origin
      ? resolved.href
      : null;
  } catch {
    return null;
  }
}

const styleAttributes = ["media", "type", "title"] as const;
const linkAttributes = [...styleAttributes, "integrity", "crossorigin", "referrerpolicy", "fetchpriority"] as const;

function copyAttributes(source: Element, target: Element, names: readonly string[]): void {
  for (const name of names) {
    const value = source.getAttribute(name);
    if (value !== null) target.setAttribute(name, value);
  }
}

function prepareDocument(parentWindow: Window, pipWindow: Window): void {
  const parentDocument = parentWindow.document;
  const document = pipWindow.document;
  document.title = "Room Companion — Character Relay";
  const base = document.createElement("base");
  base.href = parentWindow.location.href;
  document.head.appendChild(base);

  // Copy CSS, never script nodes or event-handler attributes. Creating nodes
  // explicitly also avoids CSSOM access to cross-origin stylesheet rules.
  for (const source of parentDocument.querySelectorAll<HTMLStyleElement | HTMLLinkElement>("style, link[rel~='stylesheet']")) {
    if (source.tagName.toLowerCase() === "style") {
      const style = document.createElement("style");
      copyAttributes(source, style, styleAttributes);
      if (source.nonce) style.nonce = source.nonce;
      style.textContent = source.textContent;
      document.head.appendChild(style);
    } else {
      const stylesheet = source as HTMLLinkElement;
      const href = sameOriginStylesheetUrl(stylesheet.href, parentWindow.location.href);
      if (!href) continue;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      copyAttributes(source, link, linkAttributes);
      if (source.nonce) link.nonce = source.nonce;
      link.disabled = stylesheet.disabled;
      document.head.appendChild(link);
    }
  }
  // The full Portal body has a 320px minimum; native PiP can clamp below it.
  document.body.style.minWidth = "0";
}

/** Call directly from the user's click; native activation/security errors propagate. */
export async function requestRoomPip(
  parentWindow: Window,
  size: RoomPipSize = DEFAULT_ROOM_PIP_SIZE
): Promise<Window> {
  if (!isRoomPipSize(size)) throw new RangeError("Room Companion size is outside the supported limits.");
  const api = (parentWindow as DocumentPipParent).documentPictureInPicture;
  if (typeof api?.requestWindow !== "function") throw new DocumentPipUnavailableError();
  const pipWindow = await api.requestWindow({ width: size.width, height: size.height });
  try {
    prepareDocument(parentWindow, pipWindow);
  } catch (error) {
    pipWindow.close();
    throw error;
  }
  // Native cached bounds or launch settings may override the request hint. Try
  // once after opening; a browser refusing resize still leaves a usable PiP.
  resizeRoomPip(pipWindow, size);
  return pipWindow;
}

/** Closing a presentation surface never closes its shared Room session. */
export function bindRoomPipLifecycle(
  parentWindow: Window,
  pipWindow: Window,
  onClose: () => void
): () => void {
  let active = true;
  function dispose(): void {
    active = false;
    parentWindow.removeEventListener("pagehide", onParentHide);
    pipWindow.removeEventListener("pagehide", onPipHide);
  }
  function onPipHide(): void {
    if (!active) return;
    dispose();
    onClose();
  }
  function onParentHide(): void {
    if (!active) return;
    try {
      pipWindow.close();
    } finally {
      onPipHide();
    }
  }
  parentWindow.addEventListener("pagehide", onParentHide);
  pipWindow.addEventListener("pagehide", onPipHide);
  if (pipWindow.closed) onPipHide();
  return dispose;
}
