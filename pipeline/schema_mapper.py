"""
Schema mapper and flexible Excel ingestion module for EventWatch pipeline.
Handles column alias resolution, unicode cleaning, and row index preservation.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import openpyxl
from pydantic import BaseModel, Field


TITLE_ALIASES: Sequence[str] = (
    "feed title",
    "bulletin title",
    "story title",
    "title",
    "headline",
    "event title",
    "news title",
    "article title",
    "disruption title",
)

ANALYST_ALIASES: Sequence[str] = (
    "analyst name",
    "moved to published by",
    "author",
    "analyst",
    "published by",
    "created by",
    "editor",
    "owner",
    "moved to not impactful (owner)",
)

def clean_unicode_text(text: Optional[str]) -> str:
    """Strip unicode spaces, non-breaking spaces, and normalize whitespace."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    # Replace non-breaking spaces and zero-width spaces
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
    # Normalize unicode to NFKC
    text = unicodedata.normalize("NFKC", text)
    # Collapse multiple whitespace characters to single space
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title_for_comparison(title: str) -> str:
    """Canonical normalization for deduplication and comparison."""
    cleaned = clean_unicode_text(title)
    # Lowercase and trim punctuation on edges
    normalized = cleaned.lower()
    return normalized


class InputRecord(BaseModel):
    """Represents a single ingested event row from the input Excel spreadsheet."""

    row_id: int = Field(description="1-based original Excel row number")
    raw_title: str = Field(description="Original feed title extracted from Excel")
    normalized_title: str = Field(description="Cleaned, normalized title")
    analyst_name: str = Field(default="", description="Identified or default analyst name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="All original row columns and values")


def find_column_index(headers: List[str], aliases: Sequence[str]) -> Optional[int]:
    """Find 0-based column index matching any of the candidate aliases."""
    for idx, header in enumerate(headers):
        if not header:
            continue
        cleaned_header = clean_unicode_text(str(header)).lower()
        if cleaned_header in aliases:
            return idx
    # Partial substring match fallback if exact match fails
    for idx, header in enumerate(headers):
        if not header:
            continue
        cleaned_header = clean_unicode_text(str(header)).lower()
        for alias in aliases:
            if alias in cleaned_header:
                return idx
    return None


def load_excel_records(file_path: Path | str) -> List[InputRecord]:
    """
    Ingests an Excel workbook, identifies title and analyst columns via flexible aliases,
    cleans unicode anomalies, and returns a list of InputRecord preserving original row indices.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path.resolve()}")

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    sheet = wb.active
    if sheet is None:
        wb.close()
        raise ValueError(f"No active worksheet found in workbook: {path.name}")

    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        wb.close()
        return []

    headers = [clean_unicode_text(str(col)) if col is not None else "" for col in header_row]

    title_idx = find_column_index(headers, TITLE_ALIASES)
    if title_idx is None:
        wb.close()
        raise ValueError(
            f"Could not locate a title column in {path.name}. Headers detected: {headers}. "
            f"Expected one of aliases: {list(TITLE_ALIASES)}"
        )

    analyst_idx = find_column_index(headers, ANALYST_ALIASES)

    records: List[InputRecord] = []
    # Row 1 was headers; data rows start at row 2
    for row_num, row in enumerate(rows_iter, start=2):
        # Skip completely empty rows
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        raw_title_val = row[title_idx] if title_idx < len(row) else None
        raw_title = clean_unicode_text(str(raw_title_val) if raw_title_val is not None else "")
        if not raw_title:
            # Skip rows where title is empty
            continue

        analyst_val = row[analyst_idx] if analyst_idx is not None and analyst_idx < len(row) else None
        analyst_name = clean_unicode_text(str(analyst_val) if analyst_val is not None else "")

        metadata: Dict[str, Any] = {}
        for col_idx, col_val in enumerate(row):
            col_name = headers[col_idx] if col_idx < len(headers) and headers[col_idx] else f"Column_{col_idx+1}"
            metadata[col_name] = col_val

        records.append(
            InputRecord(
                row_id=row_num,
                raw_title=raw_title,
                normalized_title=normalize_title_for_comparison(raw_title),
                analyst_name=analyst_name,
                metadata=metadata,
            )
        )

    wb.close()
    return records
