from pathlib import Path

path = Path("src/echo_masque/connector_runtime.py")
text = path.read_text(encoding="utf-8")
old = '''                "To intentionally invite another character to answer, you may begin your reply with @ "
                "followed by one of the listed character Tags, or place the same Tag "
'''
new = '''                "To intentionally invite another character to answer, you may "
                "begin your reply with @ followed by one of the listed character Tags, "
                "or place the same Tag "
'''
if old not in text:
    raise SystemExit("Inline handoff prompt formatting anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
