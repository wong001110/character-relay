# Media Epistemic Observability

Character Relay separates **Runtime truth** from **Character social behavior** when a Character encounters shared media.

A Character may decide not to inspect an image, video, or article and still bluff, lie, tease, evade, or guess if that behavior fits the persona. The Runtime must not turn that role-play into false perception state.

```text
Discord content
  -> Media Attention
       action: watch | skip
       response_stance: neutral | truthful | bluff | lie | tease | evasive | guess | uncertain
  -> optional Media Understanding
  -> Runtime epistemic state
       skipped | perceived | unavailable
  -> Character reply
```

The private Media Attention decision records two different motives:

- `reason`: why the Character chose to inspect or skip the content;
- `stance_reason`: the short social motive behind how the Character intends to present itself.

`response_stance` is model-declared intent, not a post-hoc lie detector. It is selected before the final Character response and is injected back into the Character turn as private guidance. It never grants unseen media facts.

Runtime Trace adds a `turn_media_epistemic` event with bounded metadata:

- actual perception state;
- attention action and reason;
- model-declared social stance and stance note;
- deterministic stance grounding relative to the real perception state;
- Media Context count and cache-hit count;
- bounded media-resolution status.

Examples:

```text
actual_perception=skipped
response_stance=bluff
stance_grounding=intentional_without_perception
```

means the Character did not inspect the content but privately chose to present confidence or knowledge it did not actually obtain.

```text
actual_perception=perceived
response_stance=truthful
stance_grounding=grounded_in_perception
```

means the Character obtained reliable Media Context and intends to respond honestly from that perception.

The final Discord message remains free-form persona behavior. Superadmin Runtime Trace is the authoritative place to inspect the internal distinction; Provider Trace remains the place to verify whether Media Attention or Media Understanding actually called an external model.
