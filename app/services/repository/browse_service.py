"""Repository gateway for the web's page-based contract."""

import json

from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.browse_models import BrowseItem, BrowsePage, BrowseQuery
from app.services.repository.query_models import PageInfo
from app.storage.knowledge.browse_store import SQLiteBrowseStore


class BrowseService:
    """Keep HTTP routes outside storage and preserve existing cursor consumers."""

    def __init__(self, access: RepositoryAccessService, store: SQLiteBrowseStore) -> None:
        self.access = access
        self._store = store

    def search(self, query: BrowseQuery) -> BrowsePage:
        """Read an exact filtered total and summaries, without loading full contents."""
        rows, total = self._store.page(**query.model_dump(mode="json"))
        items = []

        for row in rows:
            metadata = json.loads(row.pop("metadata_json"))
            items.append(
                BrowseItem(
                    **row, topics=metadata["topics"], relevance_score=metadata["relevance_score"]
                )
            )

        return BrowsePage(
            items=items,
            total=total,
            page_info=PageInfo(
                total=total,
                has_prev=query.offset > 0,
                has_next=query.offset + len(items) < total,
            ),
        )

    def matching_ids(self, query: BrowseQuery) -> frozenset[str]:
        """Resolve eligible search IDs through the repository gateway."""
        return self._store.matching_ids(
            **query.model_dump(
                mode="json",
                include={
                    "source_types",
                    "source_names",
                    "topics",
                    "published_after",
                    "published_before",
                },
            )
        )
