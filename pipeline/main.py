"""
Main CLI entrypoint for EventWatch Impactful Classification Pipeline.
Orchestrates schema ingestion, multi-tier deduplication, fast-gate noise filtering,
EventWatch Council LLM evaluation, disk caching, and tabular export.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from tqdm import tqdm

from pipeline.cache import DiskCache
from pipeline.config import PipelineConfig, get_config
from pipeline.council_engine import EventEvaluation
from pipeline.dedup import MultiTierDeduplicator
from pipeline.exporter import export_results
from pipeline.llm_client import CouncilLLMClient
from pipeline.noise_filter import FastGateNoiseFilter
from pipeline.schema_mapper import InputRecord, load_excel_records


def print_standby_guide(missing_path: Path) -> None:
    """Displays a clean, helpful guide message when the input file is not found (Requirement R4)."""
    border = "=" * 80
    guide_msg = f"""
{border}
EVENTWATCH IMPACTFUL CLASSIFICATION PIPELINE — STANDBY MODE
{border}
Notice: Input workbook was not found at:
  {missing_path.resolve()}

To run the automated classification pipeline:
  1. Place your input Excel workbook (e.g. 'NotImpctful Events.xlsx') in the project root:
     {missing_path.parent.resolve()}
  2. Or specify an alternate file path using the --input argument:
     python -m pipeline.main --input "path/to/your_file.xlsx"

Workbook Schema Guidelines:
  - Supported Title Columns: 'Feed Title', 'Bulletin Title', 'Story Title', 'Title', 'Headline'
  - Supported Analyst Columns: 'Analyst Name', 'Moved To Published By', 'Author' (optional)

Pipeline Features Active:
  - Multi-Tier Deduplication (Exact, Update Prefixes, Character 3-Gram Jaccard >= 0.75)
  - Pre-LLM 14 Bad Article Taxonomy Noise Filter (Zero-Token Fast Gate)
  - EventWatch Council Multi-Role Debater Engine (Guardian, Controller, Judge)
  - Persistent Disk Checkpoint Cache (cache.json)
  - Strict 6-Column Tabular Export (.xlsx and .csv)

