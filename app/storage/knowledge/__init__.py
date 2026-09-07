"""Knowledge storage package.

Exports the KnowledgeStore protocol, SaveResult, and implementations.
"""

from app.storage.knowledge.knowledge_store import KnowledgeStore, SaveResult
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

__all__ = [
    "KnowledgeStore",
    "SaveResult",
    "SQLiteKnowledgeStore",
]
