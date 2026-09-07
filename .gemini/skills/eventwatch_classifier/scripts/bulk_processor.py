import pandas as pd
import sys
import os
import argparse
from pathlib import Path

# Add project root to sys path so we can import pipeline
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent.parent))
from pipeline.schema_mapper import load_excel_records
from pipeline.dedup import MultiTierDeduplicator

def prepare_batches(input_file, batch_size=100):
    print(f"Reading {input_file}...")
    try:
        # Step 1: Load and map using the actual pipeline schema mapper
        records = load_excel_records(input_file)
        if not records:
            print("No records found or failed to parse.")
            return
            
        initial_len = len(records)
        
        # Step 2: Multi-tier Deduplication (Exact, Prefix-Stripped, 3-Gram Jaccard)
        print("Running full-file multi-tier deduplication (Jaccard=0.45)...")
        dedup = MultiTierDeduplicator(jaccard_threshold=0.45)
        dedup_result = dedup.deduplicate(records)
        
        dedup_len = dedup_result.unique_items_count
        print(f"Deduplication: Reduced from {initial_len} to {dedup_len} rows.")
        
        # Extract unique canonical titles and their original metadata
        canonical_rows = []
        for i, item in enumerate(dedup_result.canonical_items):
            row_dict = {"RowID": i + 1}
            # Add all original metadata from the representative record
            row_dict.update(item.representative_record.metadata)
            canonical_rows.append(row_dict)
        
        # Put it back in a DataFrame for batching
        df = pd.DataFrame(canonical_rows)
        
        # Chunking
        num_batches = (len(df) + batch_size - 1) // batch_size
        
        for i in range(num_batches):
            batch = df.iloc[i*batch_size : (i+1)*batch_size]
            batch_filename = f"batch_{i+1}.csv"
            batch.to_csv(batch_filename, index=False)
            print(f"Created {batch_filename} ({len(batch)} rows)")
            
        print(f"\nSuccessfully created {num_batches} batches.")
        print("Agent Instruction: Read batch_1.csv, classify it, write to results_1.csv, then PAUSE for user approval.")
        
    except Exception as e:
        print(f"Error reading excel: {e}")
        return

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    prepare_batches(args.input, args.batch_size)
