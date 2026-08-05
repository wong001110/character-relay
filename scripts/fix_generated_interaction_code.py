from pathlib import Path

runtime = Path("src/echo_masque/connector_runtime.py")
runtime_text = runtime.read_text(encoding="utf-8")
runtime_text = runtime_text.replace(
    '''            interaction_guidance = (
                "This reply is part of a Portal-configured Roast Interaction Session.",
                f"The target member is {payload.interaction_target_display_name or payload.author_display_name} "
                f"with stable Discord user ID {payload.interaction_target_user_id or payload.author_id}.",
''',
    '''            target_name = (
                payload.interaction_target_display_name or payload.author_display_name
            )
            target_user_id = payload.interaction_target_user_id or payload.author_id
            interaction_guidance = (
                "This reply is part of a Portal-configured Roast Interaction Session.",
                f"The target member is {target_name} with stable Discord user ID "
                f"{target_user_id}.",
''',
)
runtime.write_text(runtime_text, encoding="utf-8")

repository = Path("src/echo_masque/persistence/interaction_repository.py")
repository_text = repository.read_text(encoding="utf-8")
repository_text = repository_text.replace(
    '''def _metadata_semantics(name: str, description: str, tags: list[str]) -> tuple[str, str, str, float]:
''',
    '''def _metadata_semantics(
    name: str,
    description: str,
    tags: list[str],
) -> tuple[str, str, str, float]:
''',
)
repository_text = repository_text.replace(
    '''                        "Every Interaction Session participant must be an active Discord deployment."
''',
    '''                        "Every Interaction Session participant must be an active "
                        "Discord deployment."
''',
)
repository.write_text(repository_text, encoding="utf-8")
