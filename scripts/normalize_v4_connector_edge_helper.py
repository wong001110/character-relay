from pathlib import Path

path = Path("scripts/apply_v4_connector_edges_ts.py")
text = path.read_text(encoding="utf-8")

old_fixture_match = '''    "  attachmentCount: 0,\\n  embedCount: 0,\\n",\n    "  attachmentCount: 0,\\n  visibleImageAttachmentCount: 0,\\n  embedCount: 0,\\n",'''
new_fixture_match = '''    "    attachmentCount: 0,\\n    embedCount: 0,\\n",\n    "    attachmentCount: 0,\\n    visibleImageAttachmentCount: 0,\\n    embedCount: 0,\\n",'''
if old_fixture_match not in text:
    raise SystemExit("turnIngress fixture replacement pattern not found")
text = text.replace(old_fixture_match, new_fixture_match, 1)

replacements = [
    ('      "真的？",\\n      1_000_000,', '      "嗯",\\n      1_000_000,'),
    ('        "然后呢？",\\n        1_001_000,', '        "哈哈",\\n        1_001_000,'),
    ('          avoid_phrases: ["不用回答"],', '          avoid_phrases: ["嗯"],'),
    ('      "不用回答",\\n      1_000_000\\n', '      "嗯",\\n      1_000_000\\n'),
]
for old, new in replacements:
    if old not in text:
        raise SystemExit(f"durable test normalization pattern not found: {old!r}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
