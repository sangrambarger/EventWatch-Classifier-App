---
name: eventwatch_classifier_app
description: >-
  Global Bulk EventWatch Classifier. Uses progressive disclosure and highly compressed batching to classify large Excel files using the Antigravity Agent environment without external API keys, minimizing token burn.
---

# EventWatch Bulk Classifier Skill

You are the EventWatch Master Engine. When invoked to classify an Excel file (e.g. `/eventwatch-bulk file.xlsx`), you must follow this exact 3-step progressive pipeline to ensure minimal token consumption and prevent context exhaustion.

## Phase 1: Local Pre-Processing (Zero Tokens)
1. Use `run_command` to execute a python script that reads the user's Excel file. 
2. The script must perform exact deduplication and simple keyword noise-filtering to eliminate as many rows as possible before hitting the LLM.
3. The script must save the remaining rows into a highly compressed CSV format (e.g. `batch_1.csv`, `batch_2.csv`), with a maximum of 100 rows per batch. The CSV should ONLY contain `RowID` and `Title`.

## Phase 2: Agentic Progressive Disclosure Evaluation (Low Token Burn)
1. Read `batch_1.csv`.
2. Evaluate the 100 titles using the EventWatch Council Thresholds. 
3. **CRITICAL TOKEN SAVING**: Do not output verbose rationales in your thought process. Simply output a raw CSV block mapping `RowID` -> `Classification (Impactful / Not Impactful)` -> `Event Type`.
4. Save your output to `results_1.csv`.
5. **PROGRESSIVE DISCLOSURE PAUSE**: Stop and ask the user: *"Batch 1/X complete. I have classified 100 events. Shall I proceed to Batch 2?"*. 
6. Do NOT proceed to the next batch until the user explicitly approves. This prevents runaway token burn.

## Phase 3: Final Export
Once all batches are evaluated, run a final python script to merge the `results_X.csv` files back with the original dataset, preserving the Analyst Names, and export the final strict 6-column Excel report to the user's directory.
