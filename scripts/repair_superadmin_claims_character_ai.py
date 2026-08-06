from pathlib import Path

path = Path("src/echo_masque/api/routes/deployments.py")
text = path.read_text(encoding="utf-8")
old = '''        raise HTTPException(
            status_code=403,
            detail="The managed Discord Bot is controlled by the Super Admin. Claim a Server by ID instead.",
        )
'''
new = '''        raise HTTPException(
            status_code=403,
            detail=(
                "The managed Discord Bot is controlled by the Super Admin. "
                "Claim a Server by ID instead."
            ),
        )
'''
if old not in text:
    raise SystemExit("Managed Discord connection error anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
