from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing patch anchor: {path}: {old[:100]!r}")
    if text.count(old) != 1:
        raise SystemExit(f"non-unique patch anchor: {path}: {old[:100]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/ConversationIntelligenceInspector.tsx",
    '''  const channels = useMemo(
    () => (catalog?.channels ?? []).filter((item) => !profile.excluded_channel_ids.includes(item.id)),
    [catalog, profile.excluded_channel_ids]
  );
''',
    '''  const channels = useMemo(
    () => (catalog?.channels ?? []).filter(
      (item) =>
        !profile.excluded_channel_ids.includes(item.id)
        && (!item.category_id || !profile.excluded_category_ids.includes(item.category_id))
    ),
    [catalog, profile.excluded_category_ids, profile.excluded_channel_ids]
  );
''',
)
replace_once(
    "web/src/ConversationIntelligenceInspector.tsx",
    "                    <strong>{item.subject_key}</strong>\n",
    "                    <strong>{item.subject_label || item.subject_key}</strong>\n",
)
