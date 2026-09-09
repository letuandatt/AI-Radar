"""Official retrieval benchmark for Qdrant vector indexing.

This benchmark is intentionally manual by default to avoid slowing down
the normal quality gate.

Run manually:
    PowerShell:
        $env:RUN_RETRIEVAL_BENCHMARK = "1"
        pytest tests/performance/test_retrieval_benchmark.py -v

Environment variables:
    QDRANT_URL              default: http://localhost:6333
    BENCH_DIMENSIONS        default: 32
    BENCH_VECTOR_COUNT      default: 1000
    BENCH_TOP_K             default: 10
    BENCH_QUERY_COUNT       default: 20
    BENCH_LATENCY_LIMIT_MS  default: 200
    BENCH_RECALL_LIMIT      default: 0.9
"""

import math
import os
import random
import time
import uuid
from collections.abc import Sequence

import pytest
from qdrant_client import QdrantClient

from app.storage.vector.base import VectorPoint
from app.storage.vector.index_config import VectorIndexConfig
from app.storage.vector.qdrant_store import QdrantVectorStore


def _qdrant_available(url: str) -> bool:
    """Check whether Qdrant is reachable."""
    try:
        client = QdrantClient(url=url, timeout=2)
        client.get_collections()
        client.close()
        return True
    except Exception:
        return False


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def _brute_force_top_k(
    query: Sequence[float],
    vectors: list[list[float]],
    top_k: int,
) -> list[str]:
    """Return IDs of top-k most similar vectors by brute force."""
    scored: list[tuple[float, str]] = []

    for idx, vector in enumerate(vectors):
        score = _cosine(query, vector)
        # Use deterministic UUID from index to match Qdrant point IDs
        scored.append((score, str(uuid.UUID(int=idx))))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc_id for _, doc_id in scored[:top_k]]


def _percentile(values: list[float], pct: float) -> float:
    """Return percentile value."""
    if not values:
        return 0.0

    ordered = sorted(values)
    index = min(len(ordered) - 1, int(math.ceil(pct / 100.0 * len(ordered))) - 1)
    return ordered[index]


@pytest.mark.performance
def test_retrieval_benchmark() -> None:
    """Benchmark Qdrant retrieval latency and recall.

    This test requires a running local Qdrant instance and is skipped
    unless RUN_RETRIEVAL_BENCHMARK=1.
    """
    if os.getenv("RUN_RETRIEVAL_BENCHMARK") != "1":
        pytest.skip("Set RUN_RETRIEVAL_BENCHMARK=1 to run the retrieval benchmark")

    url = os.getenv("QDRANT_URL", "http://localhost:6333")

    if not _qdrant_available(url):
        pytest.skip(f"Qdrant is not available at {url}")

    dimensions = int(os.getenv("BENCH_DIMENSIONS", "32"))
    vector_count = int(os.getenv("BENCH_VECTOR_COUNT", "1000"))
    top_k = int(os.getenv("BENCH_TOP_K", "10"))
    query_count = int(os.getenv("BENCH_QUERY_COUNT", "20"))
    latency_limit_ms = float(os.getenv("BENCH_LATENCY_LIMIT_MS", "200"))
    recall_limit = float(os.getenv("BENCH_RECALL_LIMIT", "0.9"))

    collection = f"benchmark_{uuid.uuid4().hex}"

    config = VectorIndexConfig(
        hnsw_m=16,
        hnsw_ef_construct=100,
        hnsw_ef=128,
    )

    store = QdrantVectorStore(
        url=url,
        collection_name=collection,
        dimensions=dimensions,
        index_config=config,
    )

    raw_client = QdrantClient(url=url, timeout=10)

    try:
        # Setup collection
        store.ensure_collection()

        # Generate deterministic random vectors
        random.seed(42)
        vectors = [
            [random.uniform(-1.0, 1.0) for _ in range(dimensions)] for _ in range(vector_count)
        ]

        points = [
            VectorPoint(
                id=str(uuid.UUID(int=i)),  # ← FIX: Valid UUID string
                vector=vectors[i],
                payload={"index": i},
            )
            for i in range(vector_count)
        ]

        # Insert in batches
        batch_size = 100
        for start in range(0, vector_count, batch_size):
            store.upsert_points(points[start : start + batch_size])

        # Encourage optimizer to run
        store.optimize_index()
        time.sleep(1.0)

        latencies: list[float] = []
        recalls: list[float] = []

        for query_index in range(min(query_count, vector_count)):
            query = vectors[query_index]

            start_time = time.perf_counter()

            response = raw_client.query_points(
                collection_name=collection,
                query=query,
                limit=top_k,
            )
            hits = response.points

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            latencies.append(elapsed_ms)

            retrieved_ids = {str(hit.id) for hit in hits}
            expected_ids = set(_brute_force_top_k(query, vectors, top_k))

            recall = len(retrieved_ids & expected_ids) / top_k
            recalls.append(recall)

        p95_latency = _percentile(latencies, 95)
        avg_recall = sum(recalls) / len(recalls)

        assert p95_latency < latency_limit_ms, (
            f"p95 latency {p95_latency:.2f}ms exceeded limit {latency_limit_ms}ms"
        )

        assert avg_recall >= recall_limit, (
            f"Average recall {avg_recall:.3f} below limit {recall_limit}"
        )

    finally:
        try:
            raw_client.delete_collection(collection_name=collection)
        except Exception:
            pass

        raw_client.close()
        store.close()
