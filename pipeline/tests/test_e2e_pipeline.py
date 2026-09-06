"""
Opaque-Box End-to-End (E2E) Test Suite for EventWatch Impactful Classification Pipeline.

Covers Tiers 1 through 4:
  Tier 1: Feature Coverage (CLI entrypoint, Standby Mode, Schema Ingestion, Multi-Tier Dedup,
          Fast-Gate Noise Filter, Strict 6-Column Exporter)
  Tier 2: Boundary & Corner Cases (Empty workbooks, missing title columns, unicode/non-breaking spaces,
          100% duplicate workbooks, blank title rows, malformed files)
  Tier 3: Cross-Feature Combinations (Chained pipeline succession, --limit flag, --no-cache flag,
          Excel vs CSV output parity)
  Tier 4: Real-World Supply Chain Application Scenarios (Semiconductor fab fire zero-hour exception,
          arterial port strike, freight rail derailment to 'Other', unmapped Tier-2 explosion,
          class-action lawsuit ad filtering, past flight delay already over)
"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import openpyxl
import pytest

from pipeline.config import CANONICAL_EVENT_TYPES_SET, get_config
from pipeline.exporter import STRICT_OUTPUT_COLUMNS


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def run_cli_pipeline(
    args: Sequence[str],
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Executes the pipeline CLI via `python -m pipeline.main` as an opaque-box process."""
    import os

    cmd = [sys.executable, "-m", "pipeline.main", *args]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def create_test_workbook(
    file_path: Path | str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sheet_name: str = "Events",
) -> Path:
    """Creates a temporary Excel workbook with the specified headers and row data."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    wb.save(str(path))
    wb.close()
    return path


def read_exported_excel(file_path: Path | str) -> Tuple[Tuple[str, ...], List[List[Any]]]:
    """Reads an exported Excel workbook and returns (headers, data_rows)."""
    path = Path(file_path)
    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return (), []
    headers = tuple(str(h) if h is not None else "" for h in rows[0])
    data_rows = [list(r) for r in rows[1:]]
    return headers, data_rows


def read_exported_csv(file_path: Path | str) -> Tuple[Tuple[str, ...], List[List[str]]]:
    """Reads an exported CSV file and returns (headers, data_rows)."""
    path = Path(file_path)
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    if not reader:
        return (), []
    headers = tuple(reader[0])
    data_rows = reader[1:]
    return headers, data_rows


# ---------------------------------------------------------------------------
# TIER 1: Feature Coverage & CLI Integration
# ---------------------------------------------------------------------------

def test_tier1_cli_standby_mode_missing_input():
    """
    Tier 1: Requirement R4 Standby Mode.
    When the input workbook does not exist, the CLI must print the clean Standby Guide
    and exit with code 0.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_file = Path(tmp_dir) / "non_existent_input.xlsx"
        result = run_cli_pipeline(["--input", str(missing_file)])

        assert result.returncode == 0, f"Expected 0 exit code in standby mode, got {result.returncode}"
        assert "STANDBY MODE" in result.stdout
        assert "Notice: Input workbook was not found" in result.stdout
        assert "Supported Title Columns" in result.stdout
        assert "The pipeline is fully ready and waiting for your data file." in result.stdout


def test_tier1_cli_help_flag():
    """
    Tier 1: CLI Interface.
    Running `python -m pipeline.main --help` must display argument flags and exit with code 0.
    """
    result = run_cli_pipeline(["--help"])
    assert result.returncode == 0
    assert "EventWatch Supply Chain Disruption Classification Pipeline" in result.stdout
    assert "--input" in result.stdout
    assert "--output" in result.stdout
    assert "--model" in result.stdout
    assert "--batch-size" in result.stdout
    assert "--jaccard" in result.stdout
    assert "--no-cache" in result.stdout
    assert "--limit" in result.stdout


