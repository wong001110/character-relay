"""Account-owned provider Key Group persistence models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class ProviderKeyGroupRecord(Base):
    """Reusable encrypted-provider configuration owned by one account."""

    __tablename__ = "provider_key_groups"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_provider_key_groups_owner_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    default_models_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CharacterKeyGroupAssignmentRecord(Base):
    """Bind one Character Card capability to one account-owned Key Group."""

    __tablename__ = "character_key_group_assignments"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "character_card_id",
            "capability",
            name="uq_character_key_group_assignment",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    character_card_id: Mapped[str] = mapped_column(
        ForeignKey("character_cards.id"), index=True, nullable=False
    )
    capability: Mapped[str] = mapped_column(String(40), nullable=False)
    key_group_id: Mapped[str] = mapped_column(
        ForeignKey("provider_key_groups.id"), index=True, nullable=False
    )
    model_override: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
