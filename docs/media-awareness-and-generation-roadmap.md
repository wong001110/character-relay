# Media Awareness, Key Groups, and Image Generation Roadmap

This document records the agreed Character Relay direction for account-level provider credentials, shared media understanding, public-content resolution, and image generation.

## 1. Product boundary

Character Relay must remain provider-agnostic. OpenRouter is one optional provider, not a platform dependency.

Each account may configure different providers for different capabilities:

```text
Character / Text
Media Understanding
Image Generation
```

A user may therefore use DeepSeek Direct for character turns, Xiaomi/MiMo Direct or OpenRouter for media, and Cloudflare/OpenRouter/another image provider for generation. Runtime code consumes capability interfaces rather than provider names.

## 2. Account-level Key Groups

Repeatedly storing the same API key on every Character Card is intentionally replaced by reusable account-owned **Key Groups**.

A Key Group stores:

- owner account;
- friendly name;
- provider identifier;
- provider base URL when required;
- encrypted API credential in the existing Credential Vault;
- optional default model per capability.

Character Cards bind a Key Group by capability and may optionally override the group's default model.

```text
Account
  ├─ Key Group: DeepSeek Main
  ├─ Key Group: OpenRouter Main
  └─ Key Group: Xiaomi Media

Character A
  ├─ character -> DeepSeek Main
  ├─ media -> Xiaomi Media
  └─ image_generation -> OpenRouter Main

Character B
  ├─ character -> DeepSeek Main
  └─ media -> Xiaomi Media
```

Direct per-character credentials remain a compatibility/override path. For character inference, direct credential wins first; assigned Key Group is the fallback. This allows existing cards to keep working while accounts migrate gradually.

Key Groups must never return plaintext API keys through account APIs. Updating a group rotates the secret once for every assigned Character Card.

## 3. Shared Media Understanding

Media understanding belongs to the media/message content, not to an individual bot.

If Bot A has already understood an attachment, Bot B must reuse the same objective Media Context rather than call the multimodal provider again.

```text
Media
  -> resolve content identity
  -> global Media Analysis cache
      -> HIT: reuse objective context
      -> MISS: provider analysis -> cache
  -> Character Runtime
      -> Bot A interprets through its persona
      -> Bot B interprets through its persona
```

The shared cache is **content-only**. It must not contain guild IDs, user IDs, character persona, surrounding conversation, or a previous bot's subjective reply. Cache administration is Superadmin-only.

### 3.1 In-flight deduplication / single-flight

A cache alone is insufficient because another Character or worker can request the same media while the first provider call is still running.

Every provider-analysis identity therefore has an explicit state:

```text
MISS
PROCESSING
READY
FAILED
```

The identity is based on:

```text
media_key
+ analysis_version
+ provider
+ model
```

The first worker atomically claims a short processing lease and becomes the provider-call owner. Later requests for the same identity join the existing in-flight task or wait for the shared record; they do not start another multimodal request.

```text
Bot A -> claim -> PROCESSING -> provider call
Bot B -> sees PROCESSING -> join/wait
Bot C -> sees PROCESSING -> join/wait
                         -> READY
                         -> one shared Media Context
```

Within one application process, callers share the same async Future so they do not repeatedly poll SQLite. Across multiple backend workers, the SQL unique identity plus processing lease provides cross-worker provider-analysis deduplication.

A crashed/stalled worker cannot leave the media permanently locked. `lease_expires_at` allows another worker to reclaim an expired `PROCESSING` record. Recent failures use a short cooldown so many waiting Characters do not immediately stampede the provider after one failure.

**Target queue behavior:** media inference should not block the channel-wide Discord ingestion queue. The current live slice still performs media resolution inside the Character request made from the connector's serial destination queue, so queue decoupling remains pending in Phase B.

## 4. Content identity and streaming SHA-256

For binary uploads and Discord attachments, Character Relay computes SHA-256 while the file is already streaming through the resolver. It does not make a second pass over the file and does not load a large video into memory only to calculate the hash.

```text
incoming stream
  -> safe streaming fetch
  -> SHA-256.update(chunk) at the same time
  -> media key: sha256:<digest>
```

SHA-256 is fixed-size: 32 binary bytes (64 hexadecimal characters), independent of media size.