def test_tier1_flexible_schema_mapping_cli():
    """
    Tier 1: Ingestion & Schema Normalization.
    Verifies that the CLI seamlessly ingests alternative column aliases ('Story Title', 'Author')
    and outputs the strict 6-column standard.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "input_aliases.xlsx"
        output_xlsx = Path(tmp_dir) / "output_aliases.xlsx"

        # Headers using non-standard aliases
        headers = ["Story Title", "Author", "Severity Score"]
        rows = [
            ["Rosen Law Firm Announces Class Action Investigation of Super Micro", "John Doe", "High"],
            ["Manchester City defeats Arsenal 3-1 in Premier League match", "Jane Smith", "Low"],
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0, f"CLI execution failed:\n{result.stderr}"
        assert output_xlsx.is_file()

        excel_headers, excel_rows = read_exported_excel(output_xlsx)
        assert excel_headers == STRICT_OUTPUT_COLUMNS
        assert len(excel_rows) == 2
        assert excel_rows[0][0] == "Rosen Law Firm Announces Class Action Investigation of Super Micro"
        assert excel_rows[0][1] == "John Doe"
        assert excel_rows[1][0] == "Manchester City defeats Arsenal 3-1 in Premier League match"
        assert excel_rows[1][1] == "Jane Smith"


def test_tier1_multitier_dedup_cli():
    """
    Tier 1: Multi-Tier Deduplication.
    Verifies exact, prefix-stripped, and 3-gram clustering via CLI.
    Checks that deduplication statistics are printed and duplicate rows receive canonical evaluations.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "input_dedup.xlsx"
        output_xlsx = Path(tmp_dir) / "output_dedup.xlsx"

        headers = ["Feed Title", "Analyst Name"]
        rows = [
            ["Rosen Law Firm Announces Investigation of Super Micro", "Analyst A"],
            ["  Rosen Law Firm Announces Investigation of Super Micro  ", "Analyst B"],  # Exact after norm
            ["UPDATE 1: Rosen Law Firm Announces Investigation of Super Micro", "Analyst C"],  # Prefix
            ["ALERT - Rosen Law Firm Announces Investigation of Super Micro - Reuters", "Analyst D"],  # Prefix & Suffix
            ["Premier League: Arsenal vs Chelsea highlights and score", "Analyst E"],  # Distinct event
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0, f"CLI execution failed:\n{result.stderr}"

        # Check deduplication summary in stdout
        assert "Deduplication complete: 2 unique canonical items out of 5 rows" in result.stdout
        assert "60.0% reduction" in result.stdout
        assert "3 duplicates clustered" in result.stdout

        # Verify output file has all 5 rows with identical classification for cluster 1
        _, excel_rows = read_exported_excel(output_xlsx)
        assert len(excel_rows) == 5
        # All 4 rows in cluster 1 must be Not Impactful / Legal Action
        for idx in range(4):
            assert excel_rows[idx][2] == "Not Impactful"
            assert excel_rows[idx][3] == "Legal Action"


def test_tier1_fast_gate_noise_filter_cli():
    """
    Tier 1: Fast-Gate Pre-LLM Noise Filter.
    Verifies that the 14 Bad Article Taxonomy categories are filtered with zero LLM tokens.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "input_noise.xlsx"
        output_xlsx = Path(tmp_dir) / "output_noise.xlsx"

        headers = ["Feed Title", "Analyst Name"]
        rows = [
            ["Pomerantz Law Firm Reminds Investors of Class Action Deadline", "Garima"],
            ["NBA Finals: Boston Celtics win Championship game against Dallas", "Alex"],
            ["Celebrity couple spotted together at Hollywood film premiere", "Chris"],
            ["Residential duplex fire on Elm Street displaces family of four", "Sam"],
            ["Board of Directors declares regular quarterly cash dividend", "Morgan"],
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

        assert "5 noise items filtered instantly" in result.stdout
        assert "0 items sent to LLM Council Debater" in result.stdout

        _, excel_rows = read_exported_excel(output_xlsx)
        assert len(excel_rows) == 5
        for row in excel_rows:
            assert row[2] == "Not Impactful"
            assert "Bad Article Taxonomy" in row[4]


def test_tier1_strict_6column_exporter_verification():
    """
    Tier 1: Standardized 6-Column Tabular Exporter.
    Strictly verifies:
      1. Exact 6 columns in exact order:
         ['Feed Title', 'Analyst Name', 'Classification', 'Event Type', 'Rationale', 'Feedback']
      2. 'Feedback' column is strictly empty string "" for EVERY row.
      3. Parity between Excel (.xlsx) and CSV (.csv) exports.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "input_export.xlsx"
        output_xlsx = Path(tmp_dir) / "output_export.xlsx"
        output_csv = Path(tmp_dir) / "output_export.csv"

        headers = ["Feed Title", "Analyst Name"]
        rows = [
            ["Rosen Law Firm Announces Shareholder Lawsuit Against Super Micro", "Garima Sinha"],
            ["School board approves annual budget for public parks", "Alex Chen"],
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0
        assert output_xlsx.is_file()
        assert output_csv.is_file()

        # Check Excel
        excel_headers, excel_rows = read_exported_excel(output_xlsx)
        assert excel_headers == STRICT_OUTPUT_COLUMNS
        assert len(excel_rows) == 2
        for r in excel_rows:
            assert len(r) == 6
            # Feedback column at index 5 must be None or empty string
            assert r[5] in ("", None)

        # Check CSV
        csv_headers, csv_rows = read_exported_csv(output_csv)
        assert csv_headers == STRICT_OUTPUT_COLUMNS
        assert len(csv_rows) == 2
        for r in csv_rows:
            assert len(r) == 6
            # In CSV, Feedback must be strictly empty string
            assert r[5] == ""


# ---------------------------------------------------------------------------
# TIER 2: Boundary & Corner Cases
# ---------------------------------------------------------------------------

def test_tier2_empty_file_zero_rows():
    """
    Tier 2: Boundary Condition - Workbook with 0 data rows (headers only).
    The pipeline must gracefully log an error and exit with code 1.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "empty_workbook.xlsx"
        create_test_workbook(input_xlsx, ["Feed Title", "Analyst Name"], [])

        result = run_cli_pipeline(["-i", str(input_xlsx)])
        assert result.returncode == 1
        assert "Error: No valid records found in the input workbook." in result.stdout


def test_tier2_missing_title_column():
    """
    Tier 2: Boundary Condition - Workbook missing any recognizable title column.
    The pipeline must raise an error indicating the missing title column and exit non-zero.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "missing_title.xlsx"
        create_test_workbook(input_xlsx, ["Category", "Location", "Date"], [["Industrial", "Munich", "2026-01-01"]])

        result = run_cli_pipeline(["-i", str(input_xlsx)])
        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        assert "Could not locate a title column" in combined_output


def test_tier2_unicode_non_breaking_spaces():
    """
    Tier 2: Boundary Condition - Inputs containing non-breaking spaces (\xa0),
    zero-width spaces (\u200b), BOM markers (\ufeff), and irregular spacing.
    Verifies that titles are sanitized and normalized without artifact corruptions.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "unicode_input.xlsx"
        output_xlsx = Path(tmp_dir) / "unicode_output.xlsx"

        headers = ["Feed Title", "Analyst Name"]
        dirty_title = "\ufeff  Rosen\xa0Law\u200b Firm  Announces\xa0\xa0Investigation  "
        rows = [[dirty_title, "Garima\xa0Sinha"]]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0

        _, excel_rows = read_exported_excel(output_xlsx)
        assert len(excel_rows) == 1
        exported_title = excel_rows[0][0]
        # Should be stripped of unicode non-breaking spaces
        assert "\xa0" not in exported_title
        assert "\u200b" not in exported_title
        assert "\ufeff" not in exported_title
        assert "Rosen Law Firm Announces Investigation" in exported_title


def test_tier2_100_percent_duplicate_workbook():
    """
    Tier 2: Boundary Condition - Workbook containing 100% identical duplicate rows.
    Verifies that the deduplicator collapses all rows to 1 canonical item,
    and the exporter maps the single evaluation back to all 10 rows.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "all_duplicates.xlsx"
        output_xlsx = Path(tmp_dir) / "all_duplicates_out.xlsx"

        title = "Pomerantz Law Firm Investigates Securities Claims on Behalf of Investors"
        headers = ["Feed Title", "Analyst Name"]
        rows = [[title, f"Analyst_{i}"] for i in range(10)]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0

        assert "1 unique canonical items out of 10 rows" in result.stdout
        assert "90.0% reduction" in result.stdout
        assert "9 duplicates clustered" in result.stdout

        _, excel_rows = read_exported_excel(output_xlsx)
        assert len(excel_rows) == 10
        for i, row in enumerate(excel_rows):
            assert row[0] == title
            assert row[1] == f"Analyst_{i}"
            assert row[2] == "Not Impactful"
            assert row[3] == "Legal Action"


def test_tier2_zero_event_blank_titles_skipped():
    """
    Tier 2: Boundary Condition - Rows with empty or whitespace-only titles.
    Verifies that blank title rows are safely ignored while rows with content are processed.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "blank_titles.xlsx"
        output_xlsx = Path(tmp_dir) / "blank_titles_out.xlsx"

        headers = ["Feed Title", "Analyst Name"]
        rows = [
            ["", "Ghost Analyst"],
            ["   \xa0 \t  ", "Another Ghost"],
            ["Rosen Law Firm Announces Class Action against Tech Corp", "Valid Analyst"],
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0
        assert "Loaded 1 total rows successfully." in result.stdout

        _, excel_rows = read_exported_excel(output_xlsx)
        assert len(excel_rows) == 1
        assert excel_rows[0][0] == "Rosen Law Firm Announces Class Action against Tech Corp"


def test_tier2_malformed_corrupted_file():
    """
    Tier 2: Boundary Condition - Completely corrupt or non-Excel file.
    Verifies that the pipeline halts gracefully with a non-zero exit code without unhandled crashes.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        corrupt_file = Path(tmp_dir) / "corrupt.xlsx"
        corrupt_file.write_text("This is not an Excel file!", encoding="utf-8")

        result = run_cli_pipeline(["-i", str(corrupt_file)])
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# TIER 3: Cross-Feature Combinations & Execution Flow
# ---------------------------------------------------------------------------

def test_tier3_chained_pipeline_succession():
    """
    Tier 3: Cross-Feature Integration.
    Chains all pipeline stages in sequence:
      1. Schema Mapping: flexible alias resolution.
      2. Multi-tier Dedup: exact + prefix deduplication.
      3. Fast-Gate Noise Filter: pre-LLM filtering of bad articles.
      4. Standardized Exporter: dual Excel + CSV export with strict 6 columns.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "chained_input.xlsx"
        output_xlsx = Path(tmp_dir) / "chained_out.xlsx"
        output_csv = Path(tmp_dir) / "chained_out.csv"

        headers = ["Headline", "Author"]  # Alternate aliases
        rows = [
            # Cluster 1: Noise item (Law Firm Ad) with prefix variation
            ["Rosen Law Firm Reminds Investors of Deadline in Super Micro Litigation", "Analyst 1"],
            ["UPDATE 1: Rosen Law Firm Reminds Investors of Deadline in Super Micro Litigation", "Analyst 2"],
            # Cluster 2: Noise item (Sports)
            ["Champions League: Real Madrid advances to semifinals after penalty shootout", "Analyst 3"],
            # Cluster 3: Noise item (Civilian domestic incident)
            ["Residential house fire on Maple Street displaces family", "Analyst 4"],
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0, f"Chained execution failed:\n{result.stderr}"

        # Check deduplication stats
        assert "3 unique canonical items out of 4 rows" in result.stdout
        # Check fast-gate filter stats
        assert "3 noise items filtered instantly" in result.stdout
        # Check export files
        assert output_xlsx.is_file()
        assert output_csv.is_file()

        _, excel_rows = read_exported_excel(output_xlsx)
        assert len(excel_rows) == 4
        assert excel_rows[0][2] == "Not Impactful"
        assert excel_rows[1][2] == "Not Impactful"


def test_tier3_cli_limit_parameter():
    """
    Tier 3: Argument Handling - Verifies that the `--limit N` flag restricts
    processing to exactly N rows.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "limit_input.xlsx"
        output_xlsx = Path(tmp_dir) / "limit_output.xlsx"

        headers = ["Feed Title", "Analyst Name"]
        rows = [
            [f"Rosen Law Firm announces investigation number {i}", "Analyst"]
            for i in range(10)
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx), "--limit", "3"])
        assert result.returncode == 0
        assert "Limiting input to first 3 records as requested." in result.stdout

        _, excel_rows = read_exported_excel(output_xlsx)
        assert len(excel_rows) == 3


