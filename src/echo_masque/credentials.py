"""Ephemeral credential storage for local provider bindings."""

from threading import RLock

from pydantic import SecretStr


class CredentialStore:
    """Keep user-supplied provider keys in process memory only."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], SecretStr] = {}
        self._lock = RLock()

    def set(self, owner_id: str, card_id: str, api_key: SecretStr) -> None:
        with self._lock:
            self._values[(owner_id, card_id)] = api_key

    def get(self, owner_id: str, card_id: str) -> SecretStr | None:
        with self._lock:
            return self._values.get((owner_id, card_id))

    def has(self, owner_id: str, card_id: str) -> bool:
        with self._lock:
            return (owner_id, card_id) in self._values

    def delete(self, owner_id: str, card_id: str) -> None:
        with self._lock:
            self._values.pop((owner_id, card_id), None)
