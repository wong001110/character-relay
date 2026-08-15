from pathlib import Path

path = Path("web/src/styles.css")
text = path.read_text(encoding="utf-8")
marker = "/* Conversation Burst Live Observation */"
index = text.find(marker)
if index < 0:
    raise SystemExit("Conversation Burst Live Observation marker not found")
prefix = text[:index]
suffix = text[index:]
suffix = suffix.replace("\\\n", "\n")
suffix = suffix.replace("\\n", "\n")
path.write_text(prefix + suffix, encoding="utf-8")
