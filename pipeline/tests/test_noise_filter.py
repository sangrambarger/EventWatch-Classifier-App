"""
Unit tests for fast-gate heuristic noise filter in noise_filter.py.
Verifies pre-LLM zero-token classification of Bad Article Taxonomy and industrial keyword safety guards.
"""

from __future__ import annotations

from pipeline.noise_filter import FastGateNoiseFilter


def test_law_firm_advertisements():
    """Verify law firm ads and securities class action solicitations are caught."""
    filter = FastGateNoiseFilter()

    v1 = filter.evaluate("Rosen Law Firm Announces Investigation of Securities Claims Against Super Micro Computer")
    assert v1.is_noise is True
    assert v1.category == "law_firm_advertisement"
    assert v1.classification == "Not Impactful"
    assert v1.event_type == "Legal Action"
    assert "securities litigation solicitation" in v1.rationale

    v2 = filter.evaluate("Robbins Geller Reminds Investors of Lead Plaintiff Deadline in Class Action Lawsuit")
    assert v2.is_noise is True
    assert v2.classification == "Not Impactful"

    v3 = filter.evaluate("SHAREHOLDER ALERT: Pomerantz Law Firm Investigates Claims on Behalf of Investors")
    assert v3.is_noise is True


def test_sports_and_celebrity_stories():
    """Verify sports matches and celebrity news are filtered."""
    filter = FastGateNoiseFilter()

    v1 = filter.evaluate("Premier League: Manchester City defeats Arsenal 3-1 in title clash")
    assert v1.is_noise is True
    assert v1.category == "sports_story"
    assert v1.classification == "Not Impactful"
    assert v1.event_type == "Other"

    v2 = filter.evaluate("Hollywood actress breaks silence after red carpet appearance at Met Gala")
    assert v2.is_noise is True
    assert v2.category == "celebrity_story"
    assert v2.classification == "Not Impactful"


def test_civilian_domestic_incidents():
    """Verify civilian house fires and passenger car crashes are filtered."""
    filter = FastGateNoiseFilter()

    v1 = filter.evaluate("Residential duplex fire on Elm Street displaces family of four in Peoria")
    assert v1.is_noise is True
    assert v1.category == "civilian_incident_only"
    assert v1.classification == "Not Impactful"
    assert v1.event_type == "Other"

    v2 = filter.evaluate("Two-car crash on Main Street causes temporary traffic backup")
    assert v2.is_noise is True
    assert v2.classification == "Not Impactful"


def test_historical_and_promotional_pr():
    """Verify historical retrospectives and workplace awards are filtered."""
    filter = FastGateNoiseFilter()

    v1 = filter.evaluate("10 years ago today: Remembering the devastating Joplin tornado of 2011")
    assert v1.is_noise is True
    assert v1.category == "historical_recap"

    v2 = filter.evaluate("Acme Corp recognized as a Best Place to Work 2026")
    assert v2.is_noise is True
    assert v2.category == "promotional_pr"

    v3 = filter.evaluate("Board declares regular quarterly cash dividend of $0.50 per share")
    assert v3.is_noise is True
    assert v3.category == "no_disruption_signal"


def test_critical_industrial_keywords_guard():
    """Verify that industrial disruptions bypass the noise filter and proceed to LLM."""
    filter = FastGateNoiseFilter()

    # Even if title mentions "fire", if it is a semiconductor fab or chemical plant, guard prevents noise filter
    v1 = filter.evaluate("Fire extinguished at Samsung Semiconductor cleanroom in Hwaseong")
    assert v1.is_noise is False

    v2 = filter.evaluate("Dockworkers strike at Port of Los Angeles container terminal")
    assert v2.is_noise is False

    v3 = filter.evaluate("Explosion at BASF chemical plant in Ludwigshafen")
    assert v3.is_noise is False

    v4 = filter.evaluate("Force majeure declared on ethylene supply following refinery outage")
    assert v4.is_noise is False
