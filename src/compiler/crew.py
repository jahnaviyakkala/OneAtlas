"""
crew.py — ProtoFlow Pipeline Orchestrator
─────────────────────────────────────────
Assembles the CrewAI crew from YAML config and runs the full pipeline.

Key responsibilities:
  - Load agents and tasks from config/agents.yaml and config/tasks.yaml
  - Fan out parallel stages (db, api, ui, auth) via asyncio.gather
  - Run the repair loop (max 3 attempts) after validation failures
  - Emit SSE events at every stage transition
  - Hold the pipeline on HITL events using asyncio.Event
  - Write structured logs via the logging module (remove debug calls later)

All LLM calls go through Groq via crewai LiteLLM routing. Temperature is set per-agent via
the LLM config in main.py (not in YAML, because YAML does not support
the full LLM config object).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

import litellm
import yaml as _yaml

# Monkey-patch litellm to strip `cache_breakpoint` from messages.
# CrewAI 1.14+ injects this for Anthropic, but Groq strictly rejects it with a 400 Bad Request.
original_completion = litellm.completion


def patched_completion(*args, **kwargs):
    if "messages" in kwargs:
        for msg in kwargs["messages"]:
            if "cache_breakpoint" in msg:
                del msg["cache_breakpoint"]
    return original_completion(*args, **kwargs)


litellm.completion = patched_completion

import asyncio
import re
import traceback

from dotenv import load_dotenv

# Load environment variables before parsing keys
load_dotenv()

# crewai imports
from crewai import LLM, Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from compiler.tools.json_repair_tool import extract_json
from compiler.tools.routing import cost_for_tokens, model_for_stage, routing_summary

if TYPE_CHECKING:
    from compiler.schemas.contracts import FinalOutput, RepairReport, ValidationReport

logger = logging.getLogger("protoflow.crew")

SSEEmitter = Callable[[str, str, dict], Coroutine[Any, Any, None]]

MAX_REPAIR_LOOPS = int(os.getenv("MAX_REPAIR_LOOPS", "3"))


def _llm_for_agent(agent_name: str) -> "LLM":
    """
    Returns a CrewAI LLM object for the given agent name.
    Model and temperature come from routing.yaml — not hardcoded.
    Falls back to Groq defaults if stage not found in config.
    """
    primary, _fallback, temp = model_for_stage(agent_name)
    logger.debug("[routing] Agent %s -> model=%s temp=%s", agent_name, primary, temp)
    return LLM(model=primary, temperature=temp)


def _classify_repair_strategy(
    errors: list, validation_report: dict, attempt: int
) -> str:
    """
    Deterministic repair strategy classifier.
    Returns one of: STRUCTURAL, FIELD, CONSISTENCY, ESCALATED.

    Priority order:
      1. ESCALATED  — attempt >= 2 with errors still present
      2. STRUCTURAL — JSON parse failure indicators
      3. CONSISTENCY — cross-layer reference keywords
      4. FIELD      — everything else (missing/wrong field)
    """
    # ESCALATED: persistent errors after multiple attempts
    if attempt >= 2 and errors:
        return "ESCALATED"

    # Combine all error descriptions into one lowercase string for pattern matching
    all_errors = " ".join(
        e.get("description", str(e)) if isinstance(e, dict) else str(e) for e in errors
    ).lower()

    # Also check if the report itself indicates a parse failure (empty report)
    is_empty_report = not validation_report or (
        not validation_report.get("errors")
        and not validation_report.get("warnings")
        and not validation_report.get("validated_at")
    )

    # STRUCTURAL: JSON/parse/format failures
    structural_keywords = [
        "json",
        "parse",
        "malformed",
        "truncated",
        "invalid json",
        "could not extract",
        "empty",
        "syntax error",
        "decode error",
        "format",
        "missing json",
        "not valid",
    ]
    if is_empty_report or any(kw in all_errors for kw in structural_keywords):
        return "STRUCTURAL"

    # CONSISTENCY: cross-layer reference mismatches
    consistency_keywords = [
        "not found in",
        "references",
        "does not exist",
        "missing entity",
        "missing table",
        "endpoint references",
        "page references",
        "role not defined",
        "undefined role",
        "foreign key",
        "cross-layer",
        "mismatch",
        "no corresponding",
        "no matching",
        "orphan",
        "inconsistent",
        "referenced",
        "not in schema",
    ]
    if any(kw in all_errors for kw in consistency_keywords):
        return "CONSISTENCY"

    # FIELD: default for missing/wrong field type errors
    return "FIELD"


HITL_TIMEOUT_SECONDS = int(os.getenv("HITL_TIMEOUT_SECONDS", "300"))

import random
import threading

_key_lock = threading.Lock()
_global_groq_idx = 0
_global_gemini_idx = 0


def get_next_groq_key() -> str:
    global _global_groq_idx
    if not GROQ_KEYS:
        return ""
    with _key_lock:
        key = GROQ_KEYS[_global_groq_idx % len(GROQ_KEYS)]
        _global_groq_idx += 1
        return key


def get_next_gemini_key() -> str:
    global _global_gemini_idx
    if not GEMINI_KEYS:
        return ""
    with _key_lock:
        key = GEMINI_KEYS[_global_gemini_idx % len(GEMINI_KEYS)]
        _global_gemini_idx += 1
        return key


# Load all available Groq API keys from env
GROQ_KEYS = []
for k, v in os.environ.items():
    if k.startswith("GROQ_API_KEY") and v.strip():
        GROQ_KEYS.extend([key.strip() for key in v.split(",") if key.strip()])
GROQ_KEYS = list(set(GROQ_KEYS))
if GROQ_KEYS:
    os.environ["GROQ_API_KEY"] = GROQ_KEYS[0]

# Load all Gemini API keys (GEMINI_API_KEY, GEMINI_API_KEY_2, etc.) for rotation
GEMINI_KEYS = []
for _k, _v in os.environ.items():
    if _k.startswith("GEMINI_API_KEY") and _v.strip():
        GEMINI_KEYS.extend([key.strip() for key in _v.split(",") if key.strip()])
GEMINI_KEYS = list(set(GEMINI_KEYS))
if GEMINI_KEYS:
    os.environ["GEMINI_API_KEY"] = GEMINI_KEYS[0]
    logger.info("[startup] Loaded %d Gemini key(s) for rotation.", len(GEMINI_KEYS))


# ── Schema compaction ─────────────────────────────────────────────────────────


def _compact(data: Optional[dict]) -> str:
    """Strip verbose text fields to reduce token count for downstream LLM calls.
    Removes description, default_value, error_responses, navigation_links,
    props, and validation fields recursively. Keeps all structural fields
    (names, types, paths, columns, endpoints, roles, permissions).
    """
    if not data:
        return "{}"
    _VERBOSE = frozenset(
        {
            "description",
            "backstory",
            "default_value",
            "error_responses",
            "navigation_links",
            "props",
            "validation",
        }
    )

    def _rec(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _rec(v) for k, v in obj.items() if k not in _VERBOSE}
        if isinstance(obj, list):
            return [_rec(i) for i in obj]
        return obj

    return json.dumps(_rec(data), separators=(",", ":"))


def _outline(data: Optional[dict]) -> str:
    """Ultra-compact schema outline for validation/repair/runtime inputs.
    Only retains structural keys (names, types, paths, methods, roles)
    and drops all detail arrays deeper than 1 level. This keeps token
    count low enough to fit in a single Groq request even for large apps.
    """
    if not data:
        return "{}"

    # Top-level keys to keep per schema type, with how many items to show
    def _summarise(obj: Any, depth: int = 0) -> Any:
        if depth >= 5:
            # At depth 5+, only return primitive values or list length
            if isinstance(obj, list):
                return f"[{len(obj)} items]"
            if isinstance(obj, dict):
                return f"{{{len(obj)} keys}}"
            return obj
        if isinstance(obj, dict):
            KEEP = frozenset(
                {
                    "name",
                    "table",
                    "path",
                    "method",
                    "type",
                    "role",
                    "role_required",
                    "auth_required",
                    "required_role",
                    "tables",
                    "endpoints",
                    "pages",
                    "roles",
                    "permissions_matrix",
                    "auth_strategy",
                    "entities",
                    "relations",
                    "primary_key",
                    "nullable",
                    "data_type",
                    "references_table",
                    "from_entity",
                    "to_entity",
                    "submit_endpoint",
                    "api_endpoint",
                    "cardinality",
                    "is_valid",
                    "errors",
                    "warnings",
                    "conflicts",
                }
            )
            return {k: _summarise(v, depth + 1) for k, v in obj.items() if k in KEEP}
        if isinstance(obj, list):
            return [_summarise(i, depth + 1) for i in obj]
        return obj

    return json.dumps(_summarise(data), separators=(",", ":"))


# ── CrewBase class ────────────────────────────────────────────────────────────


def _sanitize_mermaid(source: str, diagram_hint: str = "") -> str:
    """Fix the two most common LLM Mermaid syntax errors so diagrams render.

    1. -->|label|>  (extra trailing >) → -->|label|
       The LLM sometimes appends a '>' after the closing '|' of an edge label,
       which is invalid in Mermaid's flowchart grammar.

    2. 'style X fill:...' inside sequenceDiagram or erDiagram.
       Those diagram types don't support the 'style' keyword — only flowcharts
       do. Strip any line that starts with 'style ' in those diagram types.
    """
    if not source:
        return source

    # Normalise escaped newlines (LLM sometimes returns \\n literals)
    src = source.replace("\\n", "\n")

    # Fix 1: -->|label|>  →  -->|label|
    import re

    src = re.sub(r"(\|[^|]*\|)>", r"\1", src)

    # Fix 2: strip 'style ...' lines for diagram types that don't support it
    needs_strip = False
    first_line = src.strip().split("\n")[0] if src.strip() else ""
    if "sequenceDiagram" in src or diagram_hint == "sequence":
        needs_strip = True
    if "erDiagram" in src or diagram_hint == "er":
        needs_strip = True

    if needs_strip:
        cleaned = []
        for line in src.split("\n"):
            stripped = line.strip()
            if stripped.startswith("style ") and (
                "fill:" in stripped or "stroke:" in stripped
            ):
                continue  # drop invalid style line
            cleaned.append(line)
        src = "\n".join(cleaned)

    return src


@CrewBase
class ProtoFlowCrew:
    """
    ProtoFlow compiler crew.
    Agents and tasks are loaded from config/agents.yaml and config/tasks.yaml.
    Python code here only wires tools and assembles the crew — no agent logic.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # ── Agent factory methods ─────────────────────────────────────────────────

    @agent
    def intent_extractor(self) -> Agent:
        logger.debug("[crew] Building intent_extractor agent.")
        return Agent(
            config=self.agents_config["intent_extractor"],  # type: ignore[index]
            llm=_llm_for_agent("intent_extractor"),
            verbose=True,
            cache=False,
        )

    @agent
    def system_architect(self) -> Agent:
        logger.debug("[crew] Building system_architect agent.")
        return Agent(
            config=self.agents_config["system_architect"],  # type: ignore[index]
            llm=_llm_for_agent("system_architect"),
            verbose=True,
            cache=False,
        )

    @agent
    def db_schema_agent(self) -> Agent:
        logger.debug("[crew] Building db_schema_agent agent.")
        return Agent(
            config=self.agents_config["db_schema_agent"],  # type: ignore[index]
            llm=_llm_for_agent("db_schema_agent"),
            verbose=True,
            cache=False,
        )

    @agent
    def api_schema_agent(self) -> Agent:
        logger.debug("[crew] Building api_schema_agent agent.")
        return Agent(
            config=self.agents_config["api_schema_agent"],  # type: ignore[index]
            llm=_llm_for_agent("api_schema_agent"),
            verbose=True,
            cache=False,
        )

    @agent
    def ui_schema_agent(self) -> Agent:
        logger.debug("[crew] Building ui_schema_agent agent.")
        return Agent(
            config=self.agents_config["ui_schema_agent"],  # type: ignore[index]
            llm=_llm_for_agent("ui_schema_agent"),
            verbose=True,
            cache=False,
        )

    @agent
    def auth_agent(self) -> Agent:
        logger.debug("[crew] Building auth_agent agent.")
        return Agent(
            config=self.agents_config["auth_agent"],  # type: ignore[index]
            llm=_llm_for_agent("auth_agent"),
            verbose=True,
            cache=False,
        )

    @agent
    def validator_agent(self) -> Agent:
        logger.debug("[crew] Building validator_agent agent.")
        return Agent(
            config=self.agents_config["validator_agent"],  # type: ignore[index]
            llm=_llm_for_agent("validator_agent"),
            verbose=True,
            cache=False,
        )

    @agent
    def repair_agent(self) -> Agent:
        logger.debug("[crew] Building repair_agent agent.")
        return Agent(
            config=self.agents_config["repair_agent"],  # type: ignore[index]
            llm=_llm_for_agent("repair_agent"),
            verbose=True,
            cache=False,
        )

    @agent
    def runtime_validator(self) -> Agent:
        logger.debug("[crew] Building runtime_validator agent.")
        return Agent(
            config=self.agents_config["runtime_validator"],  # type: ignore[index]
            llm=_llm_for_agent("runtime_validator"),
            verbose=True,
            cache=False,
        )

    @agent
    def progress_logger(self) -> Agent:
        logger.debug("[crew] Building progress_logger agent.")
        return Agent(
            config=self.agents_config["progress_logger"],  # type: ignore[index]
            llm=_llm_for_agent("progress_logger"),
            verbose=True,
            cache=False,
        )

    @agent
    def integration_agent(self) -> Agent:
        logger.debug("[crew] Building integration_agent agent.")
        return Agent(
            config=self.agents_config["integration_agent"],  # type: ignore[index]
            llm=_llm_for_agent("integration_agent"),
            verbose=True,
            cache=False,
        )

    # ── Task factory methods ──────────────────────────────────────────────────

    @task
    def task_extract_intent(self) -> Task:
        logger.debug("[crew] Building task_extract_intent.")
        return Task(
            config=self.tasks_config["task_extract_intent"],  # type: ignore[index]
        )

    @task
    def task_design_architecture(self) -> Task:
        logger.debug("[crew] Building task_design_architecture.")
        return Task(
            config=self.tasks_config["task_design_architecture"],  # type: ignore[index]
        )

    @task
    def task_generate_db_schema(self) -> Task:
        logger.debug("[crew] Building task_generate_db_schema.")
        return Task(
            config=self.tasks_config["task_generate_db_schema"],  # type: ignore[index]
        )

    @task
    def task_generate_api_schema(self) -> Task:
        logger.debug("[crew] Building task_generate_api_schema.")
        return Task(
            config=self.tasks_config["task_generate_api_schema"],  # type: ignore[index]
        )

    @task
    def task_generate_ui_schema(self) -> Task:
        logger.debug("[crew] Building task_generate_ui_schema.")
        return Task(
            config=self.tasks_config["task_generate_ui_schema"],  # type: ignore[index]
        )

    @task
    def task_generate_auth_schema(self) -> Task:
        logger.debug("[crew] Building task_generate_auth_schema.")
        return Task(
            config=self.tasks_config["task_generate_auth_schema"],  # type: ignore[index]
        )

    @task
    def task_validate_schemas(self) -> Task:
        logger.debug("[crew] Building task_validate_schemas.")
        return Task(
            config=self.tasks_config["task_validate_schemas"],  # type: ignore[index]
        )

    @task
    def task_repair_schemas(self) -> Task:
        logger.debug("[crew] Building task_repair_schemas.")
        return Task(
            config=self.tasks_config["task_repair_schemas"],  # type: ignore[index]
        )

    @task
    def task_validate_runtime(self) -> Task:
        logger.debug("[crew] Building task_validate_runtime.")
        return Task(
            config=self.tasks_config["task_validate_runtime"],  # type: ignore[index]
        )

    @task
    def task_log_progress(self) -> Task:
        logger.debug("[crew] Building task_log_progress.")
        return Task(
            config=self.tasks_config["task_log_progress"],  # type: ignore[index]
        )

    # ── Crew assembly ─────────────────────────────────────────────────────────

    @task
    def task_generate_workflow_stubs(self) -> Task:
        logger.debug("[crew] Building task_generate_workflow_stubs.")
        return Task(
            config=self.tasks_config["task_generate_workflow_stubs"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """
        Assembles the ProtoFlow crew in sequential process.
        The parallel fan-out (db/api/ui/auth) is handled by the async
        pipeline runner below, not by CrewAI's process — CrewAI sequential
        is used as the base so task context passing works correctly.
        """
        logger.info("[crew] Assembling ProtoFlow crew (sequential process).")
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=False,  # No OpenAI embedder available; context passed via task context[]
        )


# ── Session state ─────────────────────────────────────────────────────────────


class PipelineSession:
    """
    Holds all mutable state for one pipeline run.
    One instance per session_id, stored in the session store in main.py.
    """

    def __init__(self, session_id: str, prompt: str, skip_hitl: bool = False) -> None:
        self.session_id = session_id
        self.prompt = prompt
        self.original_prompt = prompt  # preserves the initial prompt
        self.skip_hitl = skip_hitl
        self.started_at = time.monotonic()

        # HITL synchronisation
        self.hitl_event: asyncio.Event = asyncio.Event()
        self.hitl_answers: list[str] = []
        self.hitl_chosen_option: Optional[str] = None

        # Midway modification support
        self.pending_modification: Optional[str] = None  # set by POST /modify
        self.modification_history: list[dict] = []  # record of all modifications

        # Accumulated outputs
        self.intent: Optional[dict] = None
        self.architecture: Optional[dict] = None
        self.db_schema: Optional[dict] = None
        self.api_schema: Optional[dict] = None
        self.ui_schema: Optional[dict] = None
        self.auth_schema: Optional[dict] = None
        self.validation_report: Optional[dict] = None
        self.repair_report: Optional[dict] = None
        self.runtime_report: Optional[dict] = None
        self.workflow_stubs: list = []
        self.integration_hooks: list = []
        self.app_spec: Optional[dict] = None
        self.stage_models: dict[str, str] = {}  # stage -> model actually used
        self.stage_costs: dict[str, float] = {}  # stage -> estimated USD cost
        self.repair_log: list = []  # Feature F: per-attempt repair log
        self.log_output: Optional[dict] = None

        # Metrics
        self.repair_count: int = 0
        self.hitl_count: int = 0
        self.stage_latencies: dict[str, int] = {}
        self.total_tokens: int = 0

        # SSE event buffer for reconnection replay
        self.event_buffer: list[dict] = []
        self.sse_queue: asyncio.Queue = asyncio.Queue()

        logger.info(
            "[session:%s] Created. prompt_length=%d chars.", session_id, len(prompt)
        )

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def resume_hitl(
        self, answers: list[str], chosen_option: Optional[str] = None
    ) -> None:
        """Called by POST /clarify to unblock the pipeline."""
        logger.info(
            "[session:%s] HITL resumed. answers=%s chosen=%s",
            self.session_id,
            answers,
            chosen_option,
        )
        self.hitl_answers = answers
        self.hitl_chosen_option = chosen_option
        self.hitl_count += 1
        self.hitl_event.set()

    def queue_modification(self, modification: str) -> None:
        """Called by POST /modify to enqueue a midway prompt modification."""
        logger.info(
            "[session:%s] Modification queued: %r",
            self.session_id,
            modification[:100],
        )
        self.pending_modification = modification


# ── Async pipeline runner ─────────────────────────────────────────────────────


async def _emit(session: PipelineSession, event_type: str, payload: dict) -> None:
    """
    Push an SSE event onto the session queue and into the replay buffer.
    Logs every emission so you can trace the exact event sequence.
    """
    event = {"event": event_type, "session_id": session.session_id, **payload}
    session.event_buffer.append(event)
    await session.sse_queue.put(event)
    logger.debug(
        "[session:%s] SSE emitted. event=%s keys=%s",
        session.session_id,
        event_type,
        list(payload.keys()),
    )


async def _wait_for_hitl(
    session: PipelineSession,
    stage: str,
    trigger_reason: str,
    questions: list[str],
    options: Optional[list[str]] = None,
    timeout_seconds: int = HITL_TIMEOUT_SECONDS,
) -> list[str]:
    """
    Emit a hitl_required event, then block until POST /clarify sets the event.
    Returns the answers list.
    """
    if getattr(session, "skip_hitl", False):
        logger.info("[session:%s] HITL skipped (eval mode).", session.session_id)
        return []

    logger.info(
        "[session:%s] HITL required. stage=%s reason=%s questions=%s",
        session.session_id,
        stage,
        trigger_reason,
        questions,
    )
    session.hitl_event.clear()
    session.hitl_answers = []

    await _emit(
        session,
        "hitl_required",
        {
            "stage": stage,
            "trigger_reason": trigger_reason,
            "questions": questions,
            "options": options,
            "timeout_seconds": timeout_seconds,
        },
    )

    try:
        await asyncio.wait_for(session.hitl_event.wait(), timeout=timeout_seconds)
        logger.info(
            "[session:%s] HITL answered. answers=%s",
            session.session_id,
            session.hitl_answers,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[session:%s] HITL timed out after %ds. Proceeding with empty answers.",
            session.session_id,
            timeout_seconds,
        )

    return session.hitl_answers


async def _apply_pending_modification(
    session: PipelineSession, current_stage: str
) -> bool:
    """
    Check for a pending midway modification. If found, apply it to session.prompt
    and emit modification_applied SSE event. Returns True if a modification was applied.

    This is called at stage boundaries (between pipeline stages) so the next stage
    picks up the updated requirements. The pipeline is NOT restarted; only future
    stages benefit from the change. A disclaimer is already shown in the UI.
    """
    mod = session.pending_modification
    if not mod:
        return False

    session.pending_modification = None
    new_prompt = f"{session.prompt}\n\n[MID-RUN MODIFICATION at {current_stage}]: {mod}"
    session.prompt = new_prompt

    record = {
        "modification": mod,
        "applied_at_stage": current_stage,
        "new_prompt_length": len(new_prompt),
    }
    session.modification_history.append(record)

    logger.info(
        "[session:%s] Modification applied at stage=%s: %r",
        session.session_id,
        current_stage,
        mod[:100],
    )

    await _emit(
        session,
        "modification_applied",
        {
            "modification": mod,
            "applied_at_stage": current_stage,
            "new_prompt": new_prompt,
        },
    )
    return True


async def _run_stage(
    session: PipelineSession,
    stage_name: str,
    coro: Coroutine,
) -> Any:
    """
    Wrap a single pipeline stage coroutine with:
      - stage_update running event
      - timing
      - stage_update complete/failed event
    """
    logger.info("[session:%s] Stage START: %s", session.session_id, stage_name)
    model = model_for_stage(stage_name)[0]
    if getattr(session, "tpm_limit_hit", False):
        logger.warning(
            "[session:%s] Skipping stage %s due to prior TPM limit hit.",
            session.session_id,
            stage_name,
        )
        await _emit(
            session,
            "stage_update",
            {
                "stage": stage_name,
                "status": "failed",
                "model": model,
                "latency_ms": 0,
                "output_summary": "Bypassed due to Groq TPM limits.",
            },
        )
        return {}
    t0 = time.monotonic()

    await _emit(
        session,
        "stage_update",
        {
            "stage": stage_name,
            "status": "running",
            "model": model,
            "latency_ms": 0,
            "output_summary": "",
        },
    )
    # Also emit stage_start as a distinct event type (assignment requirement)
    await _emit(
        session,
        "stage_start",
        {
            "stage": stage_name,
            "model": model,
            "timestamp": int(time.monotonic() * 1000),
        },
    )

    try:
        result = await coro
        latency_ms = int((time.monotonic() - t0) * 1000)
        session.stage_latencies[stage_name] = latency_ms
        # Record which model was used for this stage (from routing config)
        _prim, _fb, _tmp = model_for_stage(stage_name)
        session.stage_models[stage_name] = _prim

        # Summarise output for SSE (first 120 chars of JSON)
        summary = ""
        if result:
            try:
                summary = json.dumps(result)[:120]
            except Exception:
                summary = str(result)[:120]

        await _emit(
            session,
            "stage_update",
            {
                "stage": stage_name,
                "status": "complete",
                "model": model,
                "latency_ms": latency_ms,
                "output_summary": summary,
            },
        )
        # Also emit stage_complete as distinct event type
        await _emit(
            session,
            "stage_complete",
            {
                "stage": stage_name,
                "latency_ms": latency_ms,
                "model": model,
            },
        )

        logger.info(
            "[session:%s] Stage DONE: %s latency=%dms",
            session.session_id,
            stage_name,
            latency_ms,
        )
        return result

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        session.stage_latencies[stage_name] = latency_ms
        is_size_limit = "Request size exceeds TPM limit" in str(exc) or (
            "Request too large" in str(exc) and "Limit" in str(exc)
        )
        if is_size_limit:
            # Log but DO NOT set tpm_limit_hit — let each stage fail independently
            # so the pipeline continues to completion with whatever it can produce.
            logger.error(
                "[session:%s] Request size limit hit in stage %s — stage skipped, pipeline continues.",
                session.session_id,
                stage_name,
            )
            await _emit(
                session,
                "stage_update",
                {
                    "stage": stage_name,
                    "status": "failed",
                    "model": model,
                    "latency_ms": latency_ms,
                    "output_summary": f"Skipped (request too large for model). {exc}",
                },
            )
            return {}
        logger.error(
            "[session:%s] Stage FAILED: %s error=%s latency=%dms",
            session.session_id,
            stage_name,
            exc,
            latency_ms,
            exc_info=True,
        )
        await _emit(
            session,
            "stage_update",
            {
                "stage": stage_name,
                "status": "failed",
                "model": model,
                "latency_ms": latency_ms,
                "output_summary": f"ERROR: {exc}",
            },
        )
        raise


async def run_pipeline(session: PipelineSession) -> None:
    """
    Full async pipeline runner.

    Stage order:
      1. intent_extraction  (sequential, HITL always-on)
      2. architecture       (async)
      3. db + api + ui + auth  (parallel fan-out via asyncio.gather)
      4. validation         (sequential)
      5. repair loop        (sequential, max MAX_REPAIR_LOOPS)
      6. runtime_validation (sequential)
      7. logging            (async)
      8. pipeline_complete  SSE event
    """
    logger.info(
        "[session:%s] Pipeline START. prompt=%r",
        session.session_id,
        session.prompt[:80],
    )

    crew_instance = ProtoFlowCrew()

    # ── Read raw YAML once so we can look up agent names by task name ─────────
    _yaml_path = os.path.join(os.path.dirname(__file__), "config", "tasks.yaml")
    with open(_yaml_path, "r", encoding="utf-8") as _f:
        _raw_tasks_yaml: dict = _yaml.safe_load(_f)
    logger.debug("[crew] Loaded raw tasks YAML. keys=%s", list(_raw_tasks_yaml.keys()))

    # ── Helper: kick off a single CrewAI task and parse JSON output ───────────
    async def _kickoff_task(task_name: str, inputs: dict) -> dict:
        """
        Run a single task by creating a temporary single-task Crew.
        Reads agent name from raw YAML (not from instantiated Task objects)
        to avoid the 'attribute name must be string, not Agent' error.
        """
        logger.debug(
            "[session:%s] _kickoff_task: %s inputs_keys=%s",
            session.session_id,
            task_name,
            list(inputs.keys()),
        )

        # Get agent name string from raw YAML dict
        raw_task_def = _raw_tasks_yaml.get(task_name, {})
        agent_name: str = raw_task_def.get("agent", "")
        logger.debug(
            "[session:%s] _kickoff_task: task=%s agent_name=%r",
            session.session_id,
            task_name,
            agent_name,
        )

        # Run in a thread pool to avoid blocking the event loop
        loop = asyncio.get_running_loop()

        # Instantiate agent via the @agent method on the crew class ONCE
        agent = None
        if agent_name and isinstance(agent_name, str):
            agent_creator = getattr(crew_instance, agent_name, None)
            if callable(agent_creator):
                agent = agent_creator()

                # --- Dynamic Load Balancing & Repair Routing ---
                is_repair = task_name == "task_repair_schemas"
                target_model = None
                target_api_key = None

                if is_repair and getattr(session, "validation_report", None):
                    # Find which schema produced the failure
                    report = session.validation_report
                    worst_schema = None
                    max_errs = -1
                    for schema_type in [
                        "db_schema",
                        "api_schema",
                        "ui_schema",
                        "auth_schema",
                    ]:
                        errs = len(report.get(f"{schema_type}_errors", []))
                        if errs > max_errs:
                            max_errs = errs
                            worst_schema = schema_type

                    if worst_schema:
                        task_map = {
                            "db_schema": "task_generate_db_schema",
                            "api_schema": "task_generate_api_schema",
                            "ui_schema": "task_generate_ui_schema",
                            "auth_schema": "task_generate_auth_schema",
                        }
                        gen_task = task_map.get(worst_schema)
                        if gen_task and gen_task in getattr(
                            session, "stage_models", {}
                        ):
                            target_model = session.stage_models[gen_task]
                            logger.info(
                                "[routing] Repair task targeting failed model: %s (from %s)",
                                target_model,
                                worst_schema,
                            )

                if agent and getattr(agent, "llm", None):
                    base_temp = (
                        agent.llm.temperature
                        if hasattr(agent.llm, "temperature")
                        else 0.1
                    )
                    current_model = target_model or model_for_stage(agent_name)[0]

                    # Distribute initial request across all keys to prevent Key 1 taking 100% of the load
                    if "gemini" in current_model.lower() and GEMINI_KEYS:
                        target_api_key = get_next_gemini_key()
                    elif "groq" in current_model.lower() and GROQ_KEYS:
                        target_api_key = get_next_groq_key()

                    if target_model or target_api_key:
                        kwargs = {"model": current_model, "temperature": base_temp}
                        if target_api_key:
                            kwargs["api_key"] = target_api_key
                            if "gemini" in current_model.lower():
                                os.environ["GEMINI_API_KEY"] = target_api_key
                            elif "groq" in current_model.lower():
                                os.environ["GROQ_API_KEY"] = target_api_key

                        # Re-instantiate agent.llm with the targeted model/key
                        agent.llm = LLM(**kwargs)

                logger.debug(
                    "[session:%s] Agent instantiated: %s (model=%s)",
                    session.session_id,
                    agent_name,
                    getattr(agent.llm, "model", "?"),
                )
                _primary_model, _fallback_model, _primary_temp = model_for_stage(
                    agent_name
                )
                _active_model = _primary_model
                logger.debug(
                    "[routing] stage=%s primary=%s fallback=%s",
                    task_name,
                    _primary_model,
                    _fallback_model,
                )
            else:
                logger.warning(
                    "[session:%s] No @agent method found for name=%r on ProtoFlowCrew",
                    session.session_id,
                    agent_name,
                )
        else:
            logger.warning(
                "[session:%s] agent_name is not a string: %r (type=%s). "
                "Check tasks.yaml for task '%s'.",
                session.session_id,
                agent_name,
                type(agent_name).__name__,
                task_name,
            )

        max_retries = 5
        result = None
        for attempt in range(max_retries):
            # Instantiate task via the @task method
            task_creator = getattr(crew_instance, task_name, None)
            if not callable(task_creator):
                raise ValueError(
                    f"No @task method found for '{task_name}' on ProtoFlowCrew"
                )
            task_obj = task_creator()

            # Assign agent to task
            if agent:
                task_obj.agent = agent

            temp_crew = Crew(
                agents=[agent] if agent else [],
                tasks=[task_obj],
                verbose=True,
                memory=False,  # No OpenAI embedder; avoids ChromaDB CHROMA_OPENAI_API_KEY error
                cache=False,  # Disable LLM caching to avoid returning stale broken outputs
            )

            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: temp_crew.kickoff(inputs=inputs),
                )
                break  # Success
            except Exception as e:
                err_str = str(e)
                # 5xx provider error -> switch to fallback model from routing config
                is_5xx = (
                    any(code in err_str for code in ["500", "502", "503", "504"])
                    and "RateLimitError" not in type(e).__name__
                )
                if is_5xx and attempt == 0 and agent and agent.llm:
                    _fb = (
                        _fallback_model
                        if "_fallback_model" in dir()
                        else model_for_stage(agent_name)[1]
                    )
                    logger.warning(
                        "[routing] FALLBACK stage=%s primary=%s -> fallback=%s reason=5xx",
                        task_name,
                        getattr(agent.llm, "model", "?"),
                        _fb,
                    )
                    agent.llm = LLM(
                        model=_fb,
                        temperature=_primary_temp if "_primary_temp" in dir() else 0.1,
                    )
                    continue
                if is_5xx and attempt == 0 and agent and agent.llm:
                    _fb = (
                        _fallback_model
                        if "_fallback_model" in dir()
                        else model_for_stage(agent_name)[1]
                    )
                    logger.warning(
                        "[routing] FALLBACK stage=%s primary=%s -> fallback=%s reason=5xx",
                        task_name,
                        getattr(agent.llm, "model", "?"),
                        _fb,
                    )
                    agent.llm = LLM(
                        model=_fb,
                        temperature=_primary_temp if "_primary_temp" in dir() else 0.1,
                    )
                    _active_model = _fb
                    continue
                if (
                    "RateLimitError" in type(e).__name__
                    or "rate_limit" in err_str.lower()
                    or "rate limit reached" in err_str.lower()
                ):
                    if (
                        "Request too large" in err_str
                        and "Limit" in err_str
                        and "Requested" in err_str
                    ):
                        # Request is too large for the current model — fall back to the
                        # smallest available Groq model regardless of which model we started with.
                        if (
                            agent
                            and agent.llm
                            and "llama-3.1-8b-instant" not in str(agent.llm.model)
                        ):
                            logger.warning(
                                "[session:%s] Request size exceeds model limit for %s. Falling back to groq/llama-3.1-8b-instant.",
                                session.session_id,
                                agent.llm.model,
                            )
                            agent.llm = LLM(
                                model="groq/llama-3.1-8b-instant", temperature=0.1
                            )
                            _active_model = "groq/llama-3.1-8b-instant"
                            continue  # Try immediately with fallback model
                        else:
                            raise ValueError(
                                f"Request size exceeds limit even for fallback model: {err_str}"
                            )

                    # If not a request size limit, it's a TPD limit or standard TPM timeout.
                    # Rotate API key if we have multiple keys available.
                    rotated = False
                    _current_model = _active_model
                    _is_gemini_model = "gemini" in _current_model.lower()

                    if _is_gemini_model and len(GEMINI_KEYS) > 1:
                        # Rotate Gemini API key
                        new_gemini_key = GEMINI_KEYS[attempt % len(GEMINI_KEYS)]
                        logger.warning(
                            "[session:%s] Rate limit hit on Gemini for %s. Rotating GEMINI_API_KEY...",
                            session.session_id,
                            task_name,
                        )
                        os.environ["GEMINI_API_KEY"] = new_gemini_key
                        if agent and agent.llm:
                            temp = (
                                agent.llm.temperature
                                if hasattr(agent.llm, "temperature")
                                else 0.2
                            )
                            agent.llm = LLM(
                                model=_current_model,
                                temperature=temp,
                                api_key=new_gemini_key,
                            )
                        if attempt < len(GEMINI_KEYS):
                            continue
                        rotated = True
                    elif not _is_gemini_model and len(GROQ_KEYS) > 1:
                        new_key = GROQ_KEYS[attempt % len(GROQ_KEYS)]
                        logger.warning(
                            "[session:%s] Rate limit / TPD hit for %s. Rotating to another GROQ_API_KEY...",
                            session.session_id,
                            task_name,
                        )
                        if agent and agent.llm:
                            # Re-instantiate LLM with new API key, ensure 'groq/' prefix
                            temp = (
                                agent.llm.temperature
                                if hasattr(agent.llm, "temperature")
                                else 0.1
                            )
                            model_name = agent.llm.model
                            if not model_name.startswith("groq/"):
                                model_name = f"groq/{model_name}"
                            agent.llm = LLM(
                                model=model_name, temperature=temp, api_key=new_key
                            )

                        # Only retry immediately if we haven't exhausted all our keys
                        if attempt < len(GROQ_KEYS):
                            continue
                        rotated = True
                    else:
                        # Unconditionally fallback to OpenRouter equivalent on 429 if no more keys
                        if agent and agent.llm:
                            from src.compiler.tools.routing import (
                                get_openrouter_equivalent,
                            )

                            _fb = get_openrouter_equivalent(_current_model)
                            logger.warning(
                                "[routing] FALLBACK stage=%s primary=%s -> fallback=%s reason=429_RateLimit",
                                task_name,
                                getattr(agent.llm, "model", "?"),
                                _fb,
                            )
                            agent.llm = LLM(
                                model=_fb,
                                temperature=(
                                    _primary_temp if "_primary_temp" in dir() else 0.1
                                ),
                            )
                            continue

                    if attempt < max_retries - 1:
                        # Parse "Please try again in 1h5m21.665s." or "21.665s."
                        wait_time = 30.0
                        match = re.search(
                            r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d\.]+)s", err_str
                        )
                        if match:
                            h_str = match.group(1)
                            m_str = match.group(2)
                            s_str = match.group(3)
                            hours = int(h_str) if h_str else 0
                            minutes = int(m_str) if m_str else 0
                            seconds = float(s_str)
                            wait_time = (
                                (hours * 3600) + (minutes * 60) + seconds + 2.0
                            )  # 2s buffer

                        if wait_time > 120.0:
                            logger.error(
                                "[session:%s] Rate limit wait time too long (%.1fs). Failing task.",
                                session.session_id,
                                wait_time,
                            )
                            raise e

                        logger.warning(
                            "[session:%s] Rate limit hit for %s. Sleeping %.1fs before attempt %d. Error: %s",
                            session.session_id,
                            task_name,
                            wait_time,
                            attempt + 2,
                            (
                                err_str.split('"message":')[1].split(',"type"')[0]
                                if '"message":' in err_str
                                else err_str[:100]
                            ),
                        )
                        await asyncio.sleep(wait_time)
                        continue
                # If it's not a rate limit error, or we're out of retries, raise it
                raise e

        if result is None:
            raise RuntimeError(
                f"Task '{task_name}' failed after {max_retries} retries due to rate limits or API errors."
            )

        # Token extraction and cost estimation
        if hasattr(result, "token_usage"):
            usage = result.token_usage
            if hasattr(usage, "total_tokens"):
                session.total_tokens += usage.total_tokens
            elif isinstance(usage, dict):
                session.total_tokens += usage.get("total_tokens", 0)
        # Estimate cost using routing cost_table
        if hasattr(result, "token_usage") and result.token_usage:
            usage = result.token_usage
            _input_t = getattr(usage, "prompt_tokens", 0) or (
                usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
            )
            _output_t = getattr(usage, "completion_tokens", 0) or (
                usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0
            )
            _used_model = session.stage_models.get(task_name)
            _cost = cost_for_tokens(_used_model, _input_t, _output_t)
            session.stage_costs[task_name] = (
                session.stage_costs.get(task_name, 0.0) + _cost
            )

        raw = result.raw if hasattr(result, "raw") else str(result)
        logger.debug(
            "[session:%s] _kickoff_task raw output length: %d chars",
            session.session_id,
            len(raw),
        )
        parsed = extract_json(raw)

        # Unwrap nested dict if LLM wraps it in a stage name key (e.g. {"api_schema": {...}})
        if isinstance(parsed, dict) and len(parsed) == 1:
            first_key = list(parsed.keys())[0]
            val = parsed[first_key]
            wrapper_keys = {
                "db_schema",
                "api_schema",
                "ui_schema",
                "auth_schema",
                "validation_report",
                "repair_report",
                "runtime_report",
                "log_output",
                "task_validate_runtime",
                "task_log_progress",
                "schema",
                "result",
                "response",
                "output",
                "log_progress",
                "progress_log",
            }
            if (
                first_key in wrapper_keys
                or first_key.endswith("_schema")
                or first_key.endswith("_report")
            ):
                if isinstance(val, dict):
                    logger.warning(
                        "[session:%s] Unwrapping nested LLM dict %s",
                        session.session_id,
                        first_key,
                    )
                    parsed = val

        # Wrap lists in expected root keys if LLM forgot the root object
        if isinstance(parsed, list):
            logger.warning(
                "[session:%s] LLM wrapped output in list. Fixing based on task_name: %s",
                session.session_id,
                task_name,
            )
            if task_name == "task_generate_api_schema":
                parsed = {"endpoints": parsed}
            elif task_name == "task_generate_ui_schema":
                parsed = {"pages": parsed}
            elif task_name == "task_generate_db_schema":
                parsed = {"tables": parsed}
            elif len(parsed) > 0 and isinstance(parsed[0], dict):
                parsed = parsed[0]
            else:
                parsed = {}

        if not isinstance(parsed, dict):
            logger.error(
                "[session:%s] LLM output parsed as %s instead of dict. Coercing to empty dict.",
                session.session_id,
                type(parsed).__name__,
            )
            return {}
        return parsed

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 1 — Intent Extraction (always HITL)
    # ─────────────────────────────────────────────────────────────────────────
    async def _stage_intent() -> dict:
        result = await _kickoff_task(
            "task_extract_intent",
            {"user_prompt": session.prompt},
        )
        confidence = result.get("confidence", 1.0)
        logger.info(
            "[session:%s] Intent extracted. confidence=%.2f assumptions=%d",
            session.session_id,
            confidence,
            len(result.get("assumptions", [])),
        )

        # HITL is always-on: prefer the LLM's own questions from hitl_required.questions
        # (the agent generates context-specific questions); fall back to hardcoded only
        # if the LLM didn't populate that field.
        llm_questions = []
        hitl_field = result.get("hitl_required", {})
        if isinstance(hitl_field, dict):
            llm_questions = hitl_field.get("questions", [])

        if confidence < 0.75 or not llm_questions:
            # Low confidence or no LLM questions — use targeted hardcoded questions
            questions = llm_questions or [
                "What is the primary purpose of this application?",
                "Who are the main user types and what can each do?",
                "Are there any premium or paid features?",
            ]
            trigger = "low_confidence"
        else:
            # High confidence — use LLM's confirmatory question
            questions = llm_questions[:1]  # typically 1 confirmatory question
            trigger = "always_on"

        answers = await _wait_for_hitl(session, "intent_extraction", trigger, questions)
        result["clarifications_received"] = answers
        session.intent = result
        return result

    session.intent = await _run_stage(session, "intent_extraction", _stage_intent())

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 2 — Architecture Design
    # ─────────────────────────────────────────────────────────────────────────
    async def _stage_architecture() -> dict:
        result = await _kickoff_task(
            "task_design_architecture",
            {
                "user_prompt": session.prompt,
                "intent_schema": json.dumps(session.intent),
            },
        )
        session.architecture = result
        logger.info(
            "[session:%s] Architecture designed. entities=%d relations=%d",
            session.session_id,
            len(result.get("entities", [])),
            len(result.get("relations", [])),
        )
        return result

    session.architecture = await _run_stage(
        session, "architecture_design", _stage_architecture()
    )

    # ── Modification checkpoint (before schema generation) ────────────────────
    await _apply_pending_modification(session, "before_schema_generation")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3 — Parallel fan-out: DB + API + UI + Auth
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("[session:%s] Starting parallel schema generation.", session.session_id)

    arch_json = _compact(session.architecture or {})

    async def _stage_db() -> dict:
        result = await _kickoff_task(
            "task_generate_db_schema",
            {"architecture_schema": arch_json, "user_prompt": session.prompt},
        )
        session.db_schema = result
        logger.info(
            "[session:%s] DB schema generated. tables=%d",
            session.session_id,
            len(result.get("tables", [])),
        )
        return result

    async def _stage_api() -> dict:
        result = await _kickoff_task(
            "task_generate_api_schema",
            {
                "architecture_schema": arch_json,
                "db_schema": _compact(session.db_schema or {}),
                "user_prompt": session.prompt,
            },
        )
        session.api_schema = result
        logger.info(
            "[session:%s] API schema generated. endpoints=%d",
            session.session_id,
            len(result.get("endpoints", [])),
        )
        return result

    async def _stage_ui() -> dict:
        result = await _kickoff_task(
            "task_generate_ui_schema",
            {
                "architecture_schema": arch_json,
                "api_schema": _compact(session.api_schema or {}),
                "user_prompt": session.prompt,
            },
        )
        session.ui_schema = result
        logger.info(
            "[session:%s] UI schema generated. pages=%d",
            session.session_id,
            len(result.get("pages", [])),
        )
        return result

    async def _stage_auth() -> dict:
        result = await _kickoff_task(
            "task_generate_auth_schema",
            {
                "architecture_schema": arch_json,
                "ui_schema": _compact(session.ui_schema or {}),
                "user_prompt": session.prompt,
            },
        )
        session.auth_schema = result
        logger.info(
            "[session:%s] Auth schema generated. roles=%s",
            session.session_id,
            result.get("roles", []),
        )
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # STAGES 3-6 — Sequential Execution (formerly parallel fan-out)
    # We run these sequentially to avoid hitting Groq's 12,000 TPM rate limit
    # ─────────────────────────────────────────────────────────────────────────
    async def _run_schema_stage(stage_name: str, task_coro) -> dict:
        model = model_for_stage(stage_name)[0]
        await _emit(
            session,
            "stage_update",
            {
                "stage": stage_name,
                "status": "running",
                "model": model,
                "latency_ms": 0,
                "output_summary": "",
            },
        )
        t_start = time.monotonic()
        result = await task_coro()
        latency_ms = int((time.monotonic() - t_start) * 1000)
        # Record to session so stage_latencies in eval_metrics is complete
        session.stage_latencies[stage_name] = latency_ms
        await _emit(
            session,
            "stage_update",
            {
                "stage": stage_name,
                "status": "complete",
                "model": model,
                "latency_ms": latency_ms,
                "output_summary": json.dumps(result)[:120],
            },
        )
        return result

    db_result = await _run_schema_stage("db_schema", _stage_db)
    # ── Modification checkpoint (between db and api generation) ──────────────
    await _apply_pending_modification(session, "before_api_schema")
    api_result = await _run_schema_stage("api_schema", _stage_api)
    # ── Modification checkpoint (between api and ui generation) ──────────────
    await _apply_pending_modification(session, "before_ui_schema")
    ui_result = await _run_schema_stage("ui_schema", _stage_ui)
    auth_result = await _run_schema_stage("auth_schema", _stage_auth)

    # ── Modification checkpoint (before validation) ───────────────────────────
    await _apply_pending_modification(session, "before_validation")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3.5 — Workflow Stub Generation (runs only when integrations requested)
    # ─────────────────────────────────────────────────────────────────────────
    from compiler.integrations.registry import REGISTRY, get_action, get_integration
    from compiler.schemas.contracts import WorkflowStub, WorkflowTrigger

    async def _stage_workflow_stubs() -> list:
        """
        Hybrid workflow stub generation:
          Step 1 — Deterministic skeletons from registry + intent integrations
          Step 2 — LLM enrichment (trigger conditions, payload mappings, descriptions)
          Step 3 — Validation: drop any stub whose integration_id or action_id
                   does not exist in REGISTRY
        Returns empty list if no integrations were requested.
        """
        requested = (session.intent or {}).get("integrations", [])
        if not requested:
            logger.info(
                "[session:%s] No integrations requested — skipping workflow stubs.",
                session.session_id,
            )
            return []

        logger.info(
            "[session:%s] Generating workflow stubs for integrations: %s",
            session.session_id,
            requested,
        )

        # STEP 1 — Deterministic skeleton generation
        # Priority action per integration (first match wins)
        _ACTION_PRIORITY: dict[str, str] = {
            "slack": "send_message",
            "gmail": "send_email",
            "stripe": "create_customer",
            "whatsapp": "send_template_message",
            "webhook": "post_payload",
            "jira": "create_issue",
            "google_sheets": "append_row",
            "hubspot": "create_contact",
            "notion": "create_page",
            "twilio_sms": "send_sms",
        }
        # Default event per integration type
        _EVENT_DEFAULT: dict[str, str] = {
            "slack": "status_changed",
            "gmail": "created",
            "stripe": "created",
            "whatsapp": "status_changed",
            "webhook": "created",
            "jira": "created",
            "google_sheets": "updated",
            "hubspot": "updated",
            "notion": "created",
            "twilio_sms": "status_changed",
        }

        # Get entity names from architecture for trigger entity matching
        arch_entities = []
        if session.architecture:
            arch_entities = [
                e.get("name", "") if isinstance(e, dict) else getattr(e, "name", "")
                for e in (
                    session.architecture.get("entities", [])
                    if isinstance(session.architecture, dict)
                    else getattr(session.architecture, "entities", [])
                )
            ]

        def _best_entity(integration_id: str) -> str:
            """Pick the most relevant entity for a given integration."""
            # Heuristic: prefer entity names that match integration domain keywords
            _ENTITY_HINTS: dict[str, list[str]] = {
                "slack": ["task", "deal", "issue", "ticket", "order", "project"],
                "gmail": ["order", "user", "customer", "invoice", "booking"],
                "stripe": ["user", "customer", "subscription", "payment", "order"],
                "whatsapp": ["deal", "order", "booking", "appointment", "lead"],
                "webhook": ["event", "record", "item"],
                "jira": ["task", "issue", "bug", "ticket", "story"],
                "google_sheets": ["report", "record", "entry", "row", "data"],
                "hubspot": ["contact", "lead", "deal", "customer"],
                "notion": ["note", "page", "document", "record"],
                "twilio_sms": ["user", "customer", "booking", "appointment"],
            }
            hints = _ENTITY_HINTS.get(integration_id, [])
            for hint in hints:
                for entity in arch_entities:
                    if hint.lower() in entity.lower():
                        return entity
            # Fallback: return first entity or generic name
            return arch_entities[0] if arch_entities else "Record"

        skeletons = []
        for integ_id in requested:
            integ_id_lower = integ_id.lower().strip()
            integration = get_integration(integ_id_lower)
            if not integration:
                logger.warning(
                    "[session:%s] Requested integration %r not in registry — skipping.",
                    session.session_id,
                    integ_id,
                )
                continue
            action_id = _ACTION_PRIORITY.get(
                integ_id_lower,
                integration.actions[0].id if integration.actions else None,
            )
            if not action_id:
                continue
            entity = _best_entity(integ_id_lower)
            event = _EVENT_DEFAULT.get(integ_id_lower, "status_changed")
            skeleton = {
                "name": f"Trigger {integration.display_name} on {entity} {event.replace(chr(95), chr(32))}",
                "trigger": {"entity": entity, "event": event, "condition": None},
                "integration_id": integ_id_lower,
                "action_id": action_id,
                "payload_mapping": {},
                "description": "",
                "is_valid": True,
            }
            skeletons.append(skeleton)
            logger.info(
                "[session:%s] Stub skeleton: %s -> %s.%s",
                session.session_id,
                entity,
                integ_id_lower,
                action_id,
            )

        if not skeletons:
            logger.warning(
                "[session:%s] No valid skeletons generated.", session.session_id
            )
            return []

        # STEP 2 — LLM enrichment
        # Build registry summary for the LLM (only requested integrations)
        registry_summary = {}
        for integ_id in [s["integration_id"] for s in skeletons]:
            integ = get_integration(integ_id)
            if integ:
                registry_summary[integ_id] = {
                    "actions": [
                        {"id": a.id, "input_fields": [f.name for f in a.input_schema]}
                        for a in integ.actions
                    ]
                }

        # Compact entity schemas for payload mapping context
        entity_schemas_compact = _compact(session.db_schema or {})

        enriched_raw = await _kickoff_task(
            "task_generate_workflow_stubs",
            {
                "integration_registry": json.dumps(registry_summary),
                "stub_skeletons": json.dumps(skeletons),
                "entity_schemas": entity_schemas_compact,
                "user_prompt": session.prompt[:300],
            },
        )

        # LLM may return a dict wrapper or a list directly
        if isinstance(enriched_raw, dict):
            enriched_list = enriched_raw.get(
                "workflow_stubs",
                enriched_raw.get(
                    "stubs", list(enriched_raw.values())[0] if enriched_raw else []
                ),
            )
        elif isinstance(enriched_raw, list):
            enriched_list = enriched_raw
        else:
            enriched_list = skeletons  # fallback to deterministic skeletons

        # STEP 3 — Validation: drop invalid stubs, coerce to WorkflowStub models
        validated_stubs = []
        for stub_data in enriched_list:
            if not isinstance(stub_data, dict):
                continue
            integ_id = stub_data.get("integration_id", "")
            act_id = stub_data.get("action_id", "")
            # Registry validation — deterministic
            action = get_action(integ_id, act_id)
            if not action:
                logger.warning(
                    "[session:%s] Stub dropped — invalid registry ref %s.%s",
                    session.session_id,
                    integ_id,
                    act_id,
                )
                continue
            # Ensure trigger is a dict before passing to Pydantic
            trigger_data = stub_data.get("trigger", {})
            if not isinstance(trigger_data, dict):
                trigger_data = {
                    "entity": "Record",
                    "event": "created",
                    "condition": None,
                }
            try:
                stub = WorkflowStub(
                    name=stub_data.get("name", f"{integ_id} workflow"),
                    trigger=WorkflowTrigger(**trigger_data),
                    integration_id=integ_id,
                    action_id=act_id,
                    payload_mapping=stub_data.get("payload_mapping", {}),
                    description=stub_data.get("description", ""),
                    is_valid=True,
                )
                validated_stubs.append(stub)
            except Exception as e:
                logger.warning(
                    "[session:%s] Stub validation failed: %s — %s",
                    session.session_id,
                    stub_data.get("name", ""),
                    e,
                )

        logger.info(
            "[session:%s] Workflow stubs generated: %d valid, %d dropped.",
            session.session_id,
            len(validated_stubs),
            len(enriched_list) - len(validated_stubs),
        )
        return validated_stubs

    # Run workflow stubs stage (only fires if integrations were requested)
    _workflow_stubs_result = await _run_stage(
        session, "workflow_stubs", _stage_workflow_stubs()
    )
    # _run_stage returns a dict on error, list on success — handle both
    if isinstance(_workflow_stubs_result, list):
        session.workflow_stubs = _workflow_stubs_result
    else:
        session.workflow_stubs = []

    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3.5 — Workflow Stub Generation
    # Runs only when integrations were requested in the user prompt.
    # Deterministic skeletons + LLM enrichment + registry validation.
    # ─────────────────────────────────────────────────────────────────────────
    from compiler.integrations.registry import get_action, get_integration
    from compiler.schemas.contracts import WorkflowStub, WorkflowTrigger

    async def _stage_workflow_stubs() -> list:
        requested = (session.intent or {}).get("integrations", [])
        if not requested:
            logger.info(
                "[session:%s] No integrations requested — skipping workflow stubs.",
                session.session_id,
            )
            return []

        logger.info(
            "[session:%s] Generating workflow stubs for: %s",
            session.session_id,
            requested,
        )

        # Priority action per integration (deterministic skeleton)
        _ACTION_PRIORITY = {
            "slack": "send_message",
            "gmail": "send_email",
            "stripe": "create_customer",
            "whatsapp": "send_template_message",
            "webhook": "post_payload",
            "jira": "create_issue",
            "google_sheets": "append_row",
            "hubspot": "create_contact",
            "notion": "create_page",
            "twilio_sms": "send_sms",
        }
        _EVENT_DEFAULT = {
            "slack": "status_changed",
            "gmail": "created",
            "stripe": "created",
            "whatsapp": "status_changed",
            "webhook": "created",
            "jira": "created",
            "google_sheets": "updated",
            "hubspot": "updated",
            "notion": "created",
            "twilio_sms": "status_changed",
        }
        _ENTITY_HINTS = {
            "slack": ["task", "deal", "issue", "ticket", "order"],
            "gmail": ["order", "user", "customer", "invoice", "booking"],
            "stripe": ["user", "customer", "subscription", "payment", "order"],
            "whatsapp": ["deal", "order", "booking", "appointment", "lead"],
            "webhook": ["event", "record", "item"],
            "jira": ["task", "issue", "bug", "ticket"],
            "google_sheets": ["report", "record", "entry"],
            "hubspot": ["contact", "lead", "deal", "customer"],
            "notion": ["note", "page", "document"],
            "twilio_sms": ["user", "customer", "booking", "appointment"],
        }

        arch = session.architecture or {}
        arch_entities = []
        raw_entities = (
            arch.get("entities", [])
            if isinstance(arch, dict)
            else getattr(arch, "entities", [])
        )
        for e in raw_entities:
            name = e.get("name", "") if isinstance(e, dict) else getattr(e, "name", "")
            if name:
                arch_entities.append(name)

        def _best_entity(integ_id: str) -> str:
            hints = _ENTITY_HINTS.get(integ_id, [])
            for hint in hints:
                for entity in arch_entities:
                    if hint.lower() in entity.lower():
                        return entity
            return arch_entities[0] if arch_entities else "Record"

        # Build deterministic skeletons
        skeletons = []
        for integ_id in requested:
            iid = integ_id.lower().strip()
            integration = get_integration(iid)
            if not integration:
                logger.warning(
                    "[session:%s] Integration %r not in registry — skipped.",
                    session.session_id,
                    iid,
                )
                continue
            action_id = _ACTION_PRIORITY.get(iid) or (
                integration.actions[0].id if integration.actions else None
            )
            if not action_id:
                continue
            entity = _best_entity(iid)
            event = _EVENT_DEFAULT.get(iid, "status_changed")
            skeletons.append(
                {
                    "name": f"Trigger {integration.display_name} when {entity} {event.replace(chr(95), chr(32))}",
                    "trigger": {"entity": entity, "event": event, "condition": None},
                    "integration_id": iid,
                    "action_id": action_id,
                    "payload_mapping": {},
                    "description": "",
                    "is_valid": True,
                }
            )
            logger.info(
                "[session:%s] Skeleton: %s -> %s.%s",
                session.session_id,
                entity,
                iid,
                action_id,
            )

        if not skeletons:
            return []

        # LLM enrichment — add conditions, payload mappings, descriptions
        registry_summary = {}
        for s in skeletons:
            integ = get_integration(s["integration_id"])
            if integ:
                registry_summary[s["integration_id"]] = {
                    "actions": [
                        {"id": a.id, "input_fields": [f.name for f in a.input_schema]}
                        for a in integ.actions
                    ]
                }

        enriched_raw = await _kickoff_task(
            "task_generate_workflow_stubs",
            {
                "integration_registry": json.dumps(registry_summary),
                "stub_skeletons": json.dumps(skeletons),
                "entity_schemas": _compact(session.db_schema or {}),
                "user_prompt": session.prompt[:300],
            },
        )

        # Normalise LLM output — may return list or dict wrapper
        if isinstance(enriched_raw, list):
            enriched_list = enriched_raw
        elif isinstance(enriched_raw, dict):
            for key in ("workflow_stubs", "stubs", "workflowStubs"):
                if key in enriched_raw:
                    enriched_list = enriched_raw[key]
                    break
            else:
                enriched_list = skeletons  # fallback to deterministic
        else:
            enriched_list = skeletons

        # Validate every stub against registry — drop invalid refs
        validated = []
        for stub_data in enriched_list:
            if not isinstance(stub_data, dict):
                continue
            iid = stub_data.get("integration_id", "")
            aid = stub_data.get("action_id", "")
            if not get_action(iid, aid):
                logger.warning(
                    "[session:%s] Stub dropped — bad registry ref %s.%s",
                    session.session_id,
                    iid,
                    aid,
                )
                continue
            trigger_data = stub_data.get("trigger", {})
            if not isinstance(trigger_data, dict):
                trigger_data = {
                    "entity": "Record",
                    "event": "created",
                    "condition": None,
                }
            try:
                stub = WorkflowStub(
                    name=stub_data.get("name", f"{iid} workflow"),
                    trigger=WorkflowTrigger(**trigger_data),
                    integration_id=iid,
                    action_id=aid,
                    payload_mapping=stub_data.get("payload_mapping", {}),
                    description=stub_data.get("description", ""),
                    is_valid=True,
                )
                validated.append(stub)
            except Exception as e:
                logger.warning(
                    "[session:%s] Stub Pydantic error: %s", session.session_id, e
                )

        logger.info(
            "[session:%s] Workflow stubs: %d valid, %d dropped.",
            session.session_id,
            len(validated),
            len(enriched_list) - len(validated),
        )
        return validated

    _wf_result = await _run_stage(session, "workflow_stubs", _stage_workflow_stubs())
    session.workflow_stubs = _wf_result if isinstance(_wf_result, list) else []

    # ── Build integration hooks deterministically from validated stubs ────────
    # One hook per unique (integration_id, action_id) pair. No LLM call.
    def _build_integration_hooks(stubs: list) -> list:
        """
        Derive IntegrationHook objects from validated workflow stubs.
        Deterministic: reads auth_type and required_inputs directly from REGISTRY.
        Deduplicates by hook_id = hook_{integration_id}_{action_id}.
        """
        from compiler.integrations.registry import get_action, get_integration
        from compiler.schemas.contracts import IntegrationHook

        seen: dict[str, IntegrationHook] = {}
        for stub in stubs:
            iid = (
                stub.integration_id
                if hasattr(stub, "integration_id")
                else stub.get("integration_id", "")
            )
            aid = (
                stub.action_id
                if hasattr(stub, "action_id")
                else stub.get("action_id", "")
            )
            hook_id = f"hook_{iid}_{aid}"
            if hook_id in seen:
                continue  # already built this hook

            integration = get_integration(iid)
            action = get_action(iid, aid)

            if not integration or not action:
                # Build an invalid hook so the validator can report it
                seen[hook_id] = IntegrationHook(
                    hook_id=hook_id,
                    integration_id=iid,
                    action_id=aid,
                    auth_type="unknown",
                    required_inputs=[],
                    is_stub=True,
                    validation_status="invalid",
                    validation_errors=[
                        f"integration_id={iid!r} or action_id={aid!r} not found in registry"
                    ],
                )
                continue

            required_inputs = [f.name for f in action.input_schema if f.required]
            v_status = "stub" if integration.is_stub else "valid"

            seen[hook_id] = IntegrationHook(
                hook_id=hook_id,
                integration_id=iid,
                action_id=aid,
                auth_type=integration.auth_type,
                required_inputs=required_inputs,
                is_stub=integration.is_stub,
                validation_status=v_status,
                validation_errors=[],
            )
            logger.info(
                "[session:%s] IntegrationHook built: %s (status=%s)",
                session.session_id,
                hook_id,
                v_status,
            )

        return list(seen.values())

    # Attach hook_id back onto each stub (normalised reference)
    updated_stubs = []
    for stub in session.workflow_stubs:
        hook_id = f"hook_{stub.integration_id}_{stub.action_id}"
        # Re-create stub with hook_id set (WorkflowStub is immutable Pydantic model)
        updated_stubs.append(stub.model_copy(update={"hook_id": hook_id}))
    session.workflow_stubs = updated_stubs

    session.integration_hooks = _build_integration_hooks(session.workflow_stubs)
    logger.info(
        "[session:%s] Integration hooks built: %d hooks for %d stubs.",
        session.session_id,
        len(session.integration_hooks),
        len(session.workflow_stubs),
    )

    # STAGE 4 + 5 — Validation + Repair loop
    # ─────────────────────────────────────────────────────────────────────────
    # Track the best (most complete) validation report seen across all attempts.
    # If a later validation returns {} (parse failure), we keep the best one.
    _best_validation: dict = {}

    for attempt in range(1, MAX_REPAIR_LOOPS + 1):
        # Use _outline() (ultra-compact) rather than _compact() for all_schemas.
        # Validation only needs structural info (table names, endpoint paths, roles) —
        # not full column/field details — to detect cross-layer mismatches.
        all_schemas_json = _outline(
            {
                "db_schema": session.db_schema,
                "api_schema": session.api_schema,
                "ui_schema": session.ui_schema,
                "auth_schema": session.auth_schema,
            }
        )
        logger.info(
            "[session:%s] Validation attempt %d/%d.",
            session.session_id,
            attempt,
            MAX_REPAIR_LOOPS,
        )

        async def _stage_validate() -> dict:
            result = await _kickoff_task(
                "task_validate_schemas",
                {
                    "all_schemas": all_schemas_json,
                    "user_prompt": session.prompt,
                },
            )
            session.validation_report = result
            is_valid = result.get("is_valid", False)
            error_count = len(result.get("errors", []))
            logger.info(
                "[session:%s] Validation result: is_valid=%s errors=%d warnings=%d",
                session.session_id,
                is_valid,
                error_count,
                len(result.get("warnings", [])),
            )
            return result

        validation = await _run_stage(session, "validation", _stage_validate())

        # Derive validity from errors array — LLM's is_valid flag is unreliable.
        # Also treat empty {} as a parse failure (validator didn't return a proper report).
        errors = validation.get("errors", [])
        is_empty_report = not validation or (
            not errors
            and not validation.get("warnings")
            and not validation.get("validated_at")
        )
        effective_is_valid = len(errors) == 0 and not is_empty_report

        # Track the best validation report — prefer a real report with content over {}.
        # This ensures session.validation_report is always the most informative result
        # even if a later parse attempt returns empty.
        if not is_empty_report and len(errors) + len(
            validation.get("warnings", [])
        ) > len(
            _best_validation.get("errors", []) + _best_validation.get("warnings", [])
        ):
            _best_validation = validation
        if not is_empty_report and not _best_validation:
            _best_validation = validation
        # Always expose the best known report in session
        if _best_validation:
            session.validation_report = _best_validation

        if is_empty_report:
            logger.warning(
                "[session:%s] Validation returned empty report on attempt %d — treating as failed parse, triggering repair.",
                session.session_id,
                attempt,
            )
        elif effective_is_valid:
            logger.info(
                "[session:%s] Schemas valid after attempt %d (0 errors).",
                session.session_id,
                attempt,
            )
            break

        errors = validation.get("errors", [])
        logger.warning(
            "[session:%s] Validation FAILED. %d errors. Triggering repair (attempt %d).",
            session.session_id,
            len(errors),
            attempt,
        )

        await _emit(
            session,
            "stage_update",
            {
                "stage": "validation",
                "status": "repair_triggered",
                "model": session.stage_models.get(
                    "validation", model_for_stage("validation")[0]
                ),
                "latency_ms": session.stage_latencies.get("validation", 0),
                "output_summary": f"{len(errors)} errors found",
                "conflicts": [
                    e.get("description", "") for e in validation.get("conflicts", [])
                ],
            },
        )

        # If same errors persist after 2 attempts, escalate to HITL
        # Only escalate on real errors — not on empty reports (those are parse failures).
        if attempt >= 2 and not is_empty_report and errors:
            unresolved = [e.get("description", str(e)) for e in errors[:3]]
            logger.warning(
                "[session:%s] Repair attempt %d — escalating to HITL. unresolved=%s",
                session.session_id,
                attempt,
                unresolved,
            )
            await _wait_for_hitl(
                session,
                stage="repair",
                trigger_reason="repair_failed",
                questions=[
                    f"Repair attempt {attempt} could not fix: {err}. "
                    f"How should this be resolved?"
                    for err in unresolved
                ],
                timeout_seconds=HITL_TIMEOUT_SECONDS,
            )

        async def _stage_repair() -> dict:
            result = await _kickoff_task(
                "task_repair_schemas",
                {
                    "validation_report": _compact(session.validation_report),
                    # Repair needs _compact (field-level detail) not _outline
                    # (name-only) because the repair agent must patch specific
                    # column constraints, endpoint validation rules, etc.
                    "all_schemas": _compact(
                        {
                            "db_schema": session.db_schema,
                            "api_schema": session.api_schema,
                            "ui_schema": session.ui_schema,
                            "auth_schema": session.auth_schema,
                        }
                    ),
                    "repair_attempt_number": attempt,
                    "user_prompt": session.prompt,
                },
            )
            session.repair_report = result
            session.repair_count += 1

            # --- Feature F: classify repair strategy and log outcome ---
            # FIELD repair: if errors are field-type, attempt narrow re-prompt
            _field_errors = [
                e
                for e in (session.validation_report or {}).get("errors", [])
                if isinstance(e, dict)
                and "field"
                in e.get("layer", "").lower() + e.get("description", "").lower()
            ]
            if _field_errors and attempt == 1:
                for _fe in _field_errors[
                    :2
                ]:  # re-prompt up to 2 field errors in isolation
                    _field_desc = _fe.get("description", "")
                    _field_name = _fe.get("field", "unknown_field")
                    logger.info(
                        "[session:%s] FIELD repair: re-prompting field=%s",
                        session.session_id,
                        _field_name,
                    )
                    try:
                        _narrow_result = await _kickoff_task(
                            "task_repair_schemas",
                            {
                                "validation_report": f'{{"errors": [{json.dumps(_fe)}]}}',
                                "all_schemas": _compact(
                                    {
                                        "db_schema": session.db_schema,
                                        "api_schema": session.api_schema,
                                    }
                                ),
                                "repair_attempt_number": attempt,
                                "user_prompt": f"Fix only this field error: {_field_desc}",
                            },
                        )
                        _narrow_updated = _narrow_result.get("updated_schemas", {})
                        for _k in {"db_schema", "api_schema"} & set(
                            _narrow_updated.keys()
                        ):
                            if isinstance(_narrow_updated[_k], dict):
                                setattr(session, _k, _narrow_updated[_k])
                                logger.info(
                                    "[session:%s] FIELD repair applied to %s",
                                    session.session_id,
                                    _k,
                                )
                    except Exception as _fe_exc:
                        logger.warning(
                            "[session:%s] FIELD narrow re-prompt failed: %s",
                            session.session_id,
                            _fe_exc,
                        )
            errors_before = len((session.validation_report or {}).get("errors", []))
            strategy = _classify_repair_strategy(
                errors=(session.validation_report or {}).get("errors", []),
                validation_report=session.validation_report or {},
                attempt=attempt,
            )
            unresolved = result.get("unresolved_errors", [])
            errors_after = len(unresolved)
            outcome = (
                "escalated"
                if strategy == "ESCALATED"
                else "repaired" if errors_after < errors_before else "failed"
            )
            log_entry = {
                "attempt_number": attempt,
                "strategy": strategy,
                "error_input": "; ".join(
                    e.get("description", str(e)) if isinstance(e, dict) else str(e)
                    for e in (session.validation_report or {}).get("errors", [])[:3]
                ),
                "outcome": outcome,
                "errors_before": errors_before,
                "errors_after": errors_after,
            }
            if not hasattr(session, "repair_log"):
                session.repair_log = []
            session.repair_log.append(log_entry)
            logger.info(
                "[session:%s] Repair attempt=%d strategy=%s outcome=%s errors=%d->%d",
                session.session_id,
                attempt,
                strategy,
                outcome,
                errors_before,
                errors_after,
            )
            logger.info(
                "[session:%s] Repair complete. repairs=%d unresolved=%d",
                session.session_id,
                len(result.get("repairs", [])),
                len(result.get("unresolved_errors", [])),
            )
            # Merge updated schemas back into session.
            # Guard against wrong-shaped updated_schemas from the LLM, e.g.:
            #   {"schema": {...}}  instead of  {"db_schema": {...}, "api_schema": {...}}
            updated = result.get("updated_schemas", {})
            if not isinstance(updated, dict):
                logger.warning(
                    "[session:%s] Repair returned non-dict updated_schemas (type=%s). Ignoring.",
                    session.session_id,
                    type(updated).__name__,
                )
                updated = {}
            elif set(updated.keys()) == {"schema"}:
                logger.warning(
                    "[session:%s] Repair returned updated_schemas wrapped under 'schema' key "
                    "(wrong format) — skipping merge to preserve valid original schemas.",
                    session.session_id,
                )
                updated = {}

            for key in {
                "db_schema",
                "api_schema",
                "ui_schema",
                "auth_schema",
            } & updated.keys():
                value = updated[key]
                if isinstance(value, dict):
                    # Guard against repair truncating schemas — only accept the
                    # repaired version if it has at least as many top-level items
                    # as the current session schema. This prevents the repair
                    # agent from replacing a 12-endpoint api_schema with 4 endpoints.
                    current = getattr(session, key, {}) or {}
                    # Count representative items per schema type
                    count_key = {
                        "db_schema": "tables",
                        "api_schema": "endpoints",
                        "ui_schema": "pages",
                        "auth_schema": "roles",
                    }.get(key)
                    if count_key:
                        current_count = len(current.get(count_key, []))
                        repair_count = len(value.get(count_key, []))
                        if repair_count < current_count:
                            logger.warning(
                                "[session:%s] Repair returned truncated %s "
                                "(%d %s vs current %d) — skipping merge to preserve original.",
                                session.session_id,
                                key,
                                repair_count,
                                count_key,
                                current_count,
                            )
                            continue
                    setattr(session, key, value)
                    logger.debug(
                        "[session:%s] %s updated by repair.", session.session_id, key
                    )
                else:
                    logger.warning(
                        "[session:%s] Repair returned non-dict for %s (type=%s). Skipping.",
                        session.session_id,
                        key,
                        type(value).__name__,
                    )
            # Rebuild all_schemas_json for next validation pass
            return result

        await _run_stage(session, "repair", _stage_repair())

        # Rebuild outline for next validation pass
        all_schemas_json = _outline(
            {
                "db_schema": session.db_schema,
                "api_schema": session.api_schema,
                "ui_schema": session.ui_schema,
                "auth_schema": session.auth_schema,
            }
        )

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 6 — Runtime Validation
    # ─────────────────────────────────────────────────────────────────────────
    async def _stage_runtime() -> dict:
        result = await _kickoff_task(
            "task_validate_runtime",
            {
                "all_schemas": _outline(
                    {
                        "db_schema": session.db_schema,
                        "api_schema": session.api_schema,
                        "ui_schema": session.ui_schema,
                        "auth_schema": session.auth_schema,
                    }
                ),
                "validation_report": _compact(session.validation_report),
                "user_prompt": session.prompt,
            },
        )
        session.runtime_report = result
        viable = result.get("execution_viable", False)
        logger.info(
            "[session:%s] Runtime validation: viable=%s flows=%d blocking=%d",
            session.session_id,
            viable,
            len(result.get("simulated_flows", [])),
            len(result.get("blocking_issues", [])),
        )
        return result

    await _run_stage(session, "runtime_validation", _stage_runtime())

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 7 — Progress Logging + Mermaid generation
    # ─────────────────────────────────────────────────────────────────────────
    async def _stage_logging() -> dict:
        result = await _kickoff_task(
            "task_log_progress",
            {
                # Include all stage latencies (schema stages now tracked too)
                "stage_latencies": json.dumps(session.stage_latencies),
                "repair_count": session.repair_count,
                "hitl_count": session.hitl_count,
                "user_prompt": session.prompt[:200],
                "session_id": session.session_id,
                "db_outline": (
                    _outline(session.db_schema)
                    if session.db_schema
                    else "No DB schema generated"
                ),
                "api_outline": (
                    _outline(session.api_schema)
                    if session.api_schema
                    else "No API schema generated"
                ),
            },
        )
        # Sanitize Mermaid diagrams before storing — fix LLM syntax mistakes
        for key, hint in [
            ("mermaid_pipeline", "flowchart"),
            ("mermaid_er", "er"),
            ("mermaid_sequence", "sequence"),
        ]:
            if key in result and result[key]:
                result[key] = _sanitize_mermaid(result[key], diagram_hint=hint)
        session.log_output = result
        logger.info(
            "[session:%s] Logging complete. mermaid keys=%s",
            session.session_id,
            [k for k in result if "mermaid" in k],
        )
        # Stream log entries as SSE
        for entry in result.get("log_entries", []):
            await _emit(
                session,
                "log_update",
                {
                    "content": (
                        json.dumps(entry) if isinstance(entry, dict) else str(entry)
                    ),
                },
            )
        return result

    await _run_stage(session, "logging", _stage_logging())

    # ─────────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    # STAGE D — Build unified AppSpec (pure Python assembly, zero LLM calls)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_app_spec() -> Optional[dict]:
        from compiler.schemas.contracts import (
            AppSpec,
            AppSpecAuthRules,
            AppSpecEndpoint,
            AppSpecEntity,
            AppSpecMeta,
            AppSpecPage,
        )

        intent = session.intent or {}
        app_type = (
            intent.get("app_type", "custom")
            if isinstance(intent, dict)
            else getattr(intent, "app_type", "custom")
        )
        features = (
            intent.get("features", [])
            if isinstance(intent, dict)
            else getattr(intent, "features", [])
        )
        assumptions = (
            intent.get("assumptions", [])
            if isinstance(intent, dict)
            else getattr(intent, "assumptions", [])
        )
        meta = AppSpecMeta(
            app_name=(
                intent.get("app_name", "")
                if isinstance(intent, dict)
                else getattr(intent, "app_name", "")
            )
            or str(app_type).replace("_", " ").title(),
            app_type=str(app_type),
            description=session.prompt[:200],
            features=features if isinstance(features, list) else [],
            assumptions=assumptions if isinstance(assumptions, list) else [],
        )
        arch = session.architecture or {}
        arch_entities_raw = (
            arch.get("entities", [])
            if isinstance(arch, dict)
            else getattr(arch, "entities", [])
        )
        arch_entity_names = []
        for e in arch_entities_raw:
            n = e.get("name", "") if isinstance(e, dict) else getattr(e, "name", "")
            if n:
                arch_entity_names.append(n)
        db = session.db_schema or {}
        tables_raw = (
            db.get("tables", []) if isinstance(db, dict) else getattr(db, "tables", [])
        )

        def _tbl(entity_name):
            el = entity_name.lower().replace(" ", "_")
            for t in tables_raw:
                tn = (
                    t.get("name", "") if isinstance(t, dict) else getattr(t, "name", "")
                )
                if (
                    tn.lower() in (el, el + "s", el.rstrip("s"))
                    or el in tn.lower()
                    or tn.lower() in el
                ):
                    return t
            return {}

        entities = []
        for name in arch_entity_names:
            tbl = _tbl(name)
            tname = (
                tbl.get("name", name.lower() + "s")
                if isinstance(tbl, dict)
                else getattr(tbl, "name", name.lower() + "s")
            )
            cols = (
                tbl.get("columns", [])
                if isinstance(tbl, dict)
                else getattr(tbl, "columns", [])
            )
            fields = [
                c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
                for c in cols
            ]
            fields = [f for f in fields if f]
            fks = (
                tbl.get("foreign_keys", [])
                if isinstance(tbl, dict)
                else getattr(tbl, "foreign_keys", [])
            )
            rels = []
            for fk in fks:
                col = (
                    fk.get("column", "")
                    if isinstance(fk, dict)
                    else getattr(fk, "column", "")
                )
                ref = (
                    fk.get("references_table", "")
                    if isinstance(fk, dict)
                    else getattr(fk, "references_table", "")
                )
                if col and ref:
                    rels.append(f"belongs to {ref} via {col}")
            entities.append(
                AppSpecEntity(
                    name=name, table_name=tname, fields=fields, relations=rels
                )
            )
        ui = session.ui_schema or {}
        pages_raw = (
            ui.get("pages", []) if isinstance(ui, dict) else getattr(ui, "pages", [])
        )
        pages = []
        for p in pages_raw:
            pth = p.get("path", "") if isinstance(p, dict) else getattr(p, "path", "")
            ttl = p.get("title", "") if isinstance(p, dict) else getattr(p, "title", "")
            role = (
                p.get("role_required")
                if isinstance(p, dict)
                else getattr(p, "role_required", None)
            )
            bound = None
            pl = pth.lower().replace("-", "_").replace("/", "_")
            for en in arch_entity_names:
                if en.lower().rstrip("s") in pl or en.lower() in pl:
                    bound = en
                    break
            # Derive layout from page path heuristics
            layout = "list"
            if any(kw in pth.lower() for kw in [":id", "/detail", "/view", "/edit"]):
                layout = "detail"
            elif any(
                kw in pth.lower()
                for kw in ["/dashboard", "/analytics", "/report", "/overview"]
            ):
                layout = "dashboard"
            elif any(
                kw in pth.lower()
                for kw in ["/settings", "/profile", "/config", "/preferences"]
            ):
                layout = "settings"
            pages.append(
                AppSpecPage(
                    path=pth,
                    title=ttl,
                    role_required=role,
                    bound_entity=bound,
                    layout=layout,
                )
            )
        api = session.api_schema or {}
        eps_raw = (
            api.get("endpoints", [])
            if isinstance(api, dict)
            else getattr(api, "endpoints", [])
        )
        api_endpoints = []
        for ep in eps_raw:
            m = (
                ep.get("method", "GET")
                if isinstance(ep, dict)
                else getattr(ep, "method", "GET")
            )
            pth = (
                ep.get("path", "") if isinstance(ep, dict) else getattr(ep, "path", "")
            )
            ar = (
                ep.get("auth_required", True)
                if isinstance(ep, dict)
                else getattr(ep, "auth_required", True)
            )
            rr = (
                ep.get("required_role")
                if isinstance(ep, dict)
                else getattr(ep, "required_role", None)
            )
            if pth:
                # Derive handler description from method + path
                handler_desc = (
                    ep.get("description", "")
                    if isinstance(ep, dict)
                    else getattr(ep, "description", "")
                )
                if not handler_desc:
                    handler_desc = f"{m} {pth}"
                # Rate limit flag: POST/PUT endpoints or paths with /upload /export
                rate_limit = any(
                    kw in str(pth).lower()
                    for kw in ["/upload", "/export", "/bulk", "/import"]
                )
                if (
                    str(m).upper() in ("POST", "PUT", "PATCH")
                    and "admin" in str(rr or "").lower()
                ):
                    rate_limit = True
                api_endpoints.append(
                    AppSpecEndpoint(
                        method=str(m),
                        path=str(pth),
                        auth_required=bool(ar),
                        required_role=rr,
                        handler_description=handler_desc,
                        rate_limit_flag=rate_limit,
                    )
                )
        auth = session.auth_schema or {}
        strat = (
            auth.get("auth_strategy", "jwt")
            if isinstance(auth, dict)
            else getattr(auth, "auth_strategy", "jwt")
        )
        roles = (
            auth.get("roles", [])
            if isinstance(auth, dict)
            else getattr(auth, "roles", [])
        )
        auth_rules = AppSpecAuthRules(
            auth_strategy=str(strat), roles=roles if isinstance(roles, list) else []
        )
        try:
            spec = AppSpec(
                meta=meta,
                entities=entities,
                pages=pages,
                api_endpoints=api_endpoints,
                auth_rules=auth_rules,
                integration_hooks=session.integration_hooks or [],
                workflow_stubs=session.workflow_stubs or [],
            )
            logger.info(
                "[session:%s] AppSpec: %d entities, %d pages, %d endpoints, %d hooks, %d stubs.",
                session.session_id,
                len(entities),
                len(pages),
                len(api_endpoints),
                len(session.integration_hooks or []),
                len(session.workflow_stubs or []),
            )
            return spec.model_dump()
        except Exception as e:
            logger.error(
                "[session:%s] AppSpec assembly error: %s", session.session_id, e
            )
            return None

    session.app_spec = _build_app_spec()

    # STAGE 8 — pipeline_complete SSE event
    # ─────────────────────────────────────────────────────────────────────────
    total_ms = session.elapsed_ms()
    log_out = session.log_output or {}

    mermaid = {
        "pipeline_flow": _sanitize_mermaid(
            log_out.get("mermaid_pipeline", ""), "flowchart"
        ),
        "er_diagram": _sanitize_mermaid(log_out.get("mermaid_er", ""), "er"),
        "api_sequence": _sanitize_mermaid(
            log_out.get("mermaid_sequence", ""), "sequence"
        ),
    }

    final_schema = {
        "session_id": session.session_id,
        "prompt": session.prompt,
        "intent": session.intent,
        "architecture": session.architecture,
        "db_schema": session.db_schema,
        "api_schema": session.api_schema,
        "ui_schema": session.ui_schema,
        "auth_schema": session.auth_schema,
        "validation_report": session.validation_report,
        "repair_report": session.repair_report,
        "runtime_report": session.runtime_report,
        "workflow_stubs": [
            s.model_dump() if hasattr(s, "model_dump") else s
            for s in (session.workflow_stubs or [])
        ],
        "integration_hooks": [
            h.model_dump() if hasattr(h, "model_dump") else h
            for h in (session.integration_hooks or [])
        ],
        "app_spec": session.app_spec,
        "repair_log": getattr(session, "repair_log", []),
    }

    from compiler.schemas.contracts import FinalOutput

    try:
        FinalOutput.model_validate(final_schema)
        logger.info(
            "[session:%s] FinalOutput Pydantic validation passed.", session.session_id
        )
    except Exception as e:
        logger.warning(
            "[session:%s] FinalOutput Pydantic validation failed (non-blocking): %s",
            session.session_id,
            e,
        )

    # Emit generation_complete as alias (assignment requirement)
    await _emit(
        session,
        "generation_complete",
        {
            "total_latency_ms": total_ms,
            "session_id": session.session_id,
        },
    )
    await _emit(
        session,
        "pipeline_complete",
        {
            "total_latency_ms": total_ms,
            "total_tokens": session.total_tokens,
            "repair_count": session.repair_count,
            "hitl_count": session.hitl_count,
            "final_schema": final_schema,
            "mermaid_diagrams": mermaid,
            "assumptions": (
                session.intent.get("assumptions", []) if session.intent else []
            ),
            "conflicts": (
                session.validation_report.get("conflicts", [])
                if session.validation_report
                else []
            ),
        },
    )

    # Signal SSE stream to close
    await session.sse_queue.put(None)

    logger.info(
        "[session:%s] Pipeline COMPLETE. total_ms=%d repairs=%d hitl=%d",
        session.session_id,
        total_ms,
        session.repair_count,
        session.hitl_count,
    )
