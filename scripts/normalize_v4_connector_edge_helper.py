from pathlib import Path

path = Path("scripts/apply_v4_connector_edges_ts.py")
text = path.read_text(encoding="utf-8")

old_fixture_match = '''    "  attachmentCount: 0,\\n  embedCount: 0,\\n",\n    "  attachmentCount: 0,\\n  visibleImageAttachmentCount: 0,\\n  embedCount: 0,\\n",'''
new_fixture_match = '''    "    attachmentCount: 0,\\n    embedCount: 0,\\n",\n    "    attachmentCount: 0,\\n    visibleImageAttachmentCount: 0,\\n    embedCount: 0,\\n",'''
if old_fixture_match not in text:
    raise SystemExit("turnIngress fixture replacement pattern not found")
text = text.replace(old_fixture_match, new_fixture_match, 1)

old_generated_block = '''    ''' + "'''\\n\\ndescribe(\"visible-image Turn Collection policy\", () => {" + "'''"
base_policy = '''    ''' + "'''\\n\\nconst basePolicy = {\\n  collectorEnabled: true,\\n  smartParticipationEnabled: true,\\n  recovery: false,\\n  mentionedBot: false,\\n  hasReplyReference: false,\\n  explicitAudience: false,\\n  hasReadableText: true,\\n  customEmojiCount: 0,\\n  stickerCount: 0,\\n  attachmentCount: 0,\\n  visibleImageAttachmentCount: 0,\\n  embedCount: 0,\\n  hasUrl: false,\\n  smartCandidateCount: 2\\n};\\n\\ndescribe(\"visible-image Turn Collection policy\", () => {" + "'''"
if old_generated_block not in text:
    raise SystemExit("generated visible-image test block marker not found")
text = text.replace(old_generated_block, base_policy, 1)

path.write_text(text, encoding="utf-8")
