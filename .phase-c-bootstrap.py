from pathlib import Path

path = Path(".phase-c-transform.py")
source = path.read_text(encoding="utf-8")
source = source.replace(
    'function log(\\n"""',
    'function log(message: string, metadata?: Record<string, unknown>): void {\\n"""',
)
exec(compile(source, str(path), "exec"))
