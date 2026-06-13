"""
mermaid_generator_tool.py
─────────────────────────
Generates syntactically valid Mermaid diagram strings from schema data.
Three diagram types:
  1. pipeline_flow  — flowchart of pipeline stages with HITL/repair annotations
  2. er_diagram     — entity-relationship diagram from DBSchema
  3. api_sequence   — sequence diagram for primary entity CRUD flow

Used by the progress_logger agent and directly by crew.py as a fallback
if the LLM-generated Mermaid is invalid.

Logs are intentionally verbose — remove logger.debug calls once stable.
"""

from __future__ import annotations

import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger("protoflow.mermaid")


# ── Input schema ──────────────────────────────────────────────────────────────

class MermaidInput(BaseModel):
    """Input for the Mermaid generator tool."""

    diagram_type: str = Field(
        ...,
        description="One of: 'pipeline_flow', 'er_diagram', 'api_sequence'.",
    )
    data: dict = Field(
        default_factory=dict,
        description="Schema data to render. Structure depends on diagram_type.",
    )


# ── Pipeline flow diagram ─────────────────────────────────────────────────────

def generate_pipeline_flow(data: dict) -> str:
    """
    Generate a Mermaid flowchart showing pipeline stages.

    data keys (all optional):
      stages: list of {name, status, hitl, repair}
      repair_count: int
      hitl_count: int
    """
    logger.debug("[mermaid] Generating pipeline_flow diagram.")

    stages = data.get("stages", [
        {"name": "Intent Extraction", "status": "complete", "hitl": True, "repair": False},
        {"name": "Architecture Design", "status": "complete", "hitl": False, "repair": False},
        {"name": "DB Schema", "status": "complete", "hitl": False, "repair": False},
        {"name": "API Schema", "status": "complete", "hitl": False, "repair": False},
        {"name": "UI Schema", "status": "complete", "hitl": False, "repair": False},
        {"name": "Auth Schema", "status": "complete", "hitl": False, "repair": False},
        {"name": "Validation", "status": "complete", "hitl": False, "repair": False},
        {"name": "Repair", "status": "complete", "hitl": False, "repair": True},
        {"name": "Runtime Validation", "status": "complete", "hitl": False, "repair": False},
        {"name": "Logging", "status": "complete", "hitl": False, "repair": False},
    ])

    lines = ["flowchart TD"]
    lines.append("    START([User Prompt]) --> S0")

    for i, stage in enumerate(stages):
        node_id = f"S{i}"
        name = stage.get("name", f"Stage {i}")
        status = stage.get("status", "complete")
        hitl = stage.get("hitl", False)
        repair = stage.get("repair", False)

        # Node shape based on status
        if status == "failed":
            node_def = f'    {node_id}["{name} [FAILED]"]'
        elif hitl:
            node_def = f'    {node_id}{{"{name} [HITL]"}}'
        elif repair:
            node_def = f'    {node_id}["{name} [REPAIR]"]'
        else:
            node_def = f'    {node_id}["{name}"]'

        lines.append(node_def)

        # Style
        if status == "failed":
            lines.append(f"    style {node_id} fill:#ff4444,color:#fff")
        elif hitl:
            lines.append(f"    style {node_id} fill:#f59e0b,color:#fff")
        elif repair:
            lines.append(f"    style {node_id} fill:#f97316,color:#fff")
        else:
            lines.append(f"    style {node_id} fill:#22c55e,color:#fff")

        # Arrow to next
        if i < len(stages) - 1:
            lines.append(f"    S{i} --> S{i+1}")

    lines.append(f"    S{len(stages)-1} --> END([Final Schema])")
    lines.append("    style END fill:#6366f1,color:#fff")
    lines.append("    style START fill:#6366f1,color:#fff")

    diagram = "\n".join(lines)
    logger.debug("[mermaid] pipeline_flow generated (%d lines).", len(lines))
    return diagram


# ── ER diagram ────────────────────────────────────────────────────────────────

def generate_er_diagram(data: dict) -> str:
    """
    Generate a Mermaid erDiagram from DBSchema data.

    data keys:
      tables: list of TableSchema dicts (name, columns, foreign_keys)
    """
    logger.debug("[mermaid] Generating er_diagram.")

    tables = data.get("tables", [])
    if not tables:
        logger.warning("[mermaid] No tables provided for ER diagram — returning placeholder.")
        return "erDiagram\n    PLACEHOLDER {\n        string id PK\n    }"

    lines = ["erDiagram"]

    for table in tables:
        name = table.get("name", "UNKNOWN").upper()
        columns = table.get("columns", [])
        lines.append(f"    {name} {{")
        for col in columns:
            col_name = col.get("name", "field")
            col_type = col.get("data_type", "string").split("(")[0].lower()
            # Mark PK and FK
            pk = table.get("primary_key", "id")
            fk_cols = {fk.get("column") for fk in table.get("foreign_keys", [])}
            if col_name == pk:
                lines.append(f"        {col_type} {col_name} PK")
            elif col_name in fk_cols:
                lines.append(f"        {col_type} {col_name} FK")
            else:
                lines.append(f"        {col_type} {col_name}")
        lines.append("    }")

    # Relationships from foreign keys
    for table in tables:
        table_name = table.get("name", "UNKNOWN").upper()
        for fk in table.get("foreign_keys", []):
            ref_table = fk.get("references_table", "UNKNOWN").upper()
            on_delete = fk.get("on_delete", "CASCADE")
            label = fk.get("column", "fk")
            # Cardinality: FK column means many-to-one
            lines.append(f'    {ref_table} ||--o{{ {table_name} : "{label}"')

    diagram = "\n".join(lines)
    logger.debug("[mermaid] er_diagram generated (%d lines).", len(lines))
    return diagram


