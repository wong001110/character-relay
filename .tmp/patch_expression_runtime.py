from pathlib import Path

path = Path("src/echo_masque/connector_runtime.py")
text = path.read_text()

def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    text = text.replace(old, new, 1)

replace_once(
    '''                "Expression controls are invisible runtime behavior. First write the most "
                "natural in-character visible reply. Then decide whether a real Discord user "
                "would naturally add one expression. Using an expression is optional; use at "
                "most one.",''',
    '''                "Expression controls are invisible runtime behavior. First write the most "
                "natural in-character visible reply. Then make exactly one expression decision. "
                "Using an expression is optional, but the decision is mandatory whenever "
                "candidates are listed; use at most one expression in this reply.",''',
    "decision contract",
)
replace_once(
    '''                "Unicode Emoji may remain naturally in your visible reply text. Never invent a "
                "custom Emoji or Sticker ID. Choose only a listed resource_key and an action "
                "allowed for that candidate.",
                "Append exactly one final machine-control line after the visible reply. Balanced "''',
    '''                "Unicode Emoji may remain naturally in your visible reply text. Never invent a "
                "custom Emoji or Sticker ID. Choose only a listed resource_key and an action "
                "allowed for that candidate.",
                "If no retrieved expression naturally fits the character, tone, or moment, choose "
                "action none. A confident none decision is better than forcing an out-of-character "
                "expression. When candidates are provided, never omit the CR_EXPRESSION decision.",
                "You MUST append exactly one final machine-control line after the visible reply. "
                "Balanced "''',
    "mandatory decision reminder",
)
path.write_text(text)
