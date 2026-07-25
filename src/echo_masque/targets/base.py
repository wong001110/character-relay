"""Target adapter protocol."""

from typing import Protocol

from echo_masque.domain import TargetResponse, TargetSummary


class TargetAdapter(Protocol):
    @property
    def summary(self) -> TargetSummary: ...

    async def reset(self) -> None: ...

    async def send(self, message: str) -> TargetResponse: ...