# ── API sequence diagram ──────────────────────────────────────────────────────

def generate_api_sequence(data: dict) -> str:
    """
    Generate a Mermaid sequenceDiagram for the primary entity CRUD flow.

    data keys:
      entity: str (primary entity name, e.g. "User")
      endpoints: list of EndpointSchema dicts
    """
    logger.debug("[mermaid] Generating api_sequence.")

    entity = data.get("entity", "Entity")
    endpoints = data.get("endpoints", [])

    # Filter to CRUD endpoints for the primary entity
    entity_lower = entity.lower()
    crud_endpoints = [
        ep for ep in endpoints
        if entity_lower in ep.get("path", "").lower()
    ]

    if not crud_endpoints:
        logger.warning(
            "[mermaid] No endpoints found for entity '%s' — using generic CRUD.", entity
        )
        crud_endpoints = [
            {"method": "POST", "path": f"/api/{entity_lower}s", "description": f"Create {entity}"},
            {"method": "GET", "path": f"/api/{entity_lower}s", "description": f"List {entity}s"},
            {"method": "GET", "path": f"/api/{entity_lower}s/{{id}}", "description": f"Get {entity}"},
            {"method": "PUT", "path": f"/api/{entity_lower}s/{{id}}", "description": f"Update {entity}"},
            {"method": "DELETE", "path": f"/api/{entity_lower}s/{{id}}", "description": f"Delete {entity}"},
        ]

    lines = [
        "sequenceDiagram",
        "    participant U as User",
        "    participant FE as Frontend",
        "    participant API as API Server",
        "    participant DB as Database",
        "    participant Auth as Auth Service",
        "",
    ]

    for ep in crud_endpoints[:8]:  # cap at 8 to keep diagram readable
        method = ep.get("method", "GET")
        path = ep.get("path", "/")
        desc = ep.get("description", f"{method} {path}")
        auth_required = ep.get("auth_required", True)

        lines.append(f"    Note over U,DB: {desc}")
        lines.append(f"    U->>FE: Trigger {method} action")
        if auth_required:
            lines.append("    FE->>Auth: Validate JWT token")
            lines.append("    Auth-->>FE: Token valid")
        lines.append(f"    FE->>API: {method} {path}")
        lines.append("    API->>DB: Execute query")
        lines.append("    DB-->>API: Return result")
        lines.append("    API-->>FE: JSON response")
        lines.append("    FE-->>U: Update UI")
        lines.append("")

    diagram = "\n".join(lines)
    logger.debug("[mermaid] api_sequence generated (%d lines).", len(lines))
    return diagram


# ── Validation ────────────────────────────────────────────────────────────────

def validate_mermaid(diagram: str) -> bool:
    """
    Basic syntactic validation — checks that the diagram starts with a
    known Mermaid diagram type keyword.
    """
    known_types = (
        "flowchart", "graph", "sequenceDiagram", "erDiagram",
        "classDiagram", "stateDiagram", "gantt", "pie",
    )
    stripped = diagram.strip()
    is_valid = any(stripped.startswith(t) for t in known_types)
    if not is_valid:
        logger.warning(
            "[mermaid] Diagram does not start with a known Mermaid type. "
            "First 80 chars: %s", stripped[:80]
        )
    return is_valid


# ── CrewAI Tool wrapper ───────────────────────────────────────────────────────

class MermaidGeneratorTool(BaseTool):
    """
    CrewAI tool that generates syntactically valid Mermaid diagram strings
    from schema data. Supports pipeline_flow, er_diagram, and api_sequence.
    """

    name: str = "mermaid_generator"
    description: str = (
        "Generates syntactically valid Mermaid diagram strings from schema data. "
        "diagram_type must be one of: 'pipeline_flow', 'er_diagram', 'api_sequence'. "
        "Returns the Mermaid string ready to embed in markdown or render in the frontend."
    )
    args_schema: type[BaseModel] = MermaidInput

    def _run(self, diagram_type: str, data: dict) -> str:
        logger.debug("[MermaidGeneratorTool] _run called for type '%s'.", diagram_type)

        generators = {
            "pipeline_flow": generate_pipeline_flow,
            "er_diagram": generate_er_diagram,
            "api_sequence": generate_api_sequence,
        }

        generator = generators.get(diagram_type)
        if not generator:
            logger.error(
                "[MermaidGeneratorTool] Unknown diagram_type '%s'. "
                "Valid types: %s", diagram_type, list(generators.keys())
            )
            return f"# Error: unknown diagram_type '{diagram_type}'"

        diagram = generator(data)

        if not validate_mermaid(diagram):
            logger.error(
                "[MermaidGeneratorTool] Generated diagram failed validation for type '%s'.",
                diagram_type,
            )

        return diagram
