"""
EventWatch Council Multi-Role Debater Engine.
Implements the three-role council debate architecture (False Negative Guardian,
False Positive Controller, Executive Council Judge) and enforces canonical taxonomy normalization.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from pipeline.config import (
    CANONICAL_EVENT_TYPES,
    CANONICAL_EVENT_TYPES_SET,
    PROHIBITED_TRANSPORT_TYPES,
)


class CouncilDebate(BaseModel):
    """Arguments from the internal multi-role debate."""

    false_negative_guardian: str = Field(
        default="",
        description="Assessment of mapped partners, zero-hour exceptions, and supply chain threat potential",
    )
    false_positive_controller: str = Field(
        default="",
        description="Assessment of whether event is non-disruptive, already over, or bad article noise",
    )
    executive_council_judge: str = Field(
        default="",
        description="Authoritative synthesis reconciling the Guardian and Controller arguments",
    )


class EventEvaluation(BaseModel):
    """Standardized output evaluation for a single event."""

    id: int = Field(description="Unique item identifier matching the batch input id")
    classification: str = Field(
        description="Binary operational impact classification"
    )
    event_type: str = Field(
        description="Canonical Resilinc event type (strictly one of the 48 types)"
    )
    rationale: str = Field(
        description="Concise 1-2 sentence evidence-based rationale"
    )
    council_debate: Optional[CouncilDebate] = Field(
        default=None,
        description="Optional internal debate synthesis",
    )


class BatchEvaluationResponse(BaseModel):
    """Batch evaluation container returned by LLM."""

    evaluations: List[EventEvaluation] = Field(default_factory=list)


# Mapping of common synonyms or non-canonical variations to canonical 48 types
COMMON_TYPE_SYNONYMS: Dict[str, str] = {
    "m&a": "Merger & Acquisition",
    "merger and acquisition": "Merger & Acquisition",
    "mergers & acquisitions": "Merger & Acquisition",
    "acquisitions": "Merger & Acquisition",
    "spinoff": "Business Spin-off",
    "spin-off": "Business Spin-off",
    "restructuring": "Corporate Restructuring",
    "workplace accident": "Factory Disruption",
    "plant fire": "Factory Fire",
    "fire": "Factory Fire",
    "spill": "Chemical Spill",
    "toxic spill": "Chemical Spill",
    "strike": "Labor Disruption",
    "walkout": "Labor Disruption",
    "blackout": "Power Outage",
    "outage": "Power Outage",
    "typhoon": "Hurricane/Typhoon",
    "hurricane": "Hurricane/Typhoon",
    "storm": "Extreme Weather",
    "winter storm": "Extreme Weather",
    "blizzard": "Extreme Weather",
    "fda warning": "FDA/EMA/OSHA Action",
    "osha violation": "FDA/EMA/OSHA Action",
    "regulatory fine": "Fine",
    "lawsuit": "Legal Action",
    "litigation": "Legal Action",
    "bankruptcy filing": "Bankruptcy",
    "chapter 11": "Bankruptcy",
    "port congestion": "Port Disruption",
    "port strike": "Labor Disruption",
    "terminal closure": "Port Disruption",
    "cyberattack": "Cyber Attack",
    "ransomware": "Cyber Attack",
    "shortage": "Supply Shortage",
    "component shortage": "Supply Shortage",
    "leadership change": "Leadership Transition",
    "ceo resignation": "Leadership Transition",
    "executive transition": "Leadership Transition",
    "civil unrest": "Protest/Riot",
}


def normalize_event_type(raw_type: str, title: str = "", rationale: str = "") -> Tuple[str, bool]:
    """
    Normalizes a proposed event type to one of the 48 canonical Resilinc types.
    Strictly enforces Challenger 2's Ground Transportation Negative Rule:
    - Rejects 'Rail Disruption', 'Highway Disruption', 'Road Disruption', 'Train Derailment', etc.
    - Classifies freight rail, locomotive, highway, bridge, and trucking disruptions strictly
      as 'Other' (or 'Port Disruption' if occurring within a maritime port terminal).
    Returns (canonical_type, was_ground_transport_reclassified).
    """
    cleaned = raw_type.strip()
    cleaned_lower = cleaned.lower()

    # Exact canonical match
    if cleaned in CANONICAL_EVENT_TYPES_SET:
        # Check if accidentally matched a prohibited type (none in canonical set, but check lower)
        return cleaned, False

    # Check case-insensitive match against canonical set
    for canon in CANONICAL_EVENT_TYPES:
        if canon.lower() == cleaned_lower:
            return canon, False

    # CRITICAL GROUND TRANSPORTATION NEGATIVE RULE ENFORCEMENT:
    # Do NOT invent 'Rail Disruption', 'Highway Disruption', 'Road Disruption',
    # 'Train Derailment', or 'Transportation Disruption'.
    is_ground_transport = (
        cleaned_lower in PROHIBITED_TRANSPORT_TYPES
        or any(pt in cleaned_lower for pt in ("rail", "train", "highway", "derailment", "trucking", "transportation"))
    )

    if is_ground_transport:
        context_text = f"{title} {rationale}".lower()
        if "port" in context_text or "harbor" in context_text or "terminal" in context_text:
            return "Port Disruption", True
        return "Other", True

    # Check common synonyms
    if cleaned_lower in COMMON_TYPE_SYNONYMS:
        return COMMON_TYPE_SYNONYMS[cleaned_lower], False

    # Fallback to 'Other'
    return "Other", False


def sanitize_council_evaluation(evaluation: EventEvaluation, title: str = "") -> EventEvaluation:
    """
    Sanitizes and normalizes an evaluation returned by the LLM:
    - Enforces binary classification ('Impactful' or 'Not Impactful')
    - Enforces canonical 48 Event Types and Ground Transport Negative Rule
    - Preserves 'Impactful' status when reclassifying ground transport disruptions
    """
    raw_class = evaluation.classification.strip()
    norm_class: Literal["Impactful", "Not Impactful"] = (
        "Impactful" if "impactful" in raw_class.lower() and "not" not in raw_class.lower() else "Not Impactful"
    )

    canonical_type, was_ground_transport = normalize_event_type(
        evaluation.event_type,
        title=title,
        rationale=evaluation.rationale,
    )

    # If reclassified from ground transport disruption, ensure Impactful is preserved if commercial impact exists
    if was_ground_transport and norm_class == "Not Impactful":
        title_lower = title.lower()
        if any(term in title_lower for term in ("freight", "cargo", "supply", "component", "commercial", "chemical", "grain")):
            norm_class = "Impactful"

    return EventEvaluation(
        id=evaluation.id,
        classification=norm_class,
        event_type=canonical_type,
        rationale=evaluation.rationale.strip(),
        council_debate=evaluation.council_debate,
    )


def build_council_batch_prompt(items: List[Dict[str, Any]]) -> str:
    """Constructs user prompt for batch LLM evaluation."""
    items_json = [
        {"id": item["id"], "title": item["title"]}
        for item in items
    ]
    prompt = (
        "Execute the EventWatch Council Multi-Role Debater protocol for the following event items.\n"
        "For EACH item, internally weigh:\n"
        "1. False Negative Guardian: Mapped partners, Tier-1 industrial giants, zero-hour factory fires (PA-007/008), cleanroom power sags.\n"
        "2. False Positive Controller: Non-events, 14 Bad Article Taxonomy categories, events already over with zero downtime.\n"
        "3. Executive Council Judge: Synthesis into single binary verdict ('Impactful' vs 'Not Impactful'), canonical 48 Event Type, and 1-2 sentence evidence-based Rationale.\n\n"
        "CRITICAL TAXONOMY NEGATIVE RULE: Do NOT invent 'Rail Disruption', 'Highway Disruption', 'Road Disruption', 'Train Derailment', or 'Transportation Disruption'. "
        "Classify all freight rail, locomotive, highway, bridge, and commercial trucking corridor disruptions strictly as 'Other' (or 'Port Disruption' if inside a port terminal), "
        "while preserving 'Impactful' if commercial freight or component supply is disrupted.\n\n"
        "Respond ONLY with a valid JSON array of objects with the following structure:\n"
        "[\n"
        "  {\n"
        '    "id": <int matching item id>,\n'
        '    "classification": "Impactful" | "Not Impactful",\n'
        '    "event_type": "<Canonical Resilinc Event Type>",\n'
        '    "rationale": "<Concise 1-2 sentence evidence-based rationale>"\n'
        "  }\n"
        "]\n\n"
        f"Input Items:\n{items_json}"
    )
    return prompt
