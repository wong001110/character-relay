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


## Dots follow-up acceptance

The optimization pass also covers the following room UX requirements before any merge:

1. **Expressions, images, and attachments**
   - render Discord custom emoji instead of raw `<:name:id>` / `<a:name:id>` tokens;
   - render stickers as message content, with a clear attachment fallback when a resource cannot render;
   - retain bounded Discord attachment metadata for Web Room display, including image preview metadata;
   - never append attachment/CDN URLs to ordinary LLM conversation prose.

2. **Reply context**
   - show reply author + bounded original-text summary instead of a raw message ID;
   - clicking a resolvable reply preview scrolls to the referenced message;
   - missing/deleted/out-of-window reply targets are explicitly labelled unavailable.

3. **Send and connection state**
   - distinguish local submitting, website accepted/pending, Discord claimed/sending, delivered, failed and uncertain;
   - same-room refresh/reconnect preserves the visible transcript;
   - only real room change, revocation, or invalid authority clears the transcript.

4. **Unread/new-message behavior**
   - never force-scroll a reader who has moved away from the bottom;
   - count newly arrived message IDs while reading history;
   - expose a "new messages" jump control that returns to the latest message and clears the local unread count.

5. **Channel expression picker**
   - Web participants can browse the current Discord server's available custom emoji and stickers;
   - the picker is room/guild scoped and returns only server resources already synchronized by the Connector;
   - emoji selection inserts a validated Discord custom-emoji token;
   - sticker selection submits a stable resource key, never an arbitrary browser-supplied asset URL;
   - backend revalidates the resource against the room owner/connection/guild catalog before Connector delivery;
   - Webhook sticker delivery uses the existing safe attachment rendering path when native webhook stickers are unavailable.

The current Portal server-catalog response exposes channels only. Connector resource sync already stores
emoji/sticker metadata in the Expression catalog, so the picker should reuse that authoritative catalog
rather than adding a second Discord scan.


6. **Message reactions**
   - subscribe to Discord guild message reaction events and re-fetch the exact message/reaction state rather than trusting unordered deltas;
   - expose bounded reaction chips on Web Room messages (emoji/custom emoji + count);
   - reaction presentation state must not enter Room Director prompts or invalidate Character drafts by itself;
   - Web Room provides a per-message reaction picker using Unicode emoji and the current guild's validated custom emoji catalog;
   - Web-origin reactions are stored with the authenticated Web profile so multiple Dots can react independently in Web Room;
   - do **not** silently claim that a Web profile owns a native Discord reaction. Discord reactions are authored by Discord users/bots, and a webhook identity cannot add a reaction;
   - if a native Discord mirror is later enabled, the Connector bot may add at most one aggregate reaction per emoji, clearly represented as bot-side mirroring rather than individual Dots identity.