For public platforms, stable canonical source IDs are preferred before downloading large media when available, for example:

- `youtube:<video-id>`
- `bilibili:<bvid>`
- `x:<post-id>`
- `tiktok:<video-id>`
- `facebook:<video-id>`
- `instagram:<shortcode>`
- `vimeo:<video-id>`

Binary SHA-256 remains the fallback and deduplication identity for attachments or sources without a trustworthy canonical ID.

The live Discord slice has three main dedupe layers:

```text
same Discord message -> attachment metadata/source task reuse
same attachment/direct binary -> source task + streaming SHA-256 reuse
same content/provider/model -> global Media Analysis cache + single-flight
```

A re-upload of the same binary under a new Discord attachment ID may still need to stream/hash again to prove content equality, but the resulting SHA-256 can reuse the existing provider analysis.

### 4.1 URL Content Resolver

A posted link is not automatically a multimodal-provider request. URLs first pass through a provider-neutral Content Resolver that classifies the source and derives the cheapest reusable identity available before network-heavy extraction.

```text
URL
 -> canonicalize / remove tracking fragments
 -> classify source
    ├─ article
    ├─ direct image
    ├─ direct video/audio
    ├─ public platform video/social post
    └─ unresolved/partial
 -> canonical source key
 -> extraction/media pipeline
```

The static resolver derives canonical keys for common URL shapes without performing a fetch. Current classifications include YouTube, Bilibili/b23, TikTok, X/Twitter, Facebook video/reel URLs, Instagram reels/posts, Vimeo, direct media extensions, and generic article URLs.

### 4.2 Public video / social platform pipeline

Recognized platform video URLs now use an embedded `yt-dlp` resolver rather than sending a YouTube/Bilibili/TikTok page URL directly to the multimodal model.

```text
platform URL
 -> canonical source key
 -> yt-dlp extract_info(download=False)
 -> metadata
 -> manual subtitles, if available
 -> automatic captions, if manual subtitles are unavailable
 -> direct media URL, if a suitable public format is available
 -> optional multimodal visual analysis
 -> merge transcript + visual observations
 -> Shared Media Context
```

The resolver does not download the full video merely to discover metadata or subtitles. It uses an in-process one-hour source-resolution cache so repeated canonical links do not repeatedly run extraction during normal traffic.

Runtime support includes `yt-dlp[default,curl-cffi]`, ffmpeg/ffprobe, the yt-dlp EJS package supplied by the default dependency group, and an explicit Node 22 runtime for current YouTube JavaScript challenge support.

If a direct media URL cannot be obtained, or if the selected multimodal provider cannot consume it, Character Relay falls back to the reusable title/description/transcript context rather than failing the Character turn. A Media Vision Key is therefore an enhancement for visual understanding, not a prerequisite for using public subtitles/metadata.

No cookies, login sessions, or access-control bypasses are added by this pipeline. Private, region/account-restricted, or otherwise unavailable media may still be unresolved.

### 4.3 Article pipeline — Jina Reader first

Generic article links now prefer Jina Reader rather than treating the raw webpage title/body extractor as the primary path.

```text
article URL
 -> Jina ReaderLM-v2 structured extraction
      -> concise factual summary
      -> cleaned main article content
      -> title / published time where available
 -> if structured Reader is unavailable: normal Jina Reader
 -> if Jina is unavailable: local HTTP extraction
 -> if HTTP is insufficient / JavaScript-heavy: Chromium rendered fallback
 -> Shared Media Context
```

The structured Reader request asks for a short factual summary and cleaned article content while retaining enough body text for follow-up questions. The Character model receives both the summary and bounded cleaned content; it still decides how to respond through the Character persona.

Jina article results use the `article-v3` cache identity. Article cache uses a seven-day sliding TTL, while the local HTTP/Chromium fallback has a separate cache identity. This intentionally keeps changing webpages shorter-lived than stable binary media analysis.

## 5. Cache TTL and cleanup

The global Media Analysis cache is not permanent knowledge storage.

V1 uses the existing SQL database and an indexed `expires_at`; Redis is deliberately not required. Expired entries are deleted through bounded lazy/background cleanup rather than a full-table scan on each message.

Current initial policy:

