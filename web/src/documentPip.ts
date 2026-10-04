interface DocumentPictureInPictureApi {
  requestWindow(options: { width: number; height: number }): Promise<Window>;
}

type DocumentPipParent = Window & {
  documentPictureInPicture?: DocumentPictureInPictureApi;
};

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
export async function requestRoomPip(parentWindow: Window): Promise<Window> {
  const api = (parentWindow as DocumentPipParent).documentPictureInPicture;
  if (typeof api?.requestWindow !== "function") throw new DocumentPipUnavailableError();
  const pipWindow = await api.requestWindow({ width: 380, height: 480 });
  try {
    prepareDocument(parentWindow, pipWindow);
    return pipWindow;
  } catch (error) {
    pipWindow.close();
    throw error;
  }
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
