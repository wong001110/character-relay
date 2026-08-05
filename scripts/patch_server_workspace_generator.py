from pathlib import Path

path = Path("scripts/apply_server_workspace_backend.py")
text = path.read_text(encoding="utf-8")
old = '''def seed_server(client: TestClient) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
'''
new = '''def seed_server(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
'''
if old not in text:
    raise RuntimeError("seed_server signature not found")
text = text.replace(old, new, 1)

old = '''            values = {
                "connection_id": profile.connection_id,
                "guild_id": profile.guild_id,
                "guild_name": profile.guild_name,
                "channel_id": channel_id,
                "channel_name": str(channel.get("name") or channel_id),
                "category_id": category_id,
                "participant_deployment_ids": participant_ids,
                "rounds_per_trigger": template.rounds_per_trigger,
                "maximum_triggers": template.maximum_triggers,
                "cooldown_seconds": template.cooldown_seconds,
                "duration_seconds": template.duration_seconds,
                "intensity": template.intensity,
            }
        return self.create_session(
            owner_id=owner_id,
            target_user_id=target_user_id,
            target_display_name=target_display_name,
            status=status,
            **values,
        )
'''
new = '''            connection_id = profile.connection_id
            guild_id = profile.guild_id
            guild_name = profile.guild_name
            channel_name = str(channel.get("name") or channel_id)
            rounds_per_trigger = template.rounds_per_trigger
            maximum_triggers = template.maximum_triggers
            cooldown_seconds = template.cooldown_seconds
            duration_seconds = template.duration_seconds
            intensity = template.intensity
        return self.create_session(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            guild_name=guild_name,
            channel_id=channel_id,
            channel_name=channel_name,
            category_id=category_id,
            target_user_id=target_user_id,
            target_display_name=target_display_name,
            participant_deployment_ids=participant_ids,
            rounds_per_trigger=rounds_per_trigger,
            maximum_triggers=maximum_triggers,
            cooldown_seconds=cooldown_seconds,
            duration_seconds=duration_seconds,
            intensity=intensity,
            status=status,
        )
'''
if old not in text:
    raise RuntimeError("template application block not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
