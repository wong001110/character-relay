from pathlib import Path

path = Path("src/echo_masque/persistence/matrix_repository.py")
text = path.read_text()
text = text.replace(
    "            if score_delta is not None and score_delta >= 3 and candidate.pass_rate >= baseline.pass_rate:\n",
    "            if (\n"
    "                score_delta is not None\n"
    "                and score_delta >= 3\n"
    "                and candidate.pass_rate >= baseline.pass_rate\n"
    "            ):\n",
)
text = text.replace(
    '                raise ValueError(f"Matrix cannot transition from {record.status} to {status.value}.")\n',
    "                raise ValueError(\n"
    '                    f"Matrix cannot transition from {record.status} "\n'
    '                    f"to {status.value}."\n'
    "                )\n",
)
path.write_text(text)
Path("scripts/phase14_linefix.py").unlink()
Path(".github/workflows/phase14-linefix.yml").unlink()