The pipeline is fully ready and waiting for your data file.
{border}
"""
    print(guide_msg)


def run_pipeline(
    input_file: Path | str,
    output_file: Path | str,
    model_name: str | None = None,
    batch_size: int | None = None,
    jaccard_threshold: float = 0.75,
    use_cache: bool = True,
    limit: int | None = None,
) -> int:
    """Executes the full end-to-end classification pipeline."""
    start_time = time.time()
    config = get_config()

    if batch_size is not None:
        config.batch_size = batch_size
    if model_name is not None:
        config.default_model = model_name

    input_path = Path(input_file)
    output_path = Path(output_file)

    # Production readiness (R4): Check if input exists
    if not input_path.is_file():
        print_standby_guide(input_path)
        return 0

    print("=" * 80)
    print("EVENTWATCH SUPPLY CHAIN DISRUPTION CLASSIFICATION PIPELINE")
    print(f"Input Workbook : {input_path.resolve()}")
    print(f"Output Target  : {output_path.resolve()}")
    print(f"Model Selected : {config.default_model}")
    print(f"Batch Size     : {config.batch_size}")
    print("=" * 80)

    # Step 1: Ingest Excel records
    print("\n[Step 1/5] Ingesting and normalizing Excel records...")
    records = load_excel_records(input_path)
    if not records:
        print("Error: No valid records found in the input workbook.")
        return 1

    if limit is not None and limit > 0:
        print(f"Limiting input to first {limit} records as requested.")
        records = records[:limit]

    total_rows = len(records)
    print(f"Loaded {total_rows} total rows successfully.")

    # Step 2: Multi-tier Deduplication
    print("\n[Step 2/5] Running multi-tier deduplication (Exact, Prefix-Stripped, 3-Gram Jaccard)...")
    dedup = MultiTierDeduplicator(jaccard_threshold=jaccard_threshold)
    dedup_result = dedup.deduplicate(records)
    canonical_items = dedup_result.canonical_items
    print(
        f"Deduplication complete: {len(canonical_items)} unique canonical items out of {total_rows} rows "
        f"({dedup_result.reduction_percentage:.1f}% reduction, {dedup_result.duplicate_count} duplicates clustered)."
    )

    # Step 3: Fast-Gate Noise Filtering
    print("\n[Step 3/5] Applying pre-LLM fast-gate noise filter (14 Bad Article Categories)...")
    noise_filter = FastGateNoiseFilter()
    cache = DiskCache(config.cache_path) if use_cache else None

    canonical_evaluations: Dict[int, EventEvaluation] = {}
    items_for_llm: List[Dict[str, Any]] = []
    noise_count = 0
    cache_hit_count = 0

    for item in canonical_items:
        # Pre-LLM Noise Filter check
        verdict = noise_filter.evaluate(item.prefix_stripped_title)
        if verdict.is_noise:
            canonical_evaluations[item.canonical_id] = EventEvaluation(
                id=item.canonical_id,
                classification=verdict.classification,  # type: ignore[arg-type]
                event_type=verdict.event_type,
                rationale=verdict.rationale,
            )
            noise_count += 1
            continue

        # Check Cache
        if cache is not None:
            cached_data = cache.get(item.normalized_title)
            if cached_data:
                canonical_evaluations[item.canonical_id] = EventEvaluation(
                    id=item.canonical_id,
                    classification=cached_data.get("classification", "Not Impactful"),
                    event_type=cached_data.get("event_type", "Other"),
                    rationale=cached_data.get("rationale", ""),
                )
                cache_hit_count += 1
                continue

        # Needs LLM evaluation
        items_for_llm.append({
            "id": item.canonical_id,
            "title": item.raw_title,
            "norm_title": item.normalized_title,
        })

    print(
        f"Filter & Cache summary: {noise_count} noise items filtered instantly; "
        f"{cache_hit_count} items retrieved from cache; "
        f"{len(items_for_llm)} items sent to LLM Council Debater."
    )

    # Step 4: LLM Council Multi-Role Debater Evaluation
    if items_for_llm:
        print(f"\n[Step 4/5] Executing EventWatch Council Debater evaluation via {config.default_model}...")
        llm_client = CouncilLLMClient(config=config, model_name=config.default_model)

        # Batch processing
        batches = [
            items_for_llm[i : i + config.batch_size]
            for i in range(0, len(items_for_llm), config.batch_size)
        ]

        with tqdm(total=len(items_for_llm), desc="Council Evaluation", unit="events") as pbar:
            for batch in batches:
                batch_input = [{"id": b["id"], "title": b["title"]} for b in batch]
                evaluations = llm_client.evaluate_batch(batch_input)
                eval_map = {e.id: e for e in evaluations}

                for b in batch:
                    canon_id = b["id"]
                    norm_title = b["norm_title"]
                    res = eval_map.get(canon_id)
                    if res is None:
                        # Fallback if specific item was omitted by LLM
                        res = EventEvaluation(
                            id=canon_id,
                            classification="Not Impactful",
                            event_type="Other",
                            rationale="Not Impactful as evaluation could not confirm operational disruption.",
                        )

                    canonical_evaluations[canon_id] = res

                    # Save to cache
                    if cache is not None:
                        cache.set(
                            norm_title,
                            {
                                "classification": res.classification,
                                "event_type": res.event_type,
                                "rationale": res.rationale,
                            },
                        )
                pbar.update(len(batch))

        if cache is not None:
            cache.save()
            print(f"Persistent cache updated at: {config.cache_path.resolve()}")
    else:
        print("\n[Step 4/5] No uncached items required LLM evaluation.")

    # Step 5: Map Evaluations Back to All Original Rows & Export
    print("\n[Step 5/5] Re-mapping canonical evaluations to original rows and exporting...")
    output_rows: List[Dict[str, Any]] = []
    impactful_count = 0
    not_impactful_count = 0

    for record in records:
        canon_id = dedup_result.row_to_canonical_id[record.row_id]
        evaluation = canonical_evaluations[canon_id]

        if evaluation.classification == "Impactful":
            impactful_count += 1
        else:
            not_impactful_count += 1

        output_rows.append({
            "Feed Title": record.raw_title,
            "Analyst Name": record.analyst_name,
            "Classification": evaluation.classification,
            "Event Type": evaluation.event_type,
            "Rationale": evaluation.rationale,
            "Feedback": "",
        })

    export_files = export_results(output_rows, excel_path=output_path)

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print("PIPELINE EXECUTION COMPLETE")
    print(f"Total Rows Processed : {total_rows}")
    print(f"Unique Events        : {len(canonical_items)}")
    print(f"Impactful Verdicts   : {impactful_count} ({impactful_count/total_rows*100:.1f}%)")
    print(f"Not Impactful        : {not_impactful_count} ({not_impactful_count/total_rows*100:.1f}%)")
    print(f"Excel Report         : {export_files['excel'].resolve()}")
    print(f"CSV Report           : {export_files['csv'].resolve()}")
    print(f"Total Elapsed Time   : {elapsed:.2f} seconds")
    print("=" * 80)

    return 0


def main() -> None:
    """CLI parsing entrypoint."""
    parser = argparse.ArgumentParser(
        description="EventWatch Supply Chain Disruption Classification Pipeline"
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="NotImpctful Events.xlsx",
        help="Path to input Excel workbook (default: 'NotImpctful Events.xlsx')",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="output/classified_events.xlsx",
        help="Path for generated output Excel workbook (default: 'output/classified_events.xlsx')",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=None,
        help="LLM Model to use (default: gpt-4o-mini or gemini-3.6-flash)",
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        type=int,
        default=15,
        help="Batch size for LLM evaluation (default: 15)",
    )
    parser.add_argument(
        "--jaccard",
        type=float,
        default=0.75,
        help="Jaccard similarity threshold for Tier 3 deduplication (default: 0.75)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable disk caching",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit execution to first N records (useful for rapid testing)",
    )

    args = parser.parse_args()

    exit_code = run_pipeline(
        input_file=args.input,
        output_file=args.output,
        model_name=args.model,
        batch_size=args.batch_size,
        jaccard_threshold=args.jaccard,
        use_cache=not args.no_cache,
        limit=args.limit,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
