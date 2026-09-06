"""
Configuration module for EventWatch Impactful Classification Pipeline.
Loads environment variables, canonical taxonomy, and runtime settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set, Tuple

from dotenv import load_dotenv

# Canonical 48 Resilinc Event Types (Strict Taxonomy)
CANONICAL_EVENT_TYPES: Tuple[str, ...] = (
    # Disruption Events (7)
    "Airport Disruption",
    "Port Disruption",
    "Factory Disruption",
    "Power Outage",
    "Supply Shortage",
    "Mail/Postal Disruption",
    "Container Ship Accidents",
    # Natural Hazard Events (9)
    "Earthquake",
    "Flood",
    "Tornado",
    "Volcano",
    "Forest Fire",
    "Hurricane/Typhoon",
    "Hurricane/Typhoon (Pre-Landfall)",
    "Hurricane/Typhoon (Post-Landfall)",
    "Extreme Weather",
    # Industrial Incidents (5)
    "Factory Fire",
    "Chemical Spill",
    "Environmental Hazard",
    "Mine Shutdown",
    "Force Majeure",
    # Social / Political Events (5)
    "Protest/Riot",
    "Labor Disruption",
    "Labor Violation",
    "Geopolitical",
    "Human Health",
    # Cyber & Security Events (2)
    "Cyber Attack",
    "Counterfeit",
    # Financial Events (4)
    "Bankruptcy",
    "Financial Distress",
    "Profit Warning",
    "Price Fluctuation",
    # Regulatory & Legal Events (8)
    "Compliance",
    "FDA/EMA/OSHA Action",
    "Regulatory Change",
    "Legal Action",
    "Bribery/Corruption",
    "Fine",
    "Recall",
    "Airworthiness",
    # Corporate Change Events (7)
    "Merger & Acquisition",
    "Business Sale",
    "Business Spin-off",
    "Company Split",
    "Corporate Restructuring",
    "Leadership Transition",
    "Layoffs",
    # Fallback (1)
    "Other",
)

CANONICAL_EVENT_TYPES_SET: Set[str] = set(CANONICAL_EVENT_TYPES)

# Negative Taxonomy: Prohibited transport categories that must map to 'Other' or 'Port Disruption'
PROHIBITED_TRANSPORT_TYPES: Set[str] = {
    "rail disruption",
    "highway disruption",
    "road disruption",
    "train derailment",
    "transportation disruption",
    "rail accident",
    "train crash",
    "derailment",
    "freight rail disruption",
    "locomotive disruption",
    "bridge disruption",
    "trucking disruption",
}


@dataclass
class PipelineConfig:
    """Runtime configuration settings for the pipeline."""

    workspace_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
    )
    pipeline_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent
    )
    rules_path: Path = field(init=False)
    cache_path: Path = field(init=False)
    output_dir: Path = field(init=False)
    default_input_path: Path = field(init=False)
    default_output_path: Path = field(init=False)

    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    default_model: str = "gpt-4o-mini"
    batch_size: int = 15
    max_retries: int = 5
    timeout_seconds: float = 60.0
    jaccard_threshold: float = 0.75

    def __post_init__(self) -> None:
        # Load .env from home directory and workspace
        home_env = Path.home() / ".env"
        if home_env.is_file():
            load_dotenv(dotenv_path=home_env, override=False)

        workspace_env = self.workspace_root / ".env"
        if workspace_env.is_file():
            load_dotenv(dotenv_path=workspace_env, override=False)

        # In case neither had it or system environment overrides
        load_dotenv(override=False)

        self.openai_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.gemini_api_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY")

        # Preferred model determination:
        # gpt-4o-mini is reliable and verified active
        # gemini-3.6-flash is supported (do NOT use deprecated gemini-2.5-flash)
        if not self.openai_api_key and self.gemini_api_key:
            self.default_model = "gemini-3.6-flash"

        # Rules path resolution: first check pipeline/simplified_rules.txt, then root
        pipeline_rules = self.pipeline_dir / "simplified_rules.txt"
        root_rules = self.workspace_root / "simplified_rules.txt"
        self.rules_path = pipeline_rules if pipeline_rules.is_file() else root_rules

        self.cache_path = self.pipeline_dir / "cache.json"
        self.output_dir = self.workspace_root / "output"
        self.default_input_path = self.workspace_root / "NotImpctful Events.xlsx"
        self.default_output_path = self.output_dir / "classified_events.xlsx"


def get_config(**kwargs) -> PipelineConfig:
    """Factory helper to obtain a PipelineConfig instance with optional overrides."""
    return PipelineConfig(**kwargs)
