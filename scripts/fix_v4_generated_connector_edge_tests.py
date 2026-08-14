from pathlib import Path

path = Path("connectors/discord/src/turnIngress.test.ts")
text = path.read_text(encoding="utf-8")
marker = '\n\ndescribe("visible-image Turn Collection policy", () => {'
fixture = '''

const basePolicy = {
  collectorEnabled: true,
  smartParticipationEnabled: true,
  recovery: false,
  mentionedBot: false,
  hasReplyReference: false,
  explicitAudience: false,
  hasReadableText: true,
  customEmojiCount: 0,
  stickerCount: 0,
  attachmentCount: 0,
  visibleImageAttachmentCount: 0,
  embedCount: 0,
  hasUrl: false,
  smartCandidateCount: 2
};

describe("visible-image Turn Collection policy", () => {'''
if marker not in text:
    raise SystemExit("generated visible-image test marker not found")
path.write_text(text.replace(marker, fixture, 1), encoding="utf-8")
