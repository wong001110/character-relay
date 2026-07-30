from pathlib import Path

path = Path("README.md")
text = path.read_text()
for heading in (
    "### Phase 15 — Authentication, User Isolation, and Secure Credential Vault",
    "### Phase 16 — AI-generated Scenario Authoring, Calibration Datasets, and Evaluation Analytics",
):
    start = text.index(heading)
    marker = text.index("Implemented deliverables:", start)
    text = text[:marker] + "Planned deliverables:" + text[marker + len("Implemented deliverables:"):]
path.write_text(text)
Path("scripts/phase14_readme_fix.py").unlink()
Path(".github/workflows/phase14-readme-fix.yml").unlink()
