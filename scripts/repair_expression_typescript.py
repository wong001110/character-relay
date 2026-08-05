from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "connectors/discord/src/expressionFlow.ts",
    '''  if (decision.action === "none") return null;
  return (
    candidates.find(
      (item) =>
        !excludedResourceKeys.has(item.resource_key) &&
        item.allowed_actions.includes(decision.action)
    ) ?? null
  );''',
    '''  const action = decision.action;
  if (action === "none") return null;
  return (
    candidates.find(
      (item) =>
        !excludedResourceKeys.has(item.resource_key) &&
        item.allowed_actions.includes(action)
    ) ?? null
  );''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''        const sent = await source.reply({
          content: visibleText || undefined,
          stickers: [candidate.resource_id],
          allowedMentions: { parse: [], repliedUser: false }
        });''',
    '''        const sent = await source.reply({
          ...(visibleText ? { content: visibleText } : {}),
          stickers: [candidate.resource_id],
          allowedMentions: { parse: [], repliedUser: false }
        });''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''  authorDisplayName: string,
  originalText: string,
  stickers: DiscordStickerContent[]
): Promise<boolean> {''',
    '''  authorDisplayName: string,
  originalText: string,
  emojis: DiscordExpressionContent[],
  stickers: DiscordStickerContent[]
): Promise<boolean> {''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''        authorDisplayName,
        originalText,
        stickers
      )''',
    '''        authorDisplayName,
        originalText,
        emojis,
        stickers
      )''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''          hasReadableText: Boolean(audience.text || originalText || stickers.length)''',
    '''          hasReadableText: Boolean(
            audience.text || originalText || emojis.length || stickers.length
          )''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''          (stickers.length
            ? "The user addressed the character with interpreted Sticker content and no text."
            : "The user addressed the character without additional readable text."),''',
    '''          (emojis.length || stickers.length
            ? "The user addressed the character with interpreted Discord expression content and no text."
            : "The user addressed the character without additional readable text."),''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''            originalText ||
            "The target member sent interpreted Discord Sticker content without text.",''',
    '''            originalText ||
            "The target member sent interpreted Discord expression content without text.",''',
)
