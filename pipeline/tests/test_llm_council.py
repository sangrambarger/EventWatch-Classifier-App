"""
Unit and integration tests for Council Debater Engine and LLM Client.
Verifies canonical 48 Event Type enforcement, Ground Transportation Negative Rule,
Council debate prompt construction, and live LLM Council evaluation.
"""

from __future__ import annotations

import pytest

from pipeline.config import CANONICAL_EVENT_TYPES_SET, get_config
from pipeline.council_engine import (
    EventEvaluation,
    build_council_batch_prompt,
    normalize_event_type,
    sanitize_council_evaluation,
)
from pipeline.llm_client import CouncilLLMClient, clean_json_response


def test_ground_transportation_negative_rule():
    """
    CRITICAL TEST: Verify Challenger 2's ground transportation negative rule.
    Prohibited types ('Rail Disruption', 'Highway Disruption', 'Train Derailment', 'Transportation Disruption')
    MUST map to 'Other' (or 'Port Disruption' if at a port), while preserving 'Impactful'.
    """
    # 1. Freight rail derailment -> 'Other'
    norm_type, was_ground = normalize_event_type("Rail Disruption", title="Freight train derails in Ohio carrying chemicals")
    assert norm_type == "Other"
    assert was_ground is True

    # 2. Highway closure -> 'Other'
    norm_type2, was_ground2 = normalize_event_type("Highway Disruption", title="Interstate 80 closed due to blizzard")
    assert norm_type2 == "Other"
    assert was_ground2 is True

    # 3. Train derailment inside port terminal -> 'Port Disruption'
    norm_type3, was_ground3 = normalize_event_type(
        "Train Derailment",
        title="Freight locomotive derails inside Port of Long Beach container terminal",
    )
    assert norm_type3 == "Port Disruption"
    assert was_ground3 is True

    # 4. Transportation disruption -> 'Other'
    norm_type4, was_ground4 = normalize_event_type("Transportation Disruption")
    assert norm_type4 == "Other"
    assert was_ground4 is True

    # 5. Sanitize evaluation preserves 'Impactful' status
    raw_eval = EventEvaluation(
        id=1,
        classification="Not Impactful",  # LLM erroneously called it not impactful
        event_type="Rail Disruption",
        rationale="Freight rail corridor blocked causing cargo component supply delays.",
    )
    sanitized = sanitize_council_evaluation(
        raw_eval,
        title="Norfolk Southern freight train derails on key corridor disrupting auto part supply",
    )
    assert sanitized.event_type == "Other"
    # Freight disruption ensures Impactful preservation
    assert sanitized.classification == "Impactful"


def test_canonical_event_type_normalization():
    """Verify normalization of canonical types and synonyms."""
    # Exact canonical match
    t1, _ = normalize_event_type("Factory Fire")
    assert t1 == "Factory Fire"
    assert t1 in CANONICAL_EVENT_TYPES_SET

    # Case insensitive canonical match
    t2, _ = normalize_event_type("labor disruption")
    assert t2 == "Labor Disruption"

    # Common synonym normalization
    t3, _ = normalize_event_type("M&A")
    assert t3 == "Merger & Acquisition"

    t4, _ = normalize_event_type("blackout")
    assert t4 == "Power Outage"

    # Completely unrecognized type falls back to Other
    t5, _ = normalize_event_type("Alien Invasion")
    assert t5 == "Other"


def test_build_council_batch_prompt():
    """Verify prompt includes Council roles and Ground Transportation Negative Rule."""
    items = [{"id": 1, "title": "Fire at chemical plant"}]
    prompt = build_council_batch_prompt(items)
    assert "False Negative Guardian" in prompt
    assert "False Positive Controller" in prompt
    assert "Executive Council Judge" in prompt
    assert "CRITICAL TAXONOMY NEGATIVE RULE" in prompt
    assert "Do NOT invent 'Rail Disruption'" in prompt


def test_clean_json_response():
    """Verify stripping of markdown delimiters and extra text."""
    raw = '```json\n[{"id": 1, "classification": "Impactful", "event_type": "Factory Fire", "rationale": "Fire at fab"}]\n```'
    cleaned = clean_json_response(raw)
    assert cleaned.startswith("[") and cleaned.endswith("]")


def test_live_council_llm_evaluation():
    """
    Live integration test: Run a batch of 3 test events through CouncilLLMClient
    and verify realistic, compliant outputs adhering to EventWatch Council rules.
    """
    config = get_config()
    if not config.openai_api_key and not config.gemini_api_key:
        pytest.skip("No API keys available for live LLM test.")

    client = CouncilLLMClient(config=config, model_name=config.default_model)

    test_batch = [
        {
            "id": 101,
            "title": "Fire breaks out at Samsung Electronics semiconductor fabrication plant in Giheung",
        },
        {
            "id": 102,
            "title": "30-second voltage sag at TSMC Fab 18 in Tainan trips precision cleanroom tools",
        },
        {
            "id": 103,
            "title": "Union Pacific freight train derails in Nebraska shutting mainline commercial cargo corridor",
        },
    ]

    results = client.evaluate_batch(test_batch)
    assert len(results) == 3

    res_map = {r.id: r for r in results}

    # 1. Samsung fab fire -> Impactful, Factory Fire
    r1 = res_map[101]
    assert r1.classification == "Impactful"
    assert r1.event_type in ("Factory Fire", "Factory Disruption")
    assert len(r1.rationale) > 10

    # 2. TSMC cleanroom sag -> Impactful, Power Outage
    r2 = res_map[102]
    assert r2.classification == "Impactful"
    assert r2.event_type in ("Power Outage", "Factory Disruption")

    # 3. Freight rail derailment -> Impactful, 'Other' (strictly enforcing Ground Transportation Negative Rule!)
    r3 = res_map[103]
    assert r3.classification == "Impactful"
    assert r3.event_type == "Other"
    assert r3.event_type in CANONICAL_EVENT_TYPES_SET
