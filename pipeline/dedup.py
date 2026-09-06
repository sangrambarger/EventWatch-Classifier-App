"""
Multi-tier deduplication engine for EventWatch pipeline.
Reduces token costs by clustering duplicates while preserving 100% of row mappings.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from pipeline.schema_mapper import InputRecord


# Regex for stripping news feed prefixes (Tier 2)
PREFIX_PATTERN = re.compile(
    r"^(?:(?:update\s*\d*|alert|breaking(?:\s*news)?|urgent|flash|developing|just\s*in|bulletin|exclusive|follow-?up|recap)\s*[:\-\|\–\—]\s*)+",
    re.IGNORECASE,
)

# Strip trailing source wire tags, e.g. " - Reuters", " | Bloomberg"
SOURCE_SUFFIX_PATTERN = re.compile(
    r"\s*[\-\|\–\—]\s*(?:reuters|bloomberg|ap|cnbc|wsj|ft|pr\s*newswire|business\s*wire)\s*$",
    re.IGNORECASE,
)


def strip_update_prefixes(text: str) -> str:
    """Remove news bulletin update prefixes and common wire source suffixes."""
    cleaned = PREFIX_PATTERN.sub("", text).strip()
    cleaned = SOURCE_SUFFIX_PATTERN.sub("", cleaned).strip()
    return cleaned if cleaned else text


def get_character_3grams(text: str) -> Set[str]:
    """Extract character 3-grams from alphanumeric-normalized text for Tier 3 Jaccard comparison."""
    # Lowercase and remove punctuation
    filtered = "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace())
    collapsed = re.sub(r"\s+", " ", filtered).strip()
    if len(collapsed) < 3:
        return {collapsed} if collapsed else set()
    return {collapsed[i : i + 3] for i in range(len(collapsed) - 2)}


def calculate_jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Calculate Jaccard similarity coefficient between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    if union == 0:
        return 0.0
    return intersection / union


@dataclass
class CanonicalItem:
    """Represents a unique canonical event title to be evaluated."""

    canonical_id: int
    representative_row_id: int
    raw_title: str
    normalized_title: str
    prefix_stripped_title: str
    grams: Set[str] = field(default_factory=set)
    member_row_ids: List[int] = field(default_factory=list)


@dataclass
class DeduplicationResult:
    """Result of multi-tier deduplication run."""

    canonical_items: List[CanonicalItem]
    row_to_canonical_id: Dict[int, int]
    total_input_rows: int
    unique_items_count: int

    @property
    def duplicate_count(self) -> int:
        return self.total_input_rows - self.unique_items_count

    @property
    def reduction_percentage(self) -> float:
        if self.total_input_rows == 0:
            return 0.0
        return (self.duplicate_count / self.total_input_rows) * 100.0


class MultiTierDeduplicator:
    """
    Three-tier deduplicator:
      Tier 1: Normalized exact string match
      Tier 2: News prefix & update tag removal match
      Tier 3: Character 3-gram Jaccard / MinHash similarity clustering (threshold >= 0.75)
    """

    def __init__(self, jaccard_threshold: float = 0.75) -> None:
        self.jaccard_threshold = jaccard_threshold

    def deduplicate(self, records: List[InputRecord]) -> DeduplicationResult:
        if not records:
            return DeduplicationResult(
                canonical_items=[],
                row_to_canonical_id={},
                total_input_rows=0,
                unique_items_count=0,
            )

        canonical_items: List[CanonicalItem] = []
        row_to_canonical_id: Dict[int, int] = {}

        # Lookup caches for Tier 1 and Tier 2 fast matching
        tier1_exact_lookup: Dict[str, int] = {}  # normalized_title -> canonical_id
        tier2_prefix_lookup: Dict[str, int] = {}  # prefix_stripped_title -> canonical_id

        for record in records:
            norm_title = record.normalized_title
            stripped_title = strip_update_prefixes(norm_title).strip()

            # --- TIER 1: Exact Normalized Match ---
            if norm_title in tier1_exact_lookup:
                matched_id = tier1_exact_lookup[norm_title]
                canonical_items[matched_id].member_row_ids.append(record.row_id)
                row_to_canonical_id[record.row_id] = matched_id
                continue

            # --- TIER 2: Prefix-Stripped Match ---
            if stripped_title and stripped_title in tier2_prefix_lookup:
                matched_id = tier2_prefix_lookup[stripped_title]
                canonical_items[matched_id].member_row_ids.append(record.row_id)
                row_to_canonical_id[record.row_id] = matched_id
                # Also register this norm_title for future exact hits
                tier1_exact_lookup[norm_title] = matched_id
                continue

            # --- TIER 3: Character 3-gram Jaccard Similarity ---
            record_grams = get_character_3grams(stripped_title or norm_title)
            matched_id = None
            best_sim = 0.0

            for canon in canonical_items:
                # Length filter heuristic: If lengths differ wildly, Jaccard cannot reach 0.75
                len_a = len(stripped_title)
                len_b = len(canon.prefix_stripped_title)
                if max(len_a, len_b) > 0 and (abs(len_a - len_b) / max(len_a, len_b)) > 0.40:
                    continue

                sim = calculate_jaccard_similarity(record_grams, canon.grams)
                if sim >= self.jaccard_threshold and sim > best_sim:
                    best_sim = sim
                    matched_id = canon.canonical_id

            if matched_id is not None:
                canonical_items[matched_id].member_row_ids.append(record.row_id)
                row_to_canonical_id[record.row_id] = matched_id
                tier1_exact_lookup[norm_title] = matched_id
                if stripped_title:
                    tier2_prefix_lookup[stripped_title] = matched_id
                continue

            # --- NEW CANONICAL ITEM CREATION ---
            new_id = len(canonical_items)
            new_item = CanonicalItem(
                canonical_id=new_id,
                representative_row_id=record.row_id,
                raw_title=record.raw_title,
                normalized_title=norm_title,
                prefix_stripped_title=stripped_title,
                grams=record_grams,
                member_row_ids=[record.row_id],
            )
            canonical_items.append(new_item)
            row_to_canonical_id[record.row_id] = new_id
            tier1_exact_lookup[norm_title] = new_id
            if stripped_title:
                tier2_prefix_lookup[stripped_title] = new_id

        return DeduplicationResult(
            canonical_items=canonical_items,
            row_to_canonical_id=row_to_canonical_id,
            total_input_rows=len(records),
            unique_items_count=len(canonical_items),
        )
