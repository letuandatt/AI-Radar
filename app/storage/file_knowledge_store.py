"""File-based KnowledgeStore implementation using JSON persistence.

This implementation stores KnowledgeObjects in a local JSON file,
suitable for development, testing, and small-scale deployments.
For production workloads, swap to a database-backed implementation
via the KnowledgeStore protocol without changing pipeline code.
"""

import json
from pathlib import Path

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject

logger = get_logger(__name__)


class FileKnowledgeStore:
    """JSON file-backed KnowledgeStore with idempotent save semantics.

    Each KnowledgeObject is serialized as a JSON document and stored
    in a single file. Idempotency is enforced by checking external_id
    and content_hash before insertion.

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

    def save_objects(self, objects: list[KnowledgeObject]) -> int:
        """Persist KnowledgeObjects with idempotent semantics.

        For each object, checks whether an existing record matches by
        (external_id, source_type) or content_hash. If matched, the
        record is updated; otherwise a new record is created.

        Args:
            objects: List of validated KnowledgeObjects to persist.

        Returns:
            Number of newly created objects (excluding updates).
        """
        created_count = 0

        for obj in objects:
            existing = self._find_existing(obj)
            if existing is not None:
                # Update: replace the existing record with the new one
                self._objects[existing.id] = obj
                logger.debug(
                    "Updated KnowledgeObject %s (external_id=%s)",
                    existing.id,
                    obj.external_id,
                )
            else:
                # Create: insert as new record
                self._objects[obj.id] = obj
                created_count += 1
                logger.debug(
                    "Created KnowledgeObject %s (external_id=%s)",
                    obj.id,
                    obj.external_id,
                )

        self._persist()

        logger.info(
            "Saved %d objects: %d created, %d updated",
            len(objects),
            created_count,
            len(objects) - created_count,
        )

        return created_count

    def get_by_external_id(self, external_id: str, source_type: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by its external identity.

        Args:
            external_id: The external identifier from the source.
            source_type: The source type to disambiguate.

        Returns:
            The matching KnowledgeObject, or None if not found.
        """
        for obj in self._objects.values():
            if obj.external_id == external_id and obj.source_type == source_type:
                return obj
        return None

    def get_by_content_hash(self, content_hash: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by its content hash.

        Args:
            content_hash: SHA-256 hash of the content text.

        Returns:
            The matching KnowledgeObject, or None if not found.
        """
        for obj in self._objects.values():
            if obj.content_hash == content_hash:
                return obj
        return None

    def get_all(self) -> list[KnowledgeObject]:
        """Retrieve all stored KnowledgeObjects.

        Returns:
            List of all KnowledgeObjects in the store.
        """
        return list(self._objects.values())

    def count(self) -> int:
        """Return the total number of stored KnowledgeObjects.

        Returns:
            Total object count.
        """
        return len(self._objects)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_existing(self, obj: KnowledgeObject) -> KnowledgeObject | None:
        """Check if an object already exists by external_id or content_hash.

        Priority:
        1. Match by (external_id, source_type)
        2. Match by content_hash

        Args:
            obj: The object to check for existence.

        Returns:
            The existing matching object, or None.
        """
        # Check by external identity
        by_external = self.get_by_external_id(obj.external_id, obj.source_type)
        if by_external is not None:
            return by_external

        # Check by content hash
        by_hash = self.get_by_content_hash(obj.content_hash)
        if by_hash is not None:
            return by_hash

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
