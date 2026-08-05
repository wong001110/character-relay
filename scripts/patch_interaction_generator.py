from pathlib import Path

path = Path("scripts/apply_interaction_sessions_and_stickers.py")
text = path.read_text(encoding="utf-8")
start_marker = '''replace(
    runtime_path,
    "                    f\\"{payload.author_display_name} | {payload.author_id}]: {payload.text}\\"\\n",
'''
start = text.index(start_marker)
end = text.index("\n\n# TypeScript connector types.", start)
replacement = '''replace(
    runtime_path,
    '        return "\\\\n".join(\\n',
    '        latest_message = DiscordContextMessage(\\n'
    '            message_id=payload.message_id,\\n'
    '            author_id=payload.author_id,\\n'
    '            author_display_name=payload.author_display_name,\\n'
    '            text=payload.text,\\n'
    '            stickers=payload.stickers,\\n'
    '            is_bot=payload.author_is_bot,\\n'
    '        )\\n'
    '        latest_content = DiscordConnectorRuntime._context_message_content(\\n'
    '            latest_message\\n'
    '        )\\n'
    '        return "\\\\n".join(\\n',
)
replace(
    runtime_path,
    "                    f\\"{payload.author_display_name} | {payload.author_id}]: {payload.text}\\"\\n",
    "                    f\\"{payload.author_display_name} | {payload.author_id}]: {latest_content}\\"\\n",
)
'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
