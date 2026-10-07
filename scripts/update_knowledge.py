"""Batch entrypoint: acquisition -> processing -> analysis (D2/E1).

Runs ONE knowledge-update cycle then exits. This is the batch runtime:
it bootstraps ONLY the dependencies the batch needs (repository, shared
LLM chain, processing + acquisition pipelines, analysis) — never the web
stack (retrieval service) and never the scheduler loop.

Usage:
    python scripts/update_knowledge.py            # real run
    python scripts/update_knowledge.py --dry-run  # bootstrap check only
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    """Entry point for the knowledge update batch job."""
    parser = argparse.ArgumentParser(description="Run one knowledge-update cycle.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be bootstrapped and exit (no network, no LLM).",
    )
    args = parser.parse_args(argv)

    from app.config.settings import get_settings
    from app.core.logger import get_logger

    settings = get_settings()
    logger = get_logger("scripts.update_knowledge")

    if args.dry_run:
        # E1 check: log exactly what the batch runtime WOULD bootstrap,
        # without touching the network (safe in CI).
        print("DRY RUN — batch runtime would initialize:")
        for component in [
            "repository      (SQLite + Qdrant + BM25 — fail fast)",
            "llm_chain       (shared: analysis + extraction, one budget)",
            "processing      (gate + bounded-chunk extraction)",
            "acquisition     (RSS + GitHub + HuggingFace)",
            "analysis        (ContentAnalyzer, semaphore-limited)",
        ]:
            print(f"  - {component}")
        print("Key settings:")
        print(f"  - sqlite_path:          {settings.sqlite_path}")
        print(f"  - bm25_index_path:      {settings.bm25_index_path}")
        print(f"  - qdrant_url:           {settings.qdrant_url}")
        print(f"  - embedding_provider:   {settings.embedding_provider}")
        print(f"  - llm_primary_provider: {settings.llm_primary_provider}")
        print(f"  - llm_fallback:         {settings.llm_fallback_providers}")
        print(f"  - llm_batch_size:       {settings.llm_batch_size}")
        print(f"  - gate_enabled:         {settings.gate_enabled}")
        print("DRY RUN OK — nothing was executed.")
        return 0

    # --- Real run: batch dependencies only (E1) ---
    from app.fetchers.registry import (
        get_github_registry,
        get_hf_registry,
        get_source_registry,
        initialize_github_registry,
        initialize_hf_registry,
        initialize_source_registry,
    )
    from app.pipelines.acquisition import DefaultAcquisitionPipeline
    from app.pipelines.knowledge_update import build_processing_pipeline, run_knowledge_update
    from app.services.repository.bootstrap import (
        create_analysis_service,
        create_llm_chain,
        initialize_knowledge_repository,
    )

    logger.info("Bootstrapping batch runtime (repository, llm_chain, pipelines)")
    initializer = initialize_knowledge_repository(settings)
    llm_chain = create_llm_chain(settings)
    processing = build_processing_pipeline(initializer, settings, llm_chain)

    initialize_source_registry(settings)
    initialize_github_registry(settings)
    initialize_hf_registry(settings)
    acquisition = DefaultAcquisitionPipeline(
        rss_registry=get_source_registry(),
        github_registry=get_github_registry(),
        hf_registry=get_hf_registry(),
        settings=settings,
    )

    acquisition_result = acquisition.run()
    logger.info(
        "Acquisition finished: %d sources (%d ok, %d failed), %d articles",
        acquisition_result.total_sources,
        acquisition_result.successful_sources,
        acquisition_result.failed_sources,
        acquisition_result.total_articles,
    )

    processing_result = run_knowledge_update(acquisition_result, processing)
    if processing_result is not None:
        logger.info(
            "Processing finished: created=%d updated=%d failed=%d filtered=%d",
            processing_result.objects_created,
            processing_result.objects_updated,
            processing_result.failed_objects,
            processing_result.filtered_objects,
        )

    analysis_service = create_analysis_service(initializer, llm_chain)
    analysis_results = asyncio.run(analysis_service.analyze_batch())
    logger.info("Analysis finished: %d items analyzed", len(analysis_results))

    initializer.shutdown()
    logger.info("Knowledge update cycle complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
