"""Batch entrypoint: render and send the Daily Intelligence digest (D2/E1).

Runs ONE digest cycle then exits. The digest pipeline itself (D1, Phase 5)
is not implemented yet — this entrypoint exists now so the schedule,
bootstrap boundary and monitoring are in place; the real run is a safe
no-op until D1 lands (no-op wire, never a 0-caller).

Usage:
    python scripts/send_digest.py            # real run (no-op until D1)
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
        # E1 check: the digest batch runtime bootstraps ONLY the repository —
        # digest reads knowledge; it must never schedule acquisition and the
        # LLM chain is initialized only when D1 actually needs it.
        print("DRY RUN — digest batch runtime would initialize:")
        for component in [
            "repository      (SQLite + Qdrant + BM25 — read path for candidates)",
            "digest pipeline (D1: query -> rank -> synthesize -> Zalo) — PENDING",
        ]:
            print(f"  - {component}")
        print("Key settings:")
        print(f"  - sqlite_path:    {settings.sqlite_path}")
        print(f"  - qdrant_url:     {settings.qdrant_url}")
        print("DRY RUN OK — nothing was executed.")
        return 0

    # --- Real run ---
    from app.services.repository.bootstrap import initialize_knowledge_repository

    logger.info("Bootstrapping digest runtime (repository only)")
    initializer = initialize_knowledge_repository(settings)

    # D1 (Phase 5): query candidates -> rank -> synthesize -> Zalo OA.
    # Until then this is a deliberate, monitored no-op.
    logger.warning(
        "Digest pipeline not implemented yet (D1, Phase 5) — no-op run, no digest was sent"
    )

    initializer.shutdown()
    logger.info("Digest cycle complete (no-op)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
