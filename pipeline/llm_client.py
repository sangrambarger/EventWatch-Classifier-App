"""
LLM Client for EventWatch Pipeline.
Supports OpenAI (gpt-4o-mini) and Google Gemini (gemini-3.6-flash) with
Pydantic schema validation, exponential backoff retries via Tenacity, and Council Debater prompts.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pipeline.config import PipelineConfig
from pipeline.council_engine import (
    EventEvaluation,
    build_council_batch_prompt,
    sanitize_council_evaluation,
)

logger = logging.getLogger(__name__)


def clean_json_response(raw_text: str) -> str:
    """Extract and clean raw JSON array from LLM response text."""
    text = raw_text.strip()
    # Strip markdown code blocks ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # If surrounded by text, find first [ and last ]
    start_bracket = text.find("[")
    end_bracket = text.rfind("]")
    if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
        text = text[start_bracket : end_bracket + 1]

    return text


class CouncilLLMClient:
    """Enterprise LLM Client executing EventWatch Council Multi-Role Debater evaluations."""

    def __init__(
        self,
        config: PipelineConfig,
        model_name: Optional[str] = None,
    ) -> None:
        self.config = config
        self.model_name = model_name or config.default_model

        # Load system rules prompt
        if not self.config.rules_path.is_file():
            raise FileNotFoundError(
                f"Rules file not found at: {self.config.rules_path.resolve()}"
            )
        self.system_prompt = self.config.rules_path.read_text(encoding="utf-8")

        # Initialize appropriate SDK client
        self.is_openai = "gpt" in self.model_name.lower() or "o1" in self.model_name.lower() or "o3" in self.model_name.lower()

        if self.is_openai:
            if not self.config.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required for OpenAI models.")
            self.openai_client = openai.OpenAI(
                api_key=self.config.openai_api_key,
                timeout=self.config.timeout_seconds,
            )
            self.gemini_client = None
        else:
            if not self.config.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required for Gemini models.")
            import google.genai as genai

            self.gemini_client = genai.Client(api_key=self.config.gemini_api_key)
            self.openai_client = None

    @retry(
        retry=retry_if_exception_type((Exception,)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        reraise=True,
    )
    def _call_model_raw(self, user_prompt: str) -> str:
        """Call underlying LLM provider with retry logic."""
        if self.is_openai:
            assert self.openai_client is not None
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        else:
            assert self.gemini_client is not None
            # For Gemini, system instructions are passed via config or combined prompt
            full_prompt = f"SYSTEM INSTRUCTIONS:\n{self.system_prompt}\n\nUSER REQUEST:\n{user_prompt}"
            response = self.gemini_client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
            )
            content = response.text or ""
            return content.strip()

    def evaluate_batch(self, items: List[Dict[str, Any]]) -> List[EventEvaluation]:
        """
        Evaluates a batch of event items using Council Multi-Role Debater protocol.
        Input items format: [{'id': int, 'title': str}]
        """
        if not items:
            return []

        user_prompt = build_council_batch_prompt(items)
        raw_output = self._call_model_raw(user_prompt)

        clean_json = clean_json_response(raw_output)
        try:
            parsed = json.loads(clean_json)
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode JSON from LLM response: %s\nRaw output: %s", exc, raw_output)
            raise ValueError(f"LLM did not return valid JSON: {exc}") from exc

        if not isinstance(parsed, list):
            if isinstance(parsed, dict) and "evaluations" in parsed:
                parsed = parsed["evaluations"]
            elif isinstance(parsed, dict) and "id" in parsed:
                parsed = [parsed]
            else:
                raise ValueError(f"Expected JSON array of evaluations, got: {type(parsed)}")

        # Build mapping of input id -> title for contextual normalization
        id_to_title = {item["id"]: item["title"] for item in items}

        results: List[EventEvaluation] = []
        for item_dict in parsed:
            item_id = item_dict.get("id")
            title = id_to_title.get(item_id, "")
            eval_obj = EventEvaluation(
                id=item_id,
                classification=item_dict.get("classification", "Not Impactful"),
                event_type=item_dict.get("event_type", "Other"),
                rationale=item_dict.get("rationale", ""),
                council_debate=item_dict.get("council_debate"),
            )
            sanitized = sanitize_council_evaluation(eval_obj, title=title)
            results.append(sanitized)

        return results
