import json
import logging
import openai
from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Any

from pipeline.config import PipelineConfig

logger = logging.getLogger(__name__)

class BouncerVerdict(BaseModel):
    id: int = Field(description="Unique item identifier matching the batch input id")
    verdict: Literal["PASS", "DROP"] = Field(description="PASS if industrial/commercial supply chain event, DROP if semantic noise")

class BouncerBatchResponse(BaseModel):
    evaluations: List[BouncerVerdict]

class AIBouncer:
    def __init__(self, config: PipelineConfig, model_name: str = "gpt-4o-mini"):
        self.config = config
        self.model_name = model_name
        self.client = openai.OpenAI(api_key=config.openai_api_key)

    def evaluate_batch(self, batch_input: List[Dict[str, Any]]) -> Dict[int, str]:
        prompt = self._build_prompt(batch_input)
        try:
            response = self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a Supply Chain News Triage Engine. Your ONLY job is to filter out semantic noise. Output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format=BouncerBatchResponse,
                temperature=0.0
            )
            result = response.choices[0].message.parsed
            return {item.id: item.verdict for item in result.evaluations}
        except Exception as e:
            logger.error(f"AI Bouncer failed on batch: {e}")
            return {item["id"]: "PASS" for item in batch_input}
            
    def _build_prompt(self, batch_input: List[Dict[str, Any]]) -> str:
        instructions = """
You are the AI Bouncer for the EventWatch Supply Chain Risk pipeline.
I will give you a list of news headlines. For each headline, you must decide whether to PASS or DROP it based on its relevance to global industrial/commercial supply chains.

## DROP (Semantic Noise)
If the event is strictly regarding:
- Civilian accidents / local crime (e.g., PG hostel collapse, residential fire, car crash, stabbing)
- Consumer product safety / retail items (e.g., Children's book recall, dog food recall, supermarket sweep)
- Local entertainment / sports / fashion (e.g., Fashion Week, movie release, local theatre)
- Retail/Restaurant accidents (e.g., cake shop fire, bakery fire, local market fire)
- Clickbait, giveaways, generic questions (e.g., "Would you lie to get a birthday freebie?")
- Minor web portal artifacts / software glitches that do not affect major services (e.g., "My Juta Login")
- Routine bureaucratic corporate spam (e.g., "September 2026 Vietnam company deregistration related service information")

## PASS (Supply Chain / Industrial / Commercial)
If the event involves:
- Manufacturing, factories, chemical plants, semiconductor fabs
- Logistics, ports, cargo planes, container shipping, railways
- Major mergers & acquisitions (M&A) or bankruptcies involving industrial/tech/telecom companies
- Extreme weather, hurricanes, earthquakes affecting industrial regions. (MANDATORY: Hurricanes/Typhoons must PASS even if they "remain offshore" or are just forming).
- Border closures or checkpoint shutdowns. (MANDATORY: Border closures must PASS even if caused by immigration, individuals, or suspects, because they block freight).
- Cybersecurity breaches, major regulatory actions, massive financial distress
- IF YOU ARE UNSURE OR AMBIGUOUS, YOU MUST DEFAULT TO PASS. (High Recall Policy)

## Input Headlines
"""
        for item in batch_input:
            instructions += f'[{item["id"]}] {item["title"]}\n'
        return instructions
