from pathlib import Path

path = Path("scripts/apply_server_workspace_backend.py")
text = path.read_text(encoding="utf-8")
old = '''def seed_server(client: TestClient) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
'''
new = '''def seed_server(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
'''
if old not in text:
    raise RuntimeError("seed_server signature not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
