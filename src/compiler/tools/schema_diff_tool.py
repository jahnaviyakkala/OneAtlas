"""
schema_diff_tool.py
───────────────────
Produces a human-readable before/after diff between two JSON objects.
Used by the repair_agent to document every change it makes.

Logs are intentionally verbose — remove logger.debug calls once stable.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger("protoflow.schema_diff")


# ── Input schema ──────────────────────────────────────────────────────────────

class SchemaDiffInput(BaseModel):
    """Input for the schema diff tool."""

    before: str = Field(
        ...,
        description="JSON string of the schema before the repair.",
    )
    after: str = Field(
        ...,
        description="JSON string of the schema after the repair.",
    )
    layer: str = Field(
        default="unknown",
        description="Which schema layer was modified (db, api, ui, auth).",
    )


# ── Diff logic ────────────────────────────────────────────────────────────────

def _flatten(obj: Any, prefix: str = "") -> dict[str, str]:
    """
    Recursively flatten a nested dict/list into dot-notation key -> value pairs.
    Used to produce a field-level diff.
    """
    items: dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            items.update(_flatten(v, new_key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_key = f"{prefix}[{i}]"
            items.update(_flatten(v, new_key))
    else:
        items[prefix] = str(obj)
    return items


def compute_diff(before_json: str, after_json: str, layer: str) -> dict:
    """
    Compare two JSON strings and return a structured diff.

    Returns a dict with:
      layer: str
      added: list of {key, value}
      removed: list of {key, value}
      changed: list of {key, before, after}
      summary: str
    """
    logger.debug("[schema_diff] Computing diff for layer '%s'.", layer)

    try:
        before_obj = json.loads(before_json)
    except json.JSONDecodeError as e:
        logger.error("[schema_diff] Failed to parse 'before' JSON: %s", e)
        before_obj = {}

    try:
        after_obj = json.loads(after_json)
    except json.JSONDecodeError as e:
        logger.error("[schema_diff] Failed to parse 'after' JSON: %s", e)
        after_obj = {}

    before_flat = _flatten(before_obj)
    after_flat = _flatten(after_obj)

    before_keys = set(before_flat.keys())
    after_keys = set(after_flat.keys())

    added = [
        {"key": k, "value": after_flat[k]}
        for k in sorted(after_keys - before_keys)
    ]
    removed = [
        {"key": k, "value": before_flat[k]}
        for k in sorted(before_keys - after_keys)
    ]
    changed = [
        {"key": k, "before": before_flat[k], "after": after_flat[k]}
        for k in sorted(before_keys & after_keys)
        if before_flat[k] != after_flat[k]
    ]

    total_changes = len(added) + len(removed) + len(changed)
    summary = (
        f"Layer '{layer}': {len(added)} added, "
        f"{len(removed)} removed, {len(changed)} changed "
        f"({total_changes} total field changes)."
    )

    logger.info("[schema_diff] %s", summary)

    return {
        "layer": layer,
        "added": added,
        "removed": removed,
        "changed": changed,
        "summary": summary,
    }


# ── CrewAI Tool wrapper ───────────────────────────────────────────────────────

class SchemaDiffTool(BaseTool):
    """
    CrewAI tool that computes a field-level diff between two JSON schema versions.
    Used by the repair_agent to document every change it makes.
    """

    name: str = "schema_diff"
    description: str = (
        "Computes a field-level before/after diff between two JSON schema versions. "
        "Returns added, removed, and changed fields with a human-readable summary. "
        "Use this after every repair to document what changed."
    )
    args_schema: type[BaseModel] = SchemaDiffInput

    def _run(self, before: str, after: str, layer: str = "unknown") -> str:
        logger.debug("[SchemaDiffTool] _run called for layer '%s'.", layer)
        diff = compute_diff(before, after, layer)
        return json.dumps(diff, indent=2)
