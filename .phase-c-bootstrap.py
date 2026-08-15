from pathlib import Path

path = Path(".phase-c-transform.py")
source = path.read_text(encoding="utf-8")
source = source.replace(
    'function log(\\n""",\n    """function visibleImageAttachmentCount',
    'function log(message: string, metadata?: Record<string, unknown>): void {\\n""",\n    """function visibleImageAttachmentCount',
)
# The replacement above changes only the old match anchor; restore the new-text boundary so the
# inserted helper block still ends immediately before the existing log function declaration.
source = source.replace(
    'function log(message: string, metadata?: Record<string, unknown>): void {\\n""",\n)\nreplace_once(\n    "connectors/discord/src/index.ts",\n    """    let serverShadowCandidateScores:',
    'function log(message: string, metadata?: Record<string, unknown>): void {\\n""",\n)\nreplace_once(\n    "connectors/discord/src/index.ts",\n    """    let serverShadowCandidateScores:',
)
exec(compile(source, str(path), "exec"))
