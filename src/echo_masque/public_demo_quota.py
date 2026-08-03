"""Cost controls for the shared public Demo account."""

from echo_masque.public_demo import PUBLIC_DEMO_USER_ID
from echo_masque.security_controls import QuotaService


class PublicDemoQuotaService(QuotaService):
    """Apply normal quotas plus a persistent daily Demo Run budget."""

    def enforce_run_start(self, owner_id: str) -> None:
        super().enforce_run_start(owner_id)
        if not self.settings.public_demo_enabled or owner_id != PUBLIC_DEMO_USER_ID:
            return
        self._consume(
            key=f"public-demo-run:{owner_id}",
            limit=self.settings.public_demo_max_runs_per_day,
            window_seconds=24 * 60 * 60,
            message="The shared Demo account has reached its daily Run quota.",
        )


__all__ = ["PublicDemoQuotaService"]
