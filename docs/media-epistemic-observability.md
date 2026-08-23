# Media Epistemic Observability

Character Relay separates **Runtime truth** from **Character social behavior** when a Character encounters shared media.

A Character may decide not to inspect an image, video, or article and still bluff, lie, tease, evade, or guess if that behavior fits the persona. The Runtime must not turn that role-play into false perception state.

```text
Discord content
  -> Runtime media gate
       visible image attachments: passive perception
       complete Discord Embed preview: preview-grounded
       explicit content request: required Media Understanding
       uncovered shared content: optional Runtime-owned media.inspect
  -> Media Understanding only when required or media.inspect is requested
  -> Runtime epistemic state
       skipped | perceived | unavailable
  -> Character reply
```

The dedicated Media Attention LLM pre-pass is no longer used. Runtime makes the deterministic
epistemic gate first. A Discord-visible Embed can ground title/provider/author/description
metadata, but it does not establish perception of a linked GIF's motion, unseen frames, audio,
or page contents. Multiple attachments are handled as one bounded batch: passive image
attachments are separated from unpreviewed media so one visible preview cannot hide another
inspection-eligible item.

Runtime Trace adds a `turn_media_epistemic` event with bounded metadata:

- actual perception state;
- attention action (`passive`, `preview`, `required`, `watch`, or `skip`) and reason;
- Media Context count and cache-hit count;
- bounded media-resolution status.

Examples:

```text
actual_perception=skipped
attention_action=preview
media_result_reason=visible_link_preview_only
```

means the Character had a human-visible Discord preview but did not inspect the linked content.
It may react to the displayed metadata, but must not claim to have seen the GIF animation or
other unseen details.

```text
actual_perception=perceived
attention_action=required
```

means Runtime obtained reliable Media Context before Character generation because the current
turn required content understanding.

The final Discord message remains free-form persona behavior. Runtime Trace is the authoritative
place to inspect the distinction; Provider Trace verifies whether Media Understanding actually
called an external model. Raw media content and provider payloads do not belong in ordinary
diagnostic events.
