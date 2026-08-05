from pathlib import Path

path = Path("web/src/CharacterShelf.tsx")
text = path.read_text(encoding="utf-8")
old = '''            <h1>Character Relay</h1>
            <p>'''
new = '''            <h1 className="brand-accessible-title">Character Relay</h1>
            <p>'''
if old not in text:
    raise SystemExit("Brand title anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

css_path = Path("web/src/notebook-ui.css")
css = css_path.read_text(encoding="utf-8")
addition = '''

.brand-accessible-title {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}
'''
if ".brand-accessible-title" not in css:
    css_path.write_text(css + addition, encoding="utf-8")
