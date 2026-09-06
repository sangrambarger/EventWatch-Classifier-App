import pandas as pd
import sys
import os
import argparse

def prepare_batches(input_file, batch_size=100):
    print(f"Reading {input_file}...")
    try:
        df = pd.read_excel(input_file)
    except Exception as e:
        print(f"Error reading excel: {e}")
        return

    # Basic schema mapping fallback
    title_col = None
    for col in df.columns:
        if str(col).lower() in ["feed title", "title", "headline", "story title"]:
            title_col = col
            break
            
    if not title_col:
        print("Could not find a Title column.")
        return

    # Deduplication
    initial_len = len(df)
    df = df.drop_duplicates(subset=[title_col])
    dedup_len = len(df)
    print(f"Deduplication: Reduced from {initial_len} to {dedup_len} rows.")

    # Select only necessary columns to save space
    df['RowID'] = range(1, len(df) + 1)
    export_df = df[['RowID', title_col]]
    
    # Chunking
    num_batches = (len(export_df) + batch_size - 1) // batch_size
    
    for i in range(num_batches):
        batch = export_df.iloc[i*batch_size : (i+1)*batch_size]
        batch_filename = f"batch_{i+1}.csv"
        batch.to_csv(batch_filename, index=False)
        print(f"Created {batch_filename} ({len(batch)} rows)")
        
    print(f"\nSuccessfully created {num_batches} batches.")
    print("Agent Instruction: Read batch_1.csv, classify it, write to results_1.csv, then PAUSE for user approval.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    prepare_batches(args.input, args.batch_size)
