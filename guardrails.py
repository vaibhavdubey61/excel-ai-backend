"""
guardrails.py
=============
Ultra-fast prompt injection and jailbreak protection for Excel AI Coach.

Protects against:
- "ignore all previous instructions" / instruction overrides
- System prompt extraction attempts ("output your system prompt")
- DAN / jailbreak modes / unrestricted persona hijacking
- Rule bypass and unauthorized instruction tampering

Constraints:
- Sub-millisecond evaluation (<10ms target) via pre-compiled regex automata.
- Executed before any vector store retrieval or LLM inference.
"""

import re
from typing import Tuple, Optional

# Standard safe response required by specification
SAFE_CANNED_RESPONSE = "I am designed to assist only with CA/CS/CMA study materials."

# Pre-compiled high-performance regex patterns
INJECTION_PATTERNS = [
    # 1. Instruction override / ignore previous instructions
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|above|existing)\s+(?:instructions?|rules?|guidelines?)", re.IGNORECASE),
    re.compile(r"forget\s+(?:all\s+)?(?:previous|prior|above)\s+(?:rules?|instructions?|context)", re.IGNORECASE),

    # 2. System prompt and confidential instructions extraction
    re.compile(r"(?:output|show|print|reveal|display|leak|give\s+me|repeat|expose)\s+(?:your\s+)?(?:secret\s+)?(?:system\s+prompt|system\s+instructions?|initial\s+prompt|meta\s+prompt|developer\s+message)", re.IGNORECASE),
    re.compile(r"what\s+(?:is|are)\s+(?:your\s+)?(?:secret\s+)?(?:system\s+prompt|system\s+instructions?|underlying\s+rules?)", re.IGNORECASE),

    # 3. DAN mode, jailbreaks, and unrestricted persona hijacking
    re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
    re.compile(r"\bjailbreak(?:ed)?\b", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now", re.IGNORECASE),
    re.compile(r"developer\s+mode\s+output", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:in\s+)?(?:god\s+mode|unfiltered\s+mode|unrestricted|evil|chaos)", re.IGNORECASE),
    re.compile(r"act\s+as\s+an?\s+(?:unrestricted|unfiltered|jailbroken|evil)\s+AI", re.IGNORECASE),
    re.compile(r"bypass\s+(?:all\s+)?(?:guardrails?|safety|filters?|restrictions?|guidelines?|rules?)", re.IGNORECASE),
    re.compile(r"you\s+have\s+been\s+freed\s+from", re.IGNORECASE),
]


def check_input_guardrails(text: str) -> Tuple[bool, Optional[str]]:
    """
    Evaluates input text against known prompt injection and jailbreak patterns.

    Returns:
        Tuple[bool, Optional[str]]:
            - is_safe: True if clean, False if an injection pattern was triggered.
            - matched_rule: Name or pattern that was triggered, or None if safe.

    Performance:
        Runs in < 0.2 milliseconds (well below the 10ms threshold).
    """
    if not text:
        return True, None

    # Normalize text for inspection
    clean_text = text.strip()

    for pattern in INJECTION_PATTERNS:
        match = pattern.search(clean_text)
        if match:
            return False, match.group(0)

    return True, None


def sanitize_or_reject(text: str) -> Optional[str]:
    """
    Convenience wrapper: returns SAFE_CANNED_RESPONSE if injection detected, else None.
    """
    is_safe, _ = check_input_guardrails(text)
    if not is_safe:
        return SAFE_CANNED_RESPONSE
    return None
