# Discord character addressing

Character Relay separates a character's Discord display identity from the names used to address that character.

## Explicit aliases

Each Discord deployment may store up to 20 address aliases, for example:

```text
安, Ann
宁, Ning
织, Zhi
```

Routing prefers these explicit aliases and still retains display-name inference for existing deployments.

## Generated character Tags

Only leading character Tags are interpreted as handoffs. Before a generated reply is sent:

- a Tag that addresses the speaking character is removed;
- Tags for other characters remain visible and are routed;
- a reply containing only a Self Tag is suppressed;
- ordinary narration containing another character name does not trigger a handoff.

Examples for Ning:

```text
@Ning 没有需要补充的。
→ 没有需要补充的。

@Ning and @Ann 这部分交给你。
→ @Ann 这部分交给你。
→ Ann is invited to respond.
```

Runtime prompt examples are generated from the actual peer aliases available in the current Discord destination. They never use a fixed character name such as `@Ning`.
