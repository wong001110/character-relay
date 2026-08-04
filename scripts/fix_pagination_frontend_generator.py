from pathlib import Path

path = Path("scripts/apply_pagination_frontend.py")
text = path.read_text()
paused = """replace_once(
    \"web/src/DeploymentCenter.tsx\",
    '''          <strong>{counts.paused}</strong>''',
    '''          <strong>{deploymentCounts.paused}</strong>''',
)
"""
if paused not in text:
    raise SystemExit("Paused summary replacement was not found.")
text = text.replace(paused, "", 1)
active = """replace_once(
    \"web/src/DeploymentCenter.tsx\",
    '''          <strong>{counts.active}</strong>''',
    '''          <strong>{deploymentCounts.active}</strong>''',
)
"""
total = """replace_once(
    \"web/src/DeploymentCenter.tsx\",
    '''          <strong>{deployments.length}</strong>''',
    '''          <strong>{deploymentTotal}</strong>''',
)
"""
if active not in text:
    raise SystemExit("Active summary replacement was not found.")
text = text.replace(active, total + active, 1)
path.write_text(text)
Path(__file__).unlink()
