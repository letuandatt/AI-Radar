"""Qdrant Vector Store Configuration.

Contains all Qdrant-specific parameters.
To adjust Qdrant settings, modify this file only.
"""

from app.core.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# QDRANT CONNECTION PARAMETERS — Edit here to adjust behavior
# ============================================================================

QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION_NAME = "knowledge_objects"
QDRANT_DISTANCE_METRIC = "Cosine"  # Best for text embeddings
QDRANT_BATCH_SIZE = 100  # Default batch size for upsert operations

# ============================================================================
# RELIABILITY PARAMETERS
# ============================================================================

QDRANT_TIMEOUT = 30  # Seconds per operation
QDRANT_MAX_RETRIES = 3  # Max retries for transient errors
QDRANT_RETRY_BASE_DELAY = 0.5  # Initial delay in seconds
QDRANT_RETRY_MAX_DELAY = 10.0  # Max delay cap in seconds

# Circuit breaker settings
QDRANT_CIRCUIT_FAILURE_THRESHOLD = 5  # Consecutive failures before opening
QDRANT_CIRCUIT_RECOVERY_TIMEOUT = 30.0  # Seconds to wait before half-open


def get_qdrant_config() -> dict:
    """Get Qdrant configuration as a dictionary.

    Returns:
        Dictionary with Qdrant configuration parameters.
    """
    return {
        "url": QDRANT_URL,
        "collection_name": QDRANT_COLLECTION_NAME,
        "distance_metric": QDRANT_DISTANCE_METRIC,
        "batch_size": QDRANT_BATCH_SIZE,
        "timeout": QDRANT_TIMEOUT,
        "max_retries": QDRANT_MAX_RETRIES,
        "retry_base_delay": QDRANT_RETRY_BASE_DELAY,
        "retry_max_delay": QDRANT_RETRY_MAX_DELAY,
        "circuit_failure_threshold": QDRANT_CIRCUIT_FAILURE_THRESHOLD,
        "circuit_recovery_timeout": QDRANT_CIRCUIT_RECOVERY_TIMEOUT,
    }
