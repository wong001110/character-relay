from pathlib import Path

path = Path("scripts/apply_expression_connector.py")
text = path.read_text(encoding="utf-8")
old = '''replace_once(
    "connectors/discord/src/index.ts",
    \'\'\'          hasReadableText: Boolean(originalText),
          sticker_count: guildMessage.stickers.size\'\'\',
    \'\'\'          hasReadableText: Boolean(originalText || parseCustomEmojiTokens(guildMessage.content).length),
          custom_emoji_count: parseCustomEmojiTokens(guildMessage.content).length,
          sticker_count: guildMessage.stickers.size\'\'\',
)'''
new = '''replace_once(
    "connectors/discord/src/index.ts",
    \'\'\'  hasReadableText: Boolean(originalText),
  stickerCount: guildMessage.stickers.size,\'\'\',
    \'\'\'  hasReadableText: Boolean(originalText || parseCustomEmojiTokens(guildMessage.content).length),
  customEmojiCount: parseCustomEmojiTokens(guildMessage.content).length,
  stickerCount: guildMessage.stickers.size,\'\'\',
)'''
if old not in text:
    raise SystemExit("Connector anchor repair target not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
