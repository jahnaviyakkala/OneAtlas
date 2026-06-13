"""
json_repair_tool.py
───────────────────
Strips markdown fences from LLM output and extracts the first valid JSON object.
Falls back to the json_repair library if standard parse fails.

Used by crew.py after every agent kickoff to sanitise raw LLM output before
passing it to Pydantic validators.

Logs are intentionally verbose — remove the logger.debug calls once stable.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from crewai.tools import BaseTool
from json_repair import repair_json
from pydantic import BaseModel, Field

logger = logging.getLogger("protoflow.json_repair")


# ── Input schema ──────────────────────────────────────────────────────────────

class JSONRepairInput(BaseModel):
    """Input for the JSON repair tool."""

    raw_text: str = Field(
        ...,
        description="Raw LLM output that may contain markdown fences, prose, or malformed JSON.",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)
_ARRAY_RE = re.compile(r"\[[\s\S]*\]", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences and return inner content."""
    match = _FENCE_RE.search(text)
    if match:
        logger.debug("[json_repair] Stripped markdown fence from LLM output.")
        return match.group(1).strip()
    return text.strip()


def _extract_first_json(text: str) -> Optional[str]:
    """
    Try to find the first JSON object or array in the text.
    Returns the raw JSON string or None.
    """
    # Prefer objects over arrays
    for pattern in (_OBJECT_RE, _ARRAY_RE):
        match = pattern.search(text)
        if match:
            logger.debug("[json_repair] Extracted JSON candidate via regex.")
            return match.group(0)
    return None


def extract_json(raw_text: str) -> Any:
    """
    Main extraction function.

    Steps:
    1. Strip markdown fences.
    2. Try standard json.loads on the stripped text.
    3. Try extracting the first JSON object/array via regex, then json.loads.
    4. Fall back to json_repair library.
    5. Raise ValueError if all attempts fail.
    """
    logger.debug("[json_repair] Starting extraction. Input length: %d chars.", len(raw_text))

    # Step 1 — strip fences
    stripped = _strip_fences(raw_text)
    logger.debug("[json_repair] After fence strip: %d chars.", len(stripped))

    # Step 2 — direct parse
    try:
        result = json.loads(stripped)
        logger.debug("[json_repair] Direct json.loads succeeded.")
        return result
    except json.JSONDecodeError as e:
        logger.debug("[json_repair] Direct parse failed: %s", e)

    # Step 3 — regex extraction + parse
    candidate = _extract_first_json(stripped)
    if candidate:
        try:
            result = json.loads(candidate)
            logger.debug("[json_repair] Regex-extracted json.loads succeeded.")
            return result
        except json.JSONDecodeError as e:
            logger.debug("[json_repair] Regex-extracted parse failed: %s", e)

    # Step 4 — json_repair fallback
    try:
        repaired = repair_json(stripped, return_objects=True)
        if repaired is not None:
            logger.warning(
                "[json_repair] Used json_repair fallback. "
                "LLM output was malformed — check agent prompt."
            )
            return repaired
    except Exception as e:
        logger.error("[json_repair] json_repair library failed: %s", e)

    # Step 5 — give up
    preview = raw_text[:200].replace("\n", " ")
    logger.error(
        "[json_repair] All extraction attempts failed. Raw preview: %s", preview
    )
    raise ValueError(
        f"Could not extract valid JSON from LLM output. "
        f"Preview: {preview!r}"
    )


# ── CrewAI Tool wrapper ───────────────────────────────────────────────────────

class JSONRepairTool(BaseTool):
    """
    CrewAI tool that strips markdown fences and extracts valid JSON from
    raw LLM output. Falls back to json_repair if standard parse fails.
    """

    name: str = "json_repair"
    description: str = (
        "Strips markdown fences from LLM output and extracts the first valid "
        "JSON object or array. Falls back to json_repair library if needed. "
        "Use this on any raw agent output before passing it to Pydantic."
    )
    args_schema: type[BaseModel] = JSONRepairInput

    def _run(self, raw_text: str) -> str:
        """Returns the extracted JSON as a compact string."""
        logger.debug("[JSONRepairTool] _run called.")
        result = extract_json(raw_text)
        compact = json.dumps(result, separators=(",", ":"))
        logger.debug("[JSONRepairTool] Returning %d chars of JSON.", len(compact))
        return compact
