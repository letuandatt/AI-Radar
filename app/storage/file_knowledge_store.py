"""File-based KnowledgeStore implementation using JSON persistence.

This implementation stores KnowledgeObjects in a local JSON file,
suitable for development, testing, and small-scale deployments.
For production workloads, swap to SQLiteKnowledgeStore via the
KnowledgeStore protocol without changing pipeline code.
"""

import json
from pathlib import Path

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.storage.knowledge.knowledge_store import SaveResult

logger = get_logger(__name__)


class FileKnowledgeStore:
    """JSON file-backed KnowledgeStore with idempotent save semantics.

    Each KnowledgeObject is serialized as a JSON document and stored
    in a single file. Idempotency is enforced by checking identity
    (source_type, source_name, external_id) and content_hash.

    Attributes:
        file_path: Path to the JSON storage file.
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize the file-based knowledge store.

        Args:
            file_path: Path to the JSON file for persistence.
        """
        self._file_path = Path(file_path)
        self._objects: dict[str, KnowledgeObject] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_objects(self, objects: list[KnowledgeObject]) -> SaveResult:
        """Persist KnowledgeObjects with idempotent semantics (DATA-001).

        For each object:
        - Lookup by (source_type, source_name, external_id)
        - Not found → INSERT (created)
        - Found + content_hash differs → UPDATE (updated)
        - Found + content_hash same → SKIP (skipped)

        Args:
            objects: List of validated KnowledgeObjects to persist.

        Returns:
            SaveResult with created, updated, and skipped counts.
        """
        created = 0
        updated = 0
        skipped = 0

        for obj in objects:
            existing = self._find_by_identity(obj.source_type, obj.source_name, obj.external_id)
            if existing is None:
                # INSERT
                self._objects[obj.id] = obj
                created += 1
                logger.debug(
                    "Created KnowledgeObject %s (external_id=%s)",
                    obj.id,
                    obj.external_id,
                )
            elif existing.content_hash != obj.content_hash:
                # UPDATE — content changed
                self._objects[existing.id] = obj
                updated += 1
                logger.debug(
                    "Updated KnowledgeObject %s (external_id=%s)",
                    existing.id,
                    obj.external_id,
                )
            else:
                # SKIP — content unchanged
                skipped += 1
                logger.debug(
                    "Skipped KnowledgeObject %s (content unchanged)",
                    obj.id,
                )

        self._persist()
        logger.info(
            "Saved %d objects: %d created, %d updated, %d skipped",
            len(objects),
            created,
            updated,
            skipped,
        )
        return SaveResult(created=created, updated=updated, skipped=skipped)

    def get_by_external_id(self, external_id: str, source_type: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by its external identity."""
        for obj in self._objects.values():
            if obj.external_id == external_id and obj.source_type == source_type:
                return obj
        return None

    def get_by_content_hash(self, content_hash: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by its content hash."""
        for obj in self._objects.values():
            if obj.content_hash == content_hash:
                return obj
        return None

    def get_all(self) -> list[KnowledgeObject]:
        """Retrieve all stored KnowledgeObjects."""
        return list(self._objects.values())

    def count(self) -> int:
        """Return the total number of stored KnowledgeObjects."""
        return len(self._objects)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_by_identity(
        self, source_type: str, source_name: str, external_id: str
    ) -> KnowledgeObject | None:
        """Find existing object by identity triple."""
        for obj in self._objects.values():
            if (
                obj.source_type == source_type
                and obj.source_name == source_name
                and obj.external_id == external_id
            ):
                return obj
        return None

    def _load(self) -> None:
        """Load objects from the JSON file into memory."""
        if not self._file_path.exists():
            logger.debug(
                "Storage file %s not found, starting with empty store",
                self._file_path,
            )
            return
        try:
            raw_data = self._file_path.read_text(encoding="utf-8")
            if not raw_data.strip():
                return
            records = json.loads(raw_data)
            for record in records:
                obj = KnowledgeObject.model_validate(record)
                self._objects[obj.id] = obj
            logger.info(
                "Loaded %d KnowledgeObjects from %s",
                len(self._objects),
                self._file_path,
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to load storage file %s: %s", self._file_path, e)

    def _persist(self) -> None:
        """Write all in-memory objects to the JSON file."""
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        records = [obj.model_dump(mode="json") for obj in self._objects.values()]
        content = json.dumps(records, indent=2, ensure_ascii=False)
        self._file_path.write_text(content, encoding="utf-8")
        logger.debug(
            "Persisted %d KnowledgeObjects to %s",
            len(records),
            self._file_path,
        )