def test_tier3_dual_export_exact_parity():
    """
    Tier 3: Output Parity.
    Verifies that Excel (.xlsx) and CSV (.csv) exports generated simultaneously
    match row-for-row, column-for-column across all 6 fields.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "parity_input.xlsx"
        output_xlsx = Path(tmp_dir) / "parity_out.xlsx"
        output_csv = Path(tmp_dir) / "parity_out.csv"

        headers = ["Feed Title", "Analyst Name"]
        rows = [
            ["Shareholder alert: Robbins Geller files class action against BigTech", "Analyst Alpha"],
            ["City council approves municipal park renovation project", "Analyst Beta"],
            ["Hollywood actor attends gala film premiere in London", "Analyst Gamma"],
        ]
        create_test_workbook(input_xlsx, headers, rows)

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0

        excel_headers, excel_rows = read_exported_excel(output_xlsx)
        csv_headers, csv_rows = read_exported_csv(output_csv)

        assert excel_headers == csv_headers == STRICT_OUTPUT_COLUMNS
        assert len(excel_rows) == len(csv_rows) == 3

        for e_row, c_row in zip(excel_rows, csv_rows):
            # Columns 0 to 4 (Title, Analyst, Classification, Event Type, Rationale)
            for col_idx in range(5):
                assert str(e_row[col_idx]).strip() == str(c_row[col_idx]).strip()
            # Column 5 (Feedback) must be empty
            assert e_row[5] in ("", None)
            assert c_row[5] == ""


def test_tier3_cli_no_cache_flag():
    """
    Tier 3: CLI Flag - Verifies that `--no-cache` flag is accepted without errors.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "nocache_input.xlsx"
        output_xlsx = Path(tmp_dir) / "nocache_out.xlsx"

        create_test_workbook(
            input_xlsx,
            ["Feed Title", "Analyst Name"],
            [["Rosen Law Firm Class Action Reminder", "Analyst"]],
        )

        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx), "--no-cache"])
        assert result.returncode == 0
        assert output_xlsx.is_file()


