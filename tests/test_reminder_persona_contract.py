from echo_masque.persistence import (
    ConditionWatchRepository,
    Database,
    ScheduledReminderRepository,
)
from echo_masque.server_time_tools import ServerAwareToolRegistry


def test_future_notification_tool_schemas_require_character_voice() -> None:
    database = Database("sqlite:///:memory:")
    database.initialize()
    registry = ServerAwareToolRegistry(
        reminder_repository=ScheduledReminderRepository(database),
        condition_watch_repository=ConditionWatchRepository(database),
        condition_watch_enabled=True,
    )
    definitions = {
        item.function.name: item
        for item in registry.provider_tools(("scheduler.remind", "watch.condition"))
    }

    reminder = definitions["scheduler_remind"].function
    reminder_properties = reminder.parameters["properties"]
    reminder_text = reminder_properties["reminder_text"]
    assert "exact future message" in reminder_text["description"]
    assert "persona and voice" in reminder_text["description"]
    assert "without another model call" in reminder.description

    watch = definitions["watch_condition"].function
    watch_properties = watch.parameters["properties"]
    notification_text = watch_properties["notification_text"]
    assert "exact future message" in notification_text["description"]
    assert "persona and voice" in notification_text["description"]
    assert "stored text deterministically" in watch.description
