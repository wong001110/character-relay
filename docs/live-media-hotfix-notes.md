# Live Media Ingestion Hotfix

This hotfix addresses two production test failures observed after the first live Media Understanding merge.

## Discord attachments

The Discord Connector now resolves current message attachment metadata inside the Connector service and sends it with the inbound Character Runtime payload. The backend consumes this metadata first and only falls back to its own Discord REST lookup when connector metadata is unavailable.

This removes the accidental requirement that the backend service must also possess the Connector's `DISCORD_BOT_TOKEN` just to discover an attachment.

Only metadata is relayed (ID, CDN/proxy URL, filename, MIME type, size and dimensions). Raw media bytes are still streamed only by the media resolver, hashed with streaming SHA-256 and not retained merely for cache reuse.

## Public article links

Article resolution remains HTTP-first. When the HTTP result is unavailable, JavaScript-gated, or too small to be useful, Media Understanding now reuses the existing short-lived Playwright/Chromium Browser Capability and extracts rendered page text.

Rendered article results use a new `article-v2` cache identity so an older V1 extraction does not hide the improved resolver behavior.
