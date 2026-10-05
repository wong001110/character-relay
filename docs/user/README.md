# User guide

Use this section to connect Discord, deploy a Character, and diagnose a conversation without needing to understand the repository architecture.

## First successful Discord reply

1. [Prepare the Discord application and Bot](discord-setup.md#1-prepare-discord).
2. Add the Discord Connection and Server Profile in Deployment Center, then copy the internal Connection UUID from Connection details.
3. Create a paused Character Deployment for that Server and activate it after checking the destination.
4. Start the Discord Connector with that internal Connection UUID and the shared secret.
5. Mention the Bot in an allowed Channel and confirm the Character replies.

## Common tasks

### Room Companion

Open Rooms, choose an authorized room and an owned chat profile, then select **Pop out · Room
Companion**. Supported browsers open a Document Picture-in-Picture window with recent
messages and a quick text reply. Keep the Character Relay tab open and use a separate tab for
Gemini or other work; navigating the parent tab to another website closes PiP. **Open full room**
returns to the current room for attachments, stickers, reactions and management, keeping the
Companion open.

The Companion opens at the latest messages and follows layout changes while you remain there.
Scroll up to read older messages without being pulled back; **View latest** returns to the end.
Discord custom emoji show an image with a readable emoji name. Image/GIF attachments and embeds
show any supplied description as text, plus **View image / View GIF** to open the source in a
new tab. Missing descriptions are labelled; the Companion does not infer GIF content from a filename.

The default small window requests a **380×480 content area**. If browser settings open it at a
different size, click **Use 380×480** in the Companion to apply the default. Chromium requires a
click inside PiP to resize it, so a browser override may prevent automatic sizing on first open.
Open **Window size** to choose
**Small · 380×480**, **Medium · 480×640**, or enter custom width and height, then **Apply size**.
These are content dimensions in pixels; the native title bar and borders add to the outer window
size. Width accepts whole pixels from 320 to 2000, height from 320 to 1600. The browser may limit
the requested dimensions; the panel displays the actual current content size.

Manual and custom adjustments are remembered when closing and reopening during this Portal
page session, including across its routes. If the browser overrides the reopened size, **Use W×H**
applies the remembered choice in one click. **Small · 380×480** restores the default. Refreshing
the page or losing authentication/room access resets this preference. The Companion corrects
its size at most once on opening where the browser permits it; it does not
continually resize while you work. The size inputs apply only to native PiP.

If Document PiP is unavailable or opening is denied, the companion stays inside Character Relay;
that fallback does not remain on top of other websites. Viewing the latest messages in either
surface acknowledges the same unread count. Opening or minimizing the companion alone does not.
Pending and uncertain delivery remain visible; an unknown submission can only be checked/retried
explicitly with its original message ID. A draft containing files or a sticker must be sent from
the full room. Dots has reported successful desktop visibility, controls and draft synchronization;
close/reopen draft retention also passed in its cloud browser. Browser-controlled reopening still
requires the in-window **Use W×H** click when dimensions differ. Real incoming messages, sending
and this reading follow-up still require its actual cloud-computer validation.

### Discord and diagnostics

- [Discord setup](discord-setup.md) — permissions, Message Content Intent, Character Relay setup, worker settings, and first verification.
- [Discord debugging](discord-debugging.md) — start with structured events, then use the temporary raw capture only when needed.
- [Server workspace behavior](../discord-server-workspace.md) — Server Profiles, deployments, exclusions, Sessions, and Stickers.
- [Manual validation](../manual-validation.md) — checks that require a real Discord Server, provider, or deployment.

Character Relay currently creates new connections and deployments for Discord only. Historical WhatsApp or Telegram records can still be viewed or deleted, but those platforms do not have a supported production runtime here.
