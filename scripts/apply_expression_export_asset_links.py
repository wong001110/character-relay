from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/ServerStickerDictionary.tsx",
    '''  function exportJson() {
    const document = {
      version: 1,
      kind: "character-relay-expression-dictionary",
      server: {
        profile_id: profile.id,
        guild_id: profile.guild_id,
        guild_name: profile.guild_name,
        workspace_name: profile.name
      },
      exported_at: new Date().toISOString(),
      expressions: resources.map((item) => ({
        resource_key: item.resource_key,
        resource_type: item.resource_type,
        resource_id: item.resource_id,
        name: item.name,
        enabled: item.enabled,
        semantic_intent: item.semantic_intent,
        semantic_emotion: item.semantic_emotion,
        semantic_description: item.semantic_description,
        aliases: item.aliases,
        situations: item.situations,
        avoid_when: item.avoid_when,
        allowed_actions: item.allowed_actions
      }))
    };
''',
    '''  function exportJson() {
    const document = {
      version: 2,
      kind: "character-relay-expression-dictionary",
      agent_guidance: {
        purpose:
          "Review each Discord Emoji or Sticker visually, then draft semantic fields for Character Relay.",
        visual_analysis:
          "Open each asset_url with a vision-capable tool before deciding its meaning. Animated assets may require viewing the full animation.",
        editable_fields: [
          "enabled",
          "semantic_intent",
          "semantic_emotion",
          "semantic_description",
          "aliases",
          "situations",
          "avoid_when",
          "allowed_actions"
        ],
        readonly_fields: [
          "resource_key",
          "resource_type",
          "resource_id",
          "name",
          "description",
          "tags",
          "asset_url",
          "format_type",
          "animated",
          "available"
        ],
        uncertainty_rule:
          "When the visual meaning is unclear, keep the semantic fields empty or mark the uncertainty for human review. Do not infer meaning from the filename alone."
      },
      server: {
        profile_id: profile.id,
        guild_id: profile.guild_id,
        guild_name: profile.guild_name,
        workspace_name: profile.name
      },
      exported_at: new Date().toISOString(),
      expressions: resources.map((item) => ({
        resource_key: item.resource_key,
        resource_type: item.resource_type,
        resource_id: item.resource_id,
        name: item.name,
        description: item.description,
        tags: item.tags,
        asset_url: item.asset_url,
        format_type: item.format_type,
        animated: item.animated,
        available: item.available,
        enabled: item.enabled,
        semantic_intent: item.semantic_intent,
        semantic_emotion: item.semantic_emotion,
        semantic_description: item.semantic_description,
        aliases: item.aliases,
        situations: item.situations,
        avoid_when: item.avoid_when,
        allowed_actions: item.allowed_actions
      }))
    };
''',
)

replace_once(
    "web/src/ServerStickerDictionary.tsx",
    '''    setNotice(zh ? "已导出当前 Server 的 Expression JSON。" : "Exported this Server's Expression JSON.");
''',
    '''    setNotice(
      zh
        ? "已导出包含 Emoji／Sticker 图片链接与 AI Agent 指引的 Expression JSON。"
        : "Exported Expression JSON with Emoji/Sticker image links and AI-agent guidance."
    );
''',
)

replace_once(
    "web/src/ServerStickerDictionary.tsx",
    '''            {zh ? "导出 JSON" : "Export JSON"}
''',
    '''            {zh ? "导出 JSON + 图片链接" : "Export JSON + image links"}
''',
)