- general image/video provider analysis: 30 days;
- article/Jina and article fallback content: 7 days;
- detailed/segment analysis: target 7-14 days;
- public canonical video analysis may later use longer TTLs where measured reuse justifies it;
- refresh a sliding TTL only when the previous access refresh is sufficiently old, preventing viral content from causing a database write on every cache hit.

The cache key also includes analysis schema/model identity so a future analysis upgrade can coexist with or lazily replace older results.

## 6. Media analysis levels

Media analysis is demand-driven.

### Level 0 — metadata / transcript

No multimodal inference. MIME type, file size, source, title/duration, public-platform metadata, and subtitles/transcripts where available.

### Level 1 — general understanding

One objective reusable description: summary, visible text, people/objects, notable events/details, broad tone/context, plus platform transcript metadata where available.

The live Discord slice injects Level-1 context into the Character prompt before Smart Output. Embedded media/page instructions are explicitly marked untrusted so they are observations, not commands.

### Level 2 — detailed analysis

A deeper analysis requested by the runtime when general context is insufficient.

### Level 3 — segment analysis

A bounded video/audio time range or selected frames, used for questions such as "what is written at 01:43?" without reprocessing the entire video.

Levels 2-3 extend the same cache contract later.

## 7. Media provider architecture

The first provider interfaces are:

```text
MediaUnderstandingProvider
ImageGenerationProvider
```

The runtime sees normalized requests/results. Provider-specific adapters sit underneath them.

Current live Media Understanding adapter support:

- OpenRouter through its OpenAI-compatible chat-completions route;
- custom/OpenAI-compatible multimodal endpoints with explicit Base URL;
- image URL input;
- video URL input when the chosen provider/model supports it;
- provider-independent yt-dlp metadata/subtitle resolution before visual inference;
- provider-independent Jina/article extraction before the Character model.

The provider adapter asks for an objective JSON description but does not require the provider's structured-output capability, improving compatibility with more multimodal models.

Credential-bearing provider instances are scoped to one Key Group. The objective Media Analysis cache is still global by content/provider/model, so identical media can reuse the result without reusing another account's provider instance or plaintext credential.

Direct MiMo/Xiaomi-specific API wiring is still pending; MiMo can already be selected through a compatible OpenRouter Key Group when supported there.

DeepSeek (or any configured character model) remains responsible for personality, social decisions, tool calling, and the final character response. Media models and content extractors return objective context rather than role-playing as the Character Card.

## 8. Image generation

Image generation is a separate capability from image understanding.

```text
Character Runtime
  -> decides that an image should be generated
  -> ImageGenerationProvider
  -> generated asset
  -> Discord delivery
```

The provider layer must support, as capabilities allow:

- text-to-image;
- aspect ratio / resolution;
- reference images for character consistency;
- provider-specific quality settings without leaking those details into Character Runtime.

The initial implementation adds the provider-neutral request/result contract. OpenRouter's image endpoint is an optional first adapter; direct provider adapters can be added without changing Tool Calling or Character Card behavior.

## 9. Security and privacy

- API credentials stay encrypted in the existing Credential Vault.
- Key Group list/status endpoints expose metadata only, never plaintext keys.
- Credential-bearing Media provider instances are isolated by Key Group.
- Shared Media Analysis contains only media-derived objective context.
- Cache-hit status and global cache metadata are Superadmin-only observability.
- Raw private Discord attachments are not retained merely for caching; the resolver stores digest/metadata/context, not the binary body.
- Direct URL/media fetches pass the existing public-destination/redirect SSRF guard before downloading content.
- Platform extraction is limited to recognized public platform hosts and does not add cookies/login bypasses.
- Media/page/transcript text is marked untrusted before being injected into Character Runtime.
- Deleting a Key Group removes its assignments and encrypted secret.

## 10. Current testable vertical slice

After this branch is merged and deployed, an account can open **Account & Security -> Data & account -> Key Groups**, create an OpenRouter/custom-compatible Key Group, set a Media model, select Character Cards, and bulk-apply the **Media Understanding** capability.

### Discord image / direct media

```text
@Character + Discord image attachment
 -> Connector attachment metadata
 -> stream + SHA-256
 -> global cache / single-flight
 -> multimodal provider
 -> objective Media Context
 -> Character prompt
 -> persona-aware reply
```

### Public platform video

