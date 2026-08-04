from pathlib import Path

path = Path("src/echo_masque/api/routes/matrices.py")
text = path.read_text()
old_import = "from typing import cast\n"
new_import = "from typing import Annotated, cast\n"
if old_import not in text:
    raise SystemExit("Matrix route typing import was not found.")
text = text.replace(old_import, new_import, 1)
old_parameter = '''    task_status: MatrixTaskStatus | None = Query(default=None, alias="status"),
'''
new_parameter = '''    task_status: Annotated[
        MatrixTaskStatus | None,
        Query(alias="status"),
    ] = None,
'''
if old_parameter not in text:
    raise SystemExit("Matrix task status parameter was not found.")
text = text.replace(old_parameter, new_parameter, 1)
path.write_text(text)
Path(__file__).unlink()
