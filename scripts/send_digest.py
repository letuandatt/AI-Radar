"""Batch entrypoint: render and deliver the Daily Intelligence digest (D1/E1).

Runs ONE digest cycle then exits: query candidates -> rank -> synthesize
(markdown via the shared LLM chain) -> deliver through a NotificationChannel
(LogChannel now, ZaloChannel in S30).

Governed by ``digest_enabled`` (default False): the scheduled job stays a
safe no-op until explicitly enabled. A failed delivery exits non-zero —
insights remain in the repository, a re-run retries delivery only.

Usage:
    python scripts/send_digest.py            # real run (gated by DIGEST_ENABLED)
    python scripts/send_digest.py --dry-run  # bootstrap check only
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    """Entry point for the daily digest batch job."""
    parser = argparse.ArgumentParser(description="Send the daily intelligence digest.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be bootstrapped and exit (no network, no LLM).",
    )
    args = parser.parse_args(argv)

    from app.config.settings import get_settings
    from app.core.logger import get_logger

    settings = get_settings()
    logger = get_logger("scripts.send_digest")

    if args.dry_run:
        # E1 check: the digest batch runtime bootstraps ONLY the repository
        # and the LLM chain — digest reads knowledge, it must never schedule
        # acquisition.
        print("DRY RUN — digest batch runtime would initialize:")
        for component in [
            "repository      (SQLite + Qdrant + BM25 — read path for candidates)",
            "llm_chain       (shared chain — digest synthesis)",
            "digest pipeline (D1: query -> rank -> synthesize -> channel)",
        ]:
            print(f"  - {component}")
        print("Key settings:")
        print(f"  - sqlite_path:      {settings.sqlite_path}")
        print(f"  - qdrant_url:       {settings.qdrant_url}")
        print(f"  - digest_enabled:   {settings.digest_enabled}")
        print(f"  - digest_max_items: {settings.digest_max_items}")
        print("DRY RUN OK — nothing was executed.")
        return 0

    # --- Real run ---
    if not settings.digest_enabled:
        logger.warning(
            "digest_enabled=false — the digest job is registered but runs as a "
            "no-op. Enable it via DIGEST_ENABLED=true in the environment."
        )
        return 0

    from app.core.run_metrics import RunMetrics
    from app.pipelines.daily_digest import DailyDigestPipeline, LogChannel
    from app.services.repository.bootstrap import (
        create_llm_chain,
        initialize_knowledge_repository,
    )

    logger.info("Bootstrapping digest runtime (repository + shared llm_chain)")
    initializer = initialize_knowledge_repository(settings)
    llm_chain = create_llm_chain(settings)

    # P1.9: one metrics line per run
    run = RunMetrics.start("digest")
    cost_before = llm_chain.cost_tracker.snapshot() if llm_chain.cost_tracker else None

    pipeline = DailyDigestPipeline(
        sqlite_store=initializer.sqlite_store,
        llm_provider=llm_chain,
        channel=LogChannel(),
        max_items=settings.digest_max_items,
    )
    result = pipeline.run()

    run.set(
        digest_target_date=result.target_date.isoformat(),
        digest_items=len(result.items),
        digest_sent=result.sent,
        digest_channel=result.channel,
    )
    if llm_chain.cost_tracker and cost_before is not None:
        cost_after = llm_chain.cost_tracker.snapshot()
        run.set(
            llm_calls=cost_after["requests_today"] - cost_before["requests_today"],
            llm_tokens=cost_after["tokens_today"] - cost_before["tokens_today"],
            llm_cost_usd=round(cost_after["current_cost"] - cost_before["current_cost"], 6),
        )

    initializer.shutdown()
    run.finish()
    run.save_jsonl(settings.run_metrics_path)

    if result.sent:
        logger.info(
            "Digest %s delivered via %s (%d items)",
            result.target_date.isoformat(),
            result.channel,
            len(result.items),
        )
        return 0

    logger.error(
        "Digest delivery FAILED: %s — insights are safe in the repository; "
        "re-run this script to retry delivery only",
        result.error,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