```text
YouTube / Bilibili / TikTok / supported public platform URL
 -> canonical source key
 -> yt-dlp metadata + subtitles/captions
 -> direct media URL when available
 -> optional multimodal visual analysis
 -> merged Media Context
 -> Character reply
```

If no Media Vision Key is assigned, a public video can still produce a Character response from the extracted transcript/title/description when available.

### Article

```text
article URL
 -> Jina ReaderLM-v2 summary + clean main content
 -> normal Jina Reader fallback
 -> HTTP fallback
 -> Chromium fallback
 -> Character Media Context
```

Also supported:

- direct public image URL -> streaming SHA-256 -> Media Understanding;
- Discord-uploaded/direct video URL -> video URL analysis when the selected provider/model supports it;
- multiple Characters inspecting the same media -> shared content analysis rather than duplicate provider inference;
- Facebook/Instagram/Vimeo public video URL classification in addition to the existing YouTube/Bilibili/TikTok/X handling.

Still not guaranteed:

- private/login-required/region-restricted platform media;
- every platform's signed direct-media URL being fetchable by every third-party multimodal provider; transcript/metadata fallback remains available where yt-dlp can extract it;
- proactive Smart Participation on an attachment-only message with no text/mention;
- channel-wide queue decoupling while slow media resolution/provider inference is in flight;
- audio understanding;
- Generate Image tool execution/delivery.

## 11. Delivery sequence

### Phase A — foundation

1. Add account-owned Key Group metadata and encrypted group credentials. ✅
2. Add per-Character capability assignment and bulk apply backend API. ✅
3. Resolve character credentials as direct-card override -> assigned Key Group fallback. ✅
4. Add streaming SHA-256 helper for attachment pipelines. ✅
5. Add global Media Analysis persistence with TTL, bounded cleanup, and sliding-access refresh. ✅
6. Add provider-neutral Media Understanding and Image Generation contracts. ✅
7. Add Media Analysis single-flight state, cross-worker processing lease, and in-process Future sharing. ✅
8. Add static URL classification/canonical source-key resolver foundation. ✅
9. Add Portal Key Group management and multi-Character bulk-apply UI. ✅

### Phase B — live Media Understanding

10. Add Discord current-message attachment resolution, metadata/source dedupe, and streaming SHA-256. ✅
11. Add SSRF-safe direct public media URL fetch + redirect revalidation. ✅
12. Add Jina ReaderLM-v2 article summary/clean-content path with seven-day article TTL and HTTP/Chromium fallbacks. ✅
13. Add OpenRouter/OpenAI-compatible multimodal adapter. ✅
14. Add direct Xiaomi/MiMo provider adapter. ⬜
15. Inject shared Level-1 Media Context into Character Runtime before Smart Output. ✅
16. Add platform video/social extraction with yt-dlp metadata, subtitles/captions, direct-media resolution, and text fallback. ✅
17. Move slow media resolution/inference outside the channel-wide Discord serial queue. ⬜
18. Add deployment/account controls for which media types characters may inspect. ⬜
19. Add Superadmin cache observability, processing-state visibility, and manual purge controls. ⬜

### Phase C — Generate Image

20. Register `image.generate` as an explicitly assignable Tool. ⬜
21. Resolve the Character Card's `image_generation` Key Group/model. ⬜
22. Keep the OpenRouter Image API adapter as one optional provider. ✅ foundation adapter
23. Add direct provider adapters where useful (Cloudflare, MiniMax, Wan, etc.). ⬜
24. Add Character reference-image handling and capability-aware model parameters. ⬜
25. Deliver generated images through the current Discord identity while preserving Runtime permission/audit rules. ⬜

### Phase D — deeper media

26. Add Level-2 question-specific media analysis. ⬜
27. Add Level-3 timestamp/segment cache entries for video. ⬜
28. Measure hit rate, provider spend, latency, database size, processing contention, and TTL effectiveness before adding Redis or another hot cache. ⬜

## 12. Non-goals for V1

- No mandatory OpenRouter dependency.
- No per-bot duplicate media analysis.
- No duplicate provider call while the same analysis identity is already processing.
- No permanent raw-media archive just for cache hits.
- No Redis until measured traffic justifies it.
- No persona-specific text stored in global Media Analysis.
- No automatic full-video download/analysis for every link merely because it appears in a channel.
