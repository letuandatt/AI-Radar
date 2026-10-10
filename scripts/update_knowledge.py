"""One batch cycle: acquisition -> processing -> content -> groups -> patterns.

Use --analysis-only for existing SQLite data, or --input-json for cached raw
articles. All modes share bootstrap, provider budget and analysis orchestration.
The scheduler and web/retrieval service are not started by this entrypoint.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def positive_int(value: str) -> int:
    """Reject unbounded or negative batch/window arguments before bootstrap."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv: list[str] | None = None) -> int:
    """Run once; return 0 for success, 1 for failed/partial runs, 2 for bad CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--analysis-only", action="store_true", help="Skip fetching and processing.")
    mode.add_argument("--input-json", type=Path, help="Read a JSON list of RawArticle objects.")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without bootstrap.")
    parser.add_argument("--limit", type=positive_int, default=50, help="Max new content analyses.")
    parser.add_argument(
        "--max-articles", type=positive_int, help="Max deduplicated inputs to process."
    )
    parser.add_argument("--group-days", type=positive_int, default=7)
    parser.add_argument("--pattern-days", type=positive_int, default=30)
    parser.add_argument(
        "--skip-content", action="store_true", help="Aggregate existing analyses only."
    )
    parser.add_argument(
        "--report", type=Path, help="Write run status and analysis results as JSON."
    )
    args = parser.parse_args(argv)

    if args.pattern_days < 7:
        parser.error("--pattern-days must be >= 7")
    if args.skip_content and not args.analysis_only:
        parser.error("--skip-content requires --analysis-only")
    if args.max_articles and args.analysis_only:
        parser.error("--max-articles does not apply to --analysis-only")

    from app.config.settings import get_settings
    from app.core.logger import get_logger

    settings = get_settings()
    logger = get_logger("scripts.update_knowledge")

    if args.dry_run:
        print("DRY RUN — repository (SQLite + Qdrant + BM25), shared llm_chain")
        input_label = "existing SQLite" if args.analysis_only else args.input_json or "live sources"
        print(f"Input: {input_label}")
        print(f"SQLite: {settings.sqlite_path}; provider: {settings.llm_primary_provider}")
        print(f"Content limit: {args.limit}; skip content: {args.skip_content}")
        print(f"Group window: {args.group_days}d; pattern window: {args.pattern_days}d")
        print("Group/pattern input uses the whole window; --limit does not cap description calls.")
        print("DRY RUN OK — no network, LLM calls, input reads or storage writes.")
        return 0

    from pydantic import TypeAdapter

    from app.core.run_metrics import RunMetrics
    from app.models.article import RawArticle
    from app.models.result import AcquisitionResult
    from app.pipelines.analysis import run_analysis
    from app.pipelines.knowledge_update import (
        build_processing_pipeline,
        deduplicate_articles,
        run_knowledge_update,
    )
    from app.services.repository.bootstrap import (
        create_analysis_service,
        create_llm_chain,
        initialize_knowledge_repository,
    )

    run = RunMetrics.start("analysis" if args.analysis_only else "knowledge_update")
    run.set(
        status="running", stage="input", group_days=args.group_days, pattern_days=args.pattern_days
    )
    initializer = None
    chain = None
    cost_before = None
    analysis_result = None
    exit_code = 1

    try:
        cached_articles = None
        if args.input_json:
            cached_articles = TypeAdapter(list[RawArticle]).validate_json(
                args.input_json.read_bytes()
            )

        run.set(stage="bootstrap")
        initializer = initialize_knowledge_repository(settings)
        chain = create_llm_chain(settings)

        if chain.cost_tracker:
            cost_before = chain.cost_tracker.snapshot()

        partial = False

        if not args.analysis_only:
            processing = build_processing_pipeline(initializer, settings, chain)
            run.set(stage="acquisition")

            if cached_articles is not None:
                acquired = AcquisitionResult(
                    timestamp=datetime.now(timezone.utc),
                    total_sources=0,
                    successful_sources=0,
                    failed_sources=0,
                    total_articles=len(cached_articles),
                    execution_time=0.0,
                    articles=cached_articles,
                )
            else:
                from app.fetchers.registry import (
                    get_github_registry,
                    get_hf_registry,
                    get_source_registry,
                    initialize_github_registry,
                    initialize_hf_registry,
                    initialize_source_registry,
                )
                from app.pipelines.acquisition import DefaultAcquisitionPipeline

                initialize_source_registry(settings)
                initialize_github_registry(settings)
                initialize_hf_registry(settings)

                acquired = DefaultAcquisitionPipeline(
                    rss_registry=get_source_registry(),
                    github_registry=get_github_registry(),
                    hf_registry=get_hf_registry(),
                    settings=settings,
                ).run()

            run.set(
                input_mode="file" if cached_articles is not None else "live",
                articles_fetched=acquired.total_articles,
                sources_total=acquired.total_sources,
                sources_ok=acquired.successful_sources,
                sources_failed=acquired.failed_sources,
            )
            partial = acquired.failed_sources > 0

            if args.max_articles:
                selected = deduplicate_articles(acquired.articles)[: args.max_articles]
                acquired = replace(acquired, articles=selected)

            run.set(stage="processing", articles_selected=len(acquired.articles))
            processed = run_knowledge_update(acquired, processing, metrics=run.metrics)

            if processed is not None:
                run.set(processing=processed.model_dump(mode="json"))
                run.set(
                    articles_total_input=processed.total_input,
                    articles_extracted=processed.extracted,
                    objects_created=processed.objects_created,
                    objects_updated=processed.objects_updated,
                    objects_failed=processed.failed_objects,
                    objects_skipped=processed.skipped_objects,
                    objects_filtered=processed.filtered_objects,
                )
                partial = partial or processed.failed_objects > 0

        run.set(stage="analysis")
        service = create_analysis_service(initializer, chain)

        analysis_result = asyncio.run(
            run_analysis(
                service,
                limit=args.limit,
                group_days=args.group_days,
                pattern_days=args.pattern_days,
                skip_content=args.skip_content,
                metrics=run.metrics,
            )
        )

        run.set(status="partial" if partial else "success", stage="complete")
        exit_code = 1 if partial else 0

    except Exception as error:
        run.set(status="failed", error_type=type(error).__name__, error=str(error))
        logger.exception("Batch failed in stage %s", run.metrics["stage"])

    finally:
        if initializer is not None:
            initializer.shutdown()

        if chain is not None and chain.cost_tracker and cost_before is not None:
            cost_after = chain.cost_tracker.snapshot()
            run.set(
                llm_calls=cost_after["requests_today"] - cost_before["requests_today"],
                llm_tokens=cost_after["tokens_today"] - cost_before["tokens_today"],
                llm_cost_usd=round(cost_after["current_cost"] - cost_before["current_cost"], 6),
            )

        run.finish()

        try:
            run.save_jsonl(settings.run_metrics_path)

            if args.report:
                report = run.to_dict()
                report["analysis"] = (
                    analysis_result.model_dump(mode="json") if analysis_result else None
                )
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(
                    json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except OSError:
            logger.exception("Could not save run metrics/report")
            run.set(status="failed", stage="report")
            exit_code = 1

    print(f"Run {run.run_id}: {run.metrics['status']}; stage={run.metrics['stage']}")

    if analysis_result is not None:
        print(
            f"Content={len(analysis_result.content)}, groups={len(analysis_result.groups)}, "
            f"patterns={len(analysis_result.patterns)}"
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
