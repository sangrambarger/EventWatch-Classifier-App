"""
Fast-Gate Heuristic Noise Filter for EventWatch Pipeline.
Pre-LLM regex gate implementing the 14 Bad Article Taxonomy categories.
Achieves zero-token instant classification for unambiguous non-events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class NoiseFilterVerdict:
    """Verdict returned by the fast-gate noise filter."""

    is_noise: bool
    category: Optional[str] = None
    classification: str = "Not Impactful"
    event_type: str = "Other"
    rationale: str = ""


# High-priority industrial keywords: If ANY of these appear, NEVER filter via fast-gate;
# always defer to the LLM Council Debater to protect against false negatives.
CRITICAL_INDUSTRIAL_KEYWORDS = re.compile(
    r"\b(?:semiconductor|wafer|cleanroom|lithography|fab\b|refinery|chemical\s*plant|"
    r"manufacturing\s*plant|industrial\s*park|port\s*(?:of|terminal)|container\s*ship|"
    r"freight\s*rail|force\s*majeure|strike|walkout|hazmat|toxic\s*leak|substation\s*fire|"
    r"cyber\s*attack|ransomware|fda|recalled|bankruptcy|chapter\s*11|copyright|patent|"
    r"infringement|intellectual\s*property|trademark)\b",
    re.IGNORECASE,
)

# 1. Law Firm Announcements & Shareholder Solicitations
LAW_FIRM_PATTERNS = re.compile(
    r"(?:"
    r"(?:rosen|robbins\s*geller|pomerantz|bronstein[,\s]+gewirtz|schall|kuehn|levi\s*&\s*korsinsky|"
    r"glancy\s*prongay|faruqi\s*&\s*faruqi|block\s*&\s*leviton|bernstein\s*liebhard|bragar\s*eagel|"
    r"kessler\s*topaz|hagens\s*berman|frank\s*r\.?\s*cruz|howard\s*g\.?\s*smith|gibbs|scott\+scott|"
    r"vincent\s*wong|johnson\s*fistel|gainey\s*mckenna|the\s*gross\s*law\s*firm)\s*(?:law|llp|p\.?c\.?|attorneys)?"
    r"|announces\s*(?:investigation\s*of|class\s*action|shareholder\s*class\s*action|lead\s*plaintiff)"
    r"|reminds\s*investors\s*(?:of|about|regarding)?\s*(?:the\s*)?(?:class\s*action|lead\s*plaintiff|deadline)"
    r"|shareholder\s*(?:alert|notice|class\s*action\s*lawsuit)"
    r"|securities\s*(?:fraud|class\s*action)\s*(?:investigation|lawsuit|litigation)"
    r"|lead\s*plaintiff\s*deadline"
    r"|did\s*you\s*(?:lose\s*money|suffer\s*a\s*loss)\s*(?:in|with|investing)"
    r"|investors\s*with\s*(?:substantial\s*)?losses"
    r"|class\s*action\s*lawsuit\s*has\s*been\s*filed\s*against"
    r")",
    re.IGNORECASE,
)

# 2. Sports Stories
SPORTS_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:premier\s*league|champions\s*league|la\s*liga|bundesliga|serie\s*a|uefa|fifa)\b"
    r"|\b(?:nfl|nba|mlb|nhl|mls|ncaa|wnba|nascar|formula\s*1|f1|pga\s*tour)\b"
    r"|\b(?:quarterback|touchdown|halftime|hat-?trick|penalty\s*shootout|slam\s*dunk|home\s*run)\b"
    r"|\b(?:head\s*coach\s*(?:fired|hired|resigns)|player\s*(?:trade|transfers|signs\s*contract))\b"
    r"|\b(?:world\s*cup|super\s*bowl|world\s*series|stanley\s*cup|olympic\s*games|olympics)\b"
    r"|vs\.?\s*.*(?:highlights|score|final\s*score)"
    r")",
    re.IGNORECASE,
)

# 3. Entertainment & Celebrity News
CELEBRITY_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:hollywood|red\s*carpet|box\s*office|movie\s*trailer|film\s*premiere|album\s*release)\b"
    r"|\b(?:grammy|oscar|emmy|golden\s*globe|tony\s*awards|billboard\s*music\s*award)\b"
    r"|\b(?:kardashian|jenner|taylor\s*swift|beyonce|prince\s*harry|meghan\s*markle|royal\s*family)\b"
    r"|\b(?:dating|divorce|breaks\s*silence|spotted\s*together|baby\s*bump|reality\s*star)\b"
    r")",
    re.IGNORECASE,
)

# 4. Civilian Incidents (Domestic home fires, non-commercial passenger car crashes, local crimes)
CIVILIAN_PATTERNS = re.compile(
    r"(?:"
    r"(?:residential|house|duplex|apartment|mobile\s*home|single-family\s*home)\s*fire\b"
    r"|fire\s*(?:at\s*(?:a\s*)?)?(?:residential\s*home|apartment\s*building|duplex|single-family\s*home)"
    r"|fire\s*displaces\s*(?:\d+|family|residents)\s*(?:in|on|after)"
    r"|\b(?:two-car|passenger\s*car|sedan|suv|motorcycle)\s*crash\b"
    r"|\b(?:fatal\s*hit-and-run|pedestrian\s*struck\s*by\s*vehicle)\b"
    r"|\b(?:armed\s*robbery|convenience\s*store\s*robbery|burglary\s*suspect|domestic\s*dispute)\b"
    r")",
    re.IGNORECASE,
)

# 5. Historical Retrospectives & Memorials
HISTORICAL_PATTERNS = re.compile(
    r"(?:"
    r"^\d+\s*years\s*ago\s*(?:today|this\s*week)?"
    r"|\banniversary\s*of\s*(?:the\s*)?(?:hurricane|earthquake|disaster|tragedy|flood)"
    r"|\bremembering\s*(?:the\s*)?(?:deadly|tragic|victims\s*of|\d{4})"
    r"|\bdecades\s*after\s*(?:the\s*)?(?:tragedy|disaster)"
    r"|^retrospective\s*:"
    r")",
    re.IGNORECASE,
)

# 6. Generic Promotional PR / Workplace Awards
PROMOTIONAL_PR_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:named|recognized\s*as)\s*(?:a\s*)?(?:best|top)\s*place\s*to\s*work\b"
    r"|\bwins?\s*(?:\d{4}\s*)?(?:customer\s*choice|best-in-class|workplace|great\s*place\s*to\s*work)\s*award\b"
    r"|\bcelebrates?\s*\d+\s*(?:years|anniversary)\s*of\s*(?:excellence|innovation|success)\b"
    r"|\bannounces?\s*(?:official\s*)?(?:partnership\s*with|sponsorship\s*of)\s*(?:football|basketball|soccer|sports|festival)"
    r"|\bunveils?\s*new\s*(?:marketing|brand|lifestyle|ad)\s*campaign\b"
    r")",
    re.IGNORECASE,
)

# 7. Generic Explainers / Tutorials
EXPLAINER_PATTERNS = re.compile(
    r"(?:"
    r"^(?:what\s*is|what\s*are|how\s*does|how\s*to|why\s*do|why\s*is)\b.*"
    r"|^(?:a\s*beginner'?s\s*guide\s*to|everything\s*you\s*need\s*to\s*know\s*about|the\s*ultimate\s*guide\s*to)\b"
    r"|^explainer\s*:"
    r"|.*\bhow\s*to\s*prepare\b.*"
    r")",
    re.IGNORECASE,
)

# 8. Opinion Pieces
OPINION_PATTERNS = re.compile(
    r"^(?:op-?ed|opinion|editorial|our\s*view|guest\s*column|commentary)\s*[:\-\|\–\—]",
    re.IGNORECASE,
)

# 8b. Minor Crime & Routine Police Reports
CRIME_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:stabbing|shooting|robbery|burglary|theft|assault|murder|homicide|domestic\s*violence|child\s*abuse|kidnapping|suspect\s*arrested)\b"
    r")",
    re.IGNORECASE,
)

# 9. Routine Cash Dividends (No operational or financial distress signal)
ROUTINE_DIVIDEND_PATTERNS = re.compile(
    r"(?:"
    r"\bdeclares?\s*(?:regular\s*)?(?:quarterly|monthly|annual)\s*(?:cash\s*)?dividend\b"
    r"|\bannounces?\s*(?:regular\s*)?(?:quarterly|monthly)\s*(?:cash\s*)?dividend\b"
    r"|\bboard\s*declares?\s*quarterly\s*dividend\b"
    r")",
    re.IGNORECASE,
)

# 10. Unrelated noise (e.g., local municipality news, pure consumer product reviews, random scraping artifacts)
UNRELATED_NOISE_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:wfaa|local\s*school\s*board|city\s*council|town\s*hall|county\s*commission|school\s*board\s*(?:approves|votes|meets)|city\s*council\s*approves\s*(?:park|playground|rezoning))\b"
    r"|\b(?:movie\s*review|restaurant\s*review|album\s*review|video\s*game\s*review|zoo\s*welcomes\s*baby|aquarium\s*announces\s*birth)\b"
    r"|\b(?:astrology|horoscope|celebrity\s*gossip|red\s*carpet|lottery\s*winner|winning\s*powerball\s*ticket|daily\s*tarot)\b"
    r")",
    re.IGNORECASE,
)

# 11. Consumer Electronics Deals/Rumors
CONSUMER_TECH_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:best\s*deals\s*on|iphone\s*1\d|galaxy\s*s\d+|pixel\s*\d+|apple\s*watch\s*series|black\s*friday\s*deals|cyber\s*monday)\b"
    r"|\b(?:rumored\s*specs|leaked\s*renders|unboxing)\b"
    r")",
    re.IGNORECASE,
)

# 12. Local Entertainment / Events
ENTERTAINMENT_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:film\s*festival|concert\s*tour|art\s*exhibition|theatre\s*production|movie\s*premiere|box\s*office|comic\s*con|arcade|music\s*festival)\b"
    r")",
    re.IGNORECASE,
)

# 13. Hospitality
HOSPITALITY_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:hotel|motel|resort|restaurant|cafe|bar|pub|nightclub|eatery)\b"
    r")",
    re.IGNORECASE,
)

# 14. Residential Real Estate
REAL_ESTATE_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:apartment\s*complex|condo|housing\s*development|residential|real\s*estate\s*listing|homebuyers?)\b"
    r")",
    re.IGNORECASE,
)

# 15. Web Portal & Scraping Artifacts
WEB_PORTAL_PATTERNS = re.compile(
    r"^(?:"
    r".*\b(?:login|sign\s*in|my\s*account|subscribe\s*now|create\s*account|forgot\s*password|welcome\s*to|request\s*could\s*not\s*be\s*satisfied|access\s*denied|404\s*not\s*found|messages\s*in\s*quarantine)\b.*"
    r"|^email:\s*.*"
    r")$",
    re.IGNORECASE,
)

# 16. Clickbait, Questions & Giveaways
CLICKBAIT_PATTERNS = re.compile(
    r"^(?:"
    r".*\b(?:would\s*you|are\s*you|can\s*you|should\s*you)\s+.*\?"
    r"|.*\b(?:freebie|giveaway|sweepstakes|win\s*a\s*free|quiz|test\s*your\s*knowledge)\b.*"
    r")$",
    re.IGNORECASE,
)

class FastGateNoiseFilter:
    """Pre-LLM fast heuristic regex filter for Bad Article Taxonomy."""

    def evaluate(self, title: str) -> NoiseFilterVerdict:
        if not title or not title.strip():
            return NoiseFilterVerdict(
                is_noise=True,
                category="very_thin_summary",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (very thin summary) as the title is empty or lacks substantive content.",
            )

        clean_title = title.strip()

        # Guard: If critical industrial keywords exist, bypass fast-gate to let LLM evaluate safely
        if CRITICAL_INDUSTRIAL_KEYWORDS.search(clean_title):
            return NoiseFilterVerdict(is_noise=False)

        # 1. Law firm advertisement & shareholder solicitations
        if LAW_FIRM_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="law_firm_advertisement",
                classification="Not Impactful",
                event_type="Legal Action",
                rationale="Not Impactful under the Bad Article Taxonomy (law firm advertisement) as this is a securities litigation solicitation seeking shareholder plaintiffs, presenting zero operational or supply chain disruption.",
            )

        # 2. Sports stories
        if SPORTS_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="sports_story",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (sports story) as athletic games, scores, and sports league announcements carry zero supply chain relevance.",
            )

        # 3. Celebrity / entertainment stories
        if CELEBRITY_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="celebrity_story",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (celebrity story) as entertainment news and celebrity gossip carry zero supply chain relevance.",
            )

        # 4. Civilian incidents
        if CIVILIAN_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="civilian_incident_only",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (civilian incident) as this is a domestic residential or civilian incident with zero industrial manufacturing or freight impact.",
            )

        # 5. Historical retrospectives
        if HISTORICAL_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="historical_recap",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (historical recap) as retrospective anniversary narratives recount past events with zero active supply chain disruption.",
            )

        # 6. Promotional PR
        if PROMOTIONAL_PR_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="promotional_pr",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (promotional PR) as brand marketing campaigns and workplace awards present zero operational disruption.",
            )

        # 7. Generic explainers
        if EXPLAINER_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="generic_explainer",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (generic explainer) as educational guides and glossaries contain zero contemporaneous operational disruption.",
            )

        # 8. Opinion only
        if OPINION_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="opinion_only",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (opinion only) as commentary and op-ed viewpoints lack concrete supply chain disruption events.",
            )

        # 9. Routine dividends
        if ROUTINE_DIVIDEND_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="no_disruption_signal",
                classification="Not Impactful",
                event_type="Financial Distress",
                rationale="Not Impactful under the Bad Article Taxonomy (no disruption signal) as routine quarterly dividend declarations reflect normal business operations without disruption.",
            )

        # 8b. Crime
        if CRIME_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="minor_crime",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful. Routine local crime does not disrupt industrial supply chains.",
            )

        # 11. Consumer Electronics
        if CONSUMER_TECH_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="consumer_tech",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful. Consumer product releases and deals do not represent supply chain disruptions.",
            )

        # 12. Entertainment
        if ENTERTAINMENT_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="local_entertainment",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful. Local entertainment events have no supply chain relevance.",
            )

        # 13. Hospitality
        if HOSPITALITY_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="hospitality",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful. Restaurants, pubs, and hotels are outside the industrial supply chain scope.",
            )

        # 14. Real Estate
        if REAL_ESTATE_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="residential_real_estate",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful. Residential real estate does not affect industrial supply chains.",
            )

        # 15. Web Portals & Logins
        if WEB_PORTAL_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="web_portal_artifact",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful. This is a web scraping artifact (login/subscription page) containing zero event data.",
            )

        # 16. Clickbait & Questions
        if CLICKBAIT_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="clickbait_or_question",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful. This is a generic clickbait article, giveaway, or hypothetical question.",
            )

        # 10. Unrelated noise
        if UNRELATED_NOISE_PATTERNS.search(clean_title):
            return NoiseFilterVerdict(
                is_noise=True,
                category="unrelated_topic_noise",
                classification="Not Impactful",
                event_type="Other",
                rationale="Not Impactful under the Bad Article Taxonomy (unrelated topic noise) as municipal or lifestyle news carries zero supply chain relevance.",
            )

        return NoiseFilterVerdict(is_noise=False)
