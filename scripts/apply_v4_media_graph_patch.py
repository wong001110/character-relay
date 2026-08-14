from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src/echo_masque/conversation_media.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from echo_masque.config import get_settings\n",
        "from echo_masque.config import get_settings\n"
        "from echo_masque.conversation_media_graph import ConversationMediaGraphService\n",
        "media graph import",
    )
    text = replace_once(
        text,
        "from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord\n"
        "from echo_masque.persistence.conversation_media_repository import (\n"
        "    ConversationMediaReferenceRepository,\n"
        ")\n",
        "from echo_masque.persistence.conversation_graph_repository import ConversationGraphRepository\n"
        "from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord\n"
        "from echo_masque.persistence.conversation_media_repository import (\n"
        "    ConversationMediaReferenceRepository,\n"
        ")\n"
        "from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository\n",
        "graph repositories",
    )
    text = replace_once(
        text,
        "        self._semantic_vectors = SemanticVectorRepository(repository.database)\n",
        "        self._semantic_vectors = SemanticVectorRepository(repository.database)\n"
        "        self._media_graph = ConversationMediaGraphService(\n"
        "            ConversationGraphRepository(repository.database),\n"
        "            ConversationTopicRepository(repository.database),\n"
        "        )\n",
        "media graph service",
    )
    text = replace_once(
        text,
        "            if self._semantic_enabled:\n"
        "                with suppress(SemanticEmbeddingUnavailable, ValueError, RuntimeError):\n"
        "                    self._ensure_vector(owner_id=owner_id, record=record, context=context)\n",
        "            with suppress(Exception):\n"
        "                self._media_graph.project_perceived(\n"
        "                    record=record,\n"
        "                    context=context,\n"
        "                    connection_id=payload.connection_id,\n"
        "                )\n"
        "            if self._semantic_enabled:\n"
        "                with suppress(SemanticEmbeddingUnavailable, ValueError, RuntimeError):\n"
        "                    self._ensure_vector(owner_id=owner_id, record=record, context=context)\n",
        "project perceived media",
    )
    text = replace_once(
        text,
        "        if not recent:\n"
        "            return []\n"
        "        try:\n"
        "            encoder = self._encoder()\n",
        "        if not recent:\n"
        "            return []\n"
        "        with suppress(Exception):\n"
        "            linked_keys = self._media_graph.active_topic_media_keys(\n"
        "                owner_id=recent[0].owner_id,\n"
        "                connection_id=payload.connection_id,\n"
        "                guild_id=payload.guild_id,\n"
        "                channel_id=payload.channel_id,\n"
        "                thread_id=payload.thread_id,\n"
        "            )\n"
        "            if linked_keys:\n"
        "                narrowed = [\n"
        "                    record\n"
        "                    for record in recent\n"
        "                    if self._media_graph.media_key(record.source_key) in linked_keys\n"
        "                ]\n"
        "                if narrowed:\n"
        "                    recent = narrowed\n"
        "        try:\n"
        "            encoder = self._encoder()\n",
        "graph candidate narrowing",
    )
    TARGET.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
