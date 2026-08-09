"""HTTP views for persisted scheduled reminders."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ReminderStatus = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
    "cancelled",
]


class ScheduledReminderView(BaseModel):
    id: str
    deployment_id: str
    character_card_id: str
    character_name: str
    platform: str
    channel_id: str
    channel_name: str
    thread_id: str
    thread_name: str
    reminder_text: str
    scheduled_at: datetime
    status: ReminderStatus
    attempt_count: int
    delivered_at: datetime | None
    last_error: str
    created_at: datetime
    updated_at: datetime


class ScheduledReminderListView(BaseModel):
    items: list[ScheduledReminderView]
