# Web Room optimization

Working branch: `feature/web-room-optimization`. Do not merge to main until the user closes the current follow-up pass.

## Current UX fixes

- Preserve the current transcript while the same room refreshes or SSE reconnects.
- Clear transcript only on a real room change, revocation, or invalid snapshot.
- Keep stable Discord message IDs as React keys so unchanged messages stay mounted.

## Discord media boundary

Discord message attachments are metadata records with a source `url`, proxied `proxy_url`,
filename, MIME type, size and optional image/video dimensions. The Connector already retrieves this
metadata for the media-understanding runtime.

Web Room and Character perception are deliberately separate:

1. **Presentation path** — persist a bounded attachment descriptor on the room source and expose it
   to the authenticated Web Room snapshot. Render image attachments directly from the Discord URL
   (prefer the proxied URL when usable). This metadata is display evidence, not prompt text.
2. **Perception path** — do not append CDN URLs to conversational prose. The existing live-media
   runtime resolves image/video attachments as media assets, applies the media capability/provider
   boundary, and injects bounded analysis/observations into the Character prompt. If perception is
   unavailable, the Character must treat image details as unknown.
3. **Routing path** — Room Director/routing sees only `has_unseen_media` / media fingerprint and
   ordinary text. Attachment URLs, filenames and binary data are not serialized into routing prompts.

## Planned rendering follow-ups

- custom Discord emoji: convert Discord token metadata to inline image rendering;
- sticker: retain resource metadata and render as a separate image block;
- image attachments: retain URL/proxy URL + safe metadata and render image previews;
- ordinary files: show a bounded file card/link later; do not fetch arbitrary file contents in the browser;
- edits/deletes: replace descriptors from the same Discord message version and erase them on tombstone.

Discord attachment URLs are transport references, not a permanent media archive. Long-lived recall
must continue to depend on source identity and the existing media/perception cache rather than treating
a stale CDN URL as durable truth.
