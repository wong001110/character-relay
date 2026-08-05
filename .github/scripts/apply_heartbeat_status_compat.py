from pathlib import Path

path = Path("src/echo_masque/persistence/deployment_repository.py")
text = path.read_text(encoding="utf-8")
old = '''        last_error: str,
        replica_region: str,
        gateway_ready: bool,
        state_synchronized: bool,
        visible_server_count: int,
    ) -> bool:
'''
new = '''        last_error: str,
        replica_region: str = "",
        gateway_ready: bool = False,
        state_synchronized: bool = False,
        visible_server_count: int = 0,
    ) -> bool:
'''
if old not in text:
    raise RuntimeError("heartbeat_connection signature anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
