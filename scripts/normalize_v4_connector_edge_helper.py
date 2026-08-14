from pathlib import Path

path = Path("scripts/apply_v4_connector_edges_ts.py")
text = path.read_text(encoding="utf-8")

old_fixture_match = '''    "  attachmentCount: 0,\\n  embedCount: 0,\\n",\n    "  attachmentCount: 0,\\n  visibleImageAttachmentCount: 0,\\n  embedCount: 0,\\n",'''
new_fixture_match = '''    "    attachmentCount: 0,\\n    embedCount: 0,\\n",\n    "    attachmentCount: 0,\\n    visibleImageAttachmentCount: 0,\\n    embedCount: 0,\\n",'''
if old_fixture_match not in text:
    raise SystemExit("turnIngress fixture replacement pattern not found")

path.write_text(text.replace(old_fixture_match, new_fixture_match, 1), encoding="utf-8")