# ---------------------------------------------------------------------------
# TIER 4: Real-World Supply Chain Application Scenarios
# ---------------------------------------------------------------------------

def test_tier4_real_world_supply_chain_scenarios():
    """
    Tier 4: Comprehensive Real-World Application Scenarios.
    Executes a complete batch representing the core EventWatch threshold edge cases:
      Scenario 1 (Semiconductor Fab Fire):
        Cleanroom fire extinguished with zero downtime -> Zero-Hour Exception PA-007/008 dictates IMPACTFUL (Factory Fire).
      Scenario 2 (Arterial Port Strike):
        Dockworkers strike shutting container terminal -> IMPACTFUL (Labor Disruption or Port Disruption).
      Scenario 3 (Freight Rail Derailment):
        Freight train derailment carrying industrial chemicals -> IMPACTFUL (strictly normalized to 'Other',
        enforcing Challenger 2 Ground Transportation Negative Rule).
      Scenario 4 (Unmapped Tier-2 Industrial Explosion):
        Tier-2 chemical facility explosion -> IMPACTFUL (Chemical Spill or Factory Disruption) under Mapped Partner bias.
      Scenario 5 (Class-Action Lawsuit Ad):
        Rosen Law Firm shareholder solicitation -> NOT IMPACTFUL (Legal Action) under Bad Article Taxonomy.
      Scenario 6 (Past Flight Delay Already Over):
        Passenger airline delays cleared after morning storm with zero freight impact -> NOT IMPACTFUL (Other)
        under Already Over Tripartite Rule.
    """
    config = get_config()
    if not config.openai_api_key and not config.gemini_api_key:
        pytest.skip("Skipping Tier 4 live LLM test: No API keys configured.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        input_xlsx = Path(tmp_dir) / "tier4_scenarios.xlsx"
        output_xlsx = Path(tmp_dir) / "tier4_output.xlsx"
        output_csv = Path(tmp_dir) / "tier4_output.csv"

        headers = ["Feed Title", "Analyst Name"]
        scenarios = [
            # 1. Semiconductor Fab Fire (Zero-Hour Exception)
            ["Fire breaks out at Samsung Electronics semiconductor manufacturing plant in Giheung, extinguished in 15 minutes with fab resuming", "Garima Sinha"],
            # 2. Arterial Port Strike
            ["Dockworkers union initiates strike shutting container cargo terminals at Port of Los Angeles", "Alex Chen"],
            # 3. Freight Rail Derailment (Ground Transport Negative Rule)
            ["Norfolk Southern freight train derails in Ohio spilling industrial chemicals and halting mainline cargo corridor", "Shazma Nigar"],
            # 4. Unmapped Tier-2 Industrial Explosion
            ["Massive explosion destroys Tier-2 chemical resin manufacturing facility supplying automotive OEMs", "Garima Sinha"],
            # 5. Class-Action Lawsuit Ad (Bad Article Fast Gate)
            ["Rosen Law Firm Reminds Investors of Lead Plaintiff Deadline in Securities Class Action Lawsuit Against Intel", "Alex Chen"],
            # 6. Past Flight Delay Already Over (Already Over Tripartite Rule)
            ["Morning passenger flight delays at Chicago O'Hare cleared following thunderstorm with normal airline operations restored", "Shazma Nigar"],
        ]
        create_test_workbook(input_xlsx, headers, scenarios)

        # Run pipeline via opaque-box CLI
        result = run_cli_pipeline(["-i", str(input_xlsx), "-o", str(output_xlsx)])
        assert result.returncode == 0, f"Pipeline execution failed:\n{result.stderr}"

        # Verify output Excel and CSV exist
        assert output_xlsx.is_file()
        assert output_csv.is_file()

        excel_headers, excel_rows = read_exported_excel(output_xlsx)
        assert excel_headers == STRICT_OUTPUT_COLUMNS
        assert len(excel_rows) == 6

        # Check every row has valid canonical 48 event type and empty feedback
        for r in excel_rows:
            assert r[2] in ("Impactful", "Not Impactful"), f"Invalid classification: {r[2]}"
            assert r[3] in CANONICAL_EVENT_TYPES_SET, f"Non-canonical event type: {r[3]}"
            assert len(str(r[4])) > 5, f"Missing or thin rationale: {r[4]}"
            assert r[5] in ("", None), f"Feedback column is not empty: {r[5]}"

        # --- SCENARIO-SPECIFIC THRESHOLD ASSERTIONS ---

        # Scenario 1: Fab Fire -> Impactful, Factory Fire
        fab_fire = excel_rows[0]
        assert fab_fire[2] == "Impactful", f"Fab fire should be Impactful under PA-007/008, got: {fab_fire[2]}"
        assert fab_fire[3] in ("Factory Fire", "Factory Disruption")

        # Scenario 2: Port Strike -> Impactful, Labor Disruption or Port Disruption
        port_strike = excel_rows[1]
        assert port_strike[2] == "Impactful", f"Port strike should be Impactful, got: {port_strike[2]}"
        assert port_strike[3] in ("Labor Disruption", "Port Disruption")

        # Scenario 3: Freight Rail Derailment -> Impactful, STRICTLY normalized to 'Other', 'Chemical Spill', or 'Environmental Hazard'
        # Must NOT be 'Rail Disruption', 'Highway Disruption', or 'Train Derailment'
        rail_derailment = excel_rows[2]
        assert rail_derailment[2] == "Impactful", f"Freight derailment should be Impactful, got: {rail_derailment[2]}"
        assert rail_derailment[3] in ("Other", "Chemical Spill", "Environmental Hazard"), f"Prohibited transport type produced: {rail_derailment[3]}"
        assert rail_derailment[3] not in ("Rail Disruption", "Train Derailment", "Highway Disruption", "Transportation Disruption")

        # Scenario 4: Tier-2 Chemical Explosion -> Impactful
        tier2_explosion = excel_rows[3]
        assert tier2_explosion[2] == "Impactful", f"Tier-2 chemical facility explosion should be Impactful, got: {tier2_explosion[2]}"
        assert tier2_explosion[3] in ("Factory Disruption", "Factory Fire", "Chemical Spill", "Environmental Hazard", "Other")

        # Scenario 5: Class Action Ad -> Not Impactful, Legal Action
        law_ad = excel_rows[4]
        assert law_ad[2] == "Not Impactful", f"Law firm ad should be Not Impactful, got: {law_ad[2]}"
        assert law_ad[3] == "Legal Action"

        # Scenario 6: Past Flight Delay Already Over -> Not Impactful
        flight_delay = excel_rows[5]
        assert flight_delay[2] == "Not Impactful", f"Resolved flight delay should be Not Impactful, got: {flight_delay[2]}"
        assert flight_delay[3] in ("Airport Disruption", "Other")

