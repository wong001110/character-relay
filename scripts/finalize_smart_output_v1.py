from pathlib import Path


path = Path("tests/test_character_prompt_inspector.py")
text = path.read_text(encoding="utf-8")
old = 'assert prompt["compiler_version"] == "character-relay-compiler-v2"'
new = 'assert prompt["compiler_version"] == "character-relay-compiler-v3"'
if text.count(old) != 1:
    raise SystemExit("Expected exactly one legacy compiler-version assertion")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Smart Output V1 final test compatibility update applied.")
