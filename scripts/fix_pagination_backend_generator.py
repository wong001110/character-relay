from pathlib import Path

path = Path("scripts/apply_pagination_backend.py")
text = path.read_text()
anchor = '''def append_once(path: str, marker: str, content: str) -> None:
    target = Path(path)
    text = target.read_text()
    if marker in text:
        return
    if not text.endswith("\\n"):
        text += "\\n"
    target.write_text(text + "\\n" + dedent(content).lstrip())


'''
helper = anchor + '''def class_block(content: str) -> str:
    value = dedent(content).lstrip()
    return "\\n".join(f"    {line}" if line else "" for line in value.splitlines()) + "\\n"


'''
if anchor not in text:
    raise SystemExit("Generator helper anchor was not found.")
text = text.replace(anchor, helper, 1)
for marker in (
    "def list_tasks_page(",
    "def list_traces_page(",
    "def list_audit_events_page(",
    "def list_deployments_page(",
):
    position = text.find(marker)
    if position < 0:
        raise SystemExit(f"Generator block was not found: {marker}")
    start = text.rfind("    dedent(\n", 0, position)
    if start < 0:
        raise SystemExit(f"Generator dedent call was not found: {marker}")
    text = text[:start] + "    class_block(\n" + text[start + len("    dedent(\n"):]
    position = text.find(marker)
    closing = text.find("\n    ).lstrip(),", position)
    if closing < 0:
        raise SystemExit(f"Generator block closing was not found: {marker}")
    text = text[:closing] + "\n    )," + text[closing + len("\n    ).lstrip(),"):]
path.write_text(text)
Path(__file__).unlink()
