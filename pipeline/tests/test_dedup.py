"""
Unit tests for multi-tier deduplication engine in dedup.py.
Verifies Tier 1 (exact), Tier 2 (prefix-stripped), and Tier 3 (3-gram Jaccard) clustering.
"""

from __future__ import annotations

from pipeline.dedup import (
    MultiTierDeduplicator,
    calculate_jaccard_similarity,
    get_character_3grams,
    strip_update_prefixes,
)
from pipeline.schema_mapper import InputRecord


def test_strip_update_prefixes():
    """Verify stripping of various news prefixes and source suffixes."""
    assert strip_update_prefixes("UPDATE 2: Fire at plant") == "Fire at plant"
    assert strip_update_prefixes("ALERT - Port of Antwerp closed") == "Port of Antwerp closed"
    assert strip_update_prefixes("Breaking News: Strike in Rotterdam - Reuters") == "Strike in Rotterdam"
    assert strip_update_prefixes("Normal news title without prefixes") == "Normal news title without prefixes"


def test_character_3grams_and_jaccard():
    """Verify 3-gram set generation and Jaccard similarity calculation."""
    text1 = "Explosion at chemical plant in Ludwigshafen"
    text2 = "Explosion at chemical plant in Ludwigshafen Germany"
    grams1 = get_character_3grams(text1)
    grams2 = get_character_3grams(text2)

    sim = calculate_jaccard_similarity(grams1, grams2)
    assert sim >= 0.75  # Very similar strings

    text3 = "Basketball tournament results"
    grams3 = get_character_3grams(text3)
    sim_unrelated = calculate_jaccard_similarity(grams1, grams3)
    assert sim_unrelated < 0.20


def test_multitier_deduplicator():
    """Verify complete clustering across all three tiers."""
    records = [
        # Cluster 1: Tier 1 exact match after normalization
        InputRecord(row_id=2, raw_title="Strike at Port of Hamburg", normalized_title="strike at port of hamburg", analyst_name="Analyst A"),
        InputRecord(row_id=3, raw_title="  Strike at Port of Hamburg  ", normalized_title="strike at port of hamburg", analyst_name="Analyst B"),
        # Cluster 1: Tier 2 prefix match
        InputRecord(row_id=4, raw_title="UPDATE 1: Strike at Port of Hamburg", normalized_title="update 1: strike at port of hamburg", analyst_name="Analyst C"),
        InputRecord(row_id=5, raw_title="ALERT: Strike at Port of Hamburg - Reuters", normalized_title="alert: strike at port of hamburg - reuters", analyst_name="Analyst D"),
        # Cluster 2: Distinct event
        InputRecord(row_id=6, raw_title="Fire at Samsung Semiconductor fab in Giheung", normalized_title="fire at samsung semiconductor fab in giheung", analyst_name="Analyst E"),
        # Cluster 2: Tier 3 near-duplicate (Jaccard >= 0.75)
        InputRecord(row_id=7, raw_title="Fire at Samsung Semiconductor fab in Giheung plant", normalized_title="fire at samsung semiconductor fab in giheung plant", analyst_name="Analyst F"),
        # Cluster 3: Completely distinct event
        InputRecord(row_id=8, raw_title="TSMC reports quarterly revenue increase", normalized_title="tsmc reports quarterly revenue increase", analyst_name="Analyst G"),
    ]

    dedup = MultiTierDeduplicator(jaccard_threshold=0.75)
    result = dedup.deduplicate(records)

    assert result.total_input_rows == 7
    # Should reduce to 3 unique canonical clusters
    assert result.unique_items_count == 3
    assert result.duplicate_count == 4
    assert result.reduction_percentage > 50.0

    # Verify cluster 1 has rows 2, 3, 4, 5
    canon_0 = result.canonical_items[0]
    assert 2 in canon_0.member_row_ids
    assert 3 in canon_0.member_row_ids
    assert 4 in canon_0.member_row_ids
    assert 5 in canon_0.member_row_ids

    # Verify row mapping consistency
    assert result.row_to_canonical_id[2] == 0
    assert result.row_to_canonical_id[3] == 0
    assert result.row_to_canonical_id[4] == 0
    assert result.row_to_canonical_id[5] == 0


def test_empty_deduplication():
    """Verify handling of empty list."""
    dedup = MultiTierDeduplicator()
    res = dedup.deduplicate([])
    assert res.total_input_rows == 0
    assert res.unique_items_count == 0
    assert len(res.canonical_items) == 0
