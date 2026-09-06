"""
Unit and integration tests for schema_mapper.py.
Verifies column alias matching, unicode sanitization, row index preservation, and real workbook loading.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import openpyxl
import pytest

from pipeline.schema_mapper import (
    clean_unicode_text,
    find_column_index,
    load_excel_records,
    normalize_title_for_comparison,
    TITLE_ALIASES,
    ANALYST_ALIASES,
)


def test_clean_unicode_text():
    """Verify stripping of non-breaking spaces and whitespace collapse."""
    raw = "  Fire\xa0at\u200b  Samsung\xa0Semiconductor   "
    cleaned = clean_unicode_text(raw)
    assert cleaned == "Fire at Samsung Semiconductor"
    assert clean_unicode_text(None) == ""
    assert clean_unicode_text(12345) == "12345"


def test_normalize_title_for_comparison():
    """Verify lowercasing and standard normalization."""
    title = "UPDATE 2: Explosion at TSMC Fab 18\xa0 "
    norm = normalize_title_for_comparison(title)
    assert norm == "update 2: explosion at tsmc fab 18"


def test_find_column_index():
    """Verify flexible alias matching for title and analyst."""
    headers = ["ID", "Feed Title", "Moved To Published By", "Details"]
    t_idx = find_column_index(headers, TITLE_ALIASES)
    a_idx = find_column_index(headers, ANALYST_ALIASES)
    assert t_idx == 1
    assert a_idx == 2

    # Alternate alias
    headers2 = ["Headline", "Author", "Date"]
    assert find_column_index(headers2, TITLE_ALIASES) == 0
    assert find_column_index(headers2, ANALYST_ALIASES) == 1

    # Missing column
    assert find_column_index(["Category", "Location"], TITLE_ALIASES) is None


def test_load_excel_records_synthetic():
    """Verify record loading, row_id tracking, and default analyst assignment."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "test_events.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Events"
        ws.append(["Story Title", "Analyst Name", "Notes"])
        ws.append(["Strike at Port of Los Angeles", "Garima Sinha", "P1"])
        ws.append(["  Fire at Chem Plant\xa0", "", "P2"])  # Blank analyst
        ws.append(["", "Bob", "Empty title row"])  # Empty title -> skipped
        ws.append(["Power outage in Dresden", "Alex Chen", "P0"])
        wb.save(str(tmp_path))
        wb.close()

        records = load_excel_records(tmp_path)
        assert len(records) == 3

        # Row indices should match Excel row numbers (1-based)
        assert records[0].row_id == 2
        assert records[0].raw_title == "Strike at Port of Los Angeles"
        assert records[0].analyst_name == "Garima Sinha"

        assert records[1].row_id == 3
        assert records[1].raw_title == "Fire at Chem Plant"
        assert records[1].analyst_name == "Unassigned"

        assert records[2].row_id == 5
        assert records[2].raw_title == "Power outage in Dresden"
        assert records[2].analyst_name == "Alex Chen"


def test_load_excel_records_real_notified_story_report():
    """Integration test: Verify loading against actual workspace 04_Notified_Story_Report.xlsx."""
    real_path = Path("04_Notified_Story_Report.xlsx")
    if real_path.is_file():
        records = load_excel_records(real_path)
        assert len(records) > 0
        first = records[0]
        # Verify Bulletin Title and Moved To Published By mapped correctly
        assert "Ford" in first.raw_title
        assert first.analyst_name == "Garima Sinha"
        assert first.row_id == 2
