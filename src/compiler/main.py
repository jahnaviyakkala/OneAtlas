"""
main.py — ProtoFlow FastAPI Application
────────────────────────────────────────
Entry point for the backend server.

Routes:
  POST /generate          — start a pipeline run, returns session_id
  GET  /stream/{id}       — SSE stream of all pipeline events
  POST /clarify           — resume pipeline after HITL
  GET  /result/{id}       — full FinalOutput JSON
  GET  /logs/{id}         — markdown log as plain text
  GET  /health            — health check

All route handlers are async. All file I/O uses aiofiles.
All LLM calls go through Groq via crewai LiteLLM routing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.config
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import aiofiles
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from compiler.schemas.contracts import ClarifyRequest, ModifyRequest
from compiler.crew import _sanitize_mermaid
from compiler.tools.routing import routing_summary

# ── Load .env before anything else ───────────────────────────────────────────
load_dotenv()

# ── Fix: Disable CrewAI prompt cache_breakpoint injection ─────────────────────
# CrewAI injects a 'cache_breakpoint' key into system messages for Anthropic
# prompt caching. Groq does not support this property and rejects it with:
#   "property 'cache_breakpoint' is unsupported"
# This monkey-patch disables the injection entirely.
try:
    import crewai.llms.cache as _crewai_cache
    _crewai_cache.mark_cache_breakpoint = lambda msg: msg  # no-op
except (ImportError, AttributeError):
    pass  # If the module doesn't exist in this version, no action needed

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "debug").upper()

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "detailed",
        },
    },
    "root": {
        "level": LOG_LEVEL,
        "handlers": ["console"],
    },
    "loggers": {
        "protoflow": {"level": LOG_LEVEL, "propagate": True},
        "uvicorn": {"level": "INFO", "propagate": True},
        "crewai": {"level": "INFO", "propagate": True},
    },
})

logger = logging.getLogger("protoflow.main")

# ── Startup key validation ────────────────────────────────────────────────────
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
_GROQ_KEY = os.getenv("GROQ_API_KEY", "")

if not _GROQ_KEY:
    logger.warning(
        "[startup] GROQ_API_KEY is not set. All LLM calls will fail. "
        "Get a free key at https://console.groq.com and add it to .env"
    )
else:
    logger.info("[startup] GROQ_API_KEY loaded (length=%d).", len(_GROQ_KEY))

if not _OPENROUTER_KEY or _OPENROUTER_KEY == "your_openrouter_api_key_here":
    logger.info("[startup] OPENROUTER_API_KEY not set (not required — using Groq).")
else:
    logger.info("[startup] OPENROUTER_API_KEY loaded (length=%d) — kept as fallback.", len(_OPENROUTER_KEY))

from src.compiler.tools.routing import model_for_stage

# Log the model slugs being used so mismatches are caught early
# Model map is now driven by routing.yaml via model_for_stage()
logger.info("[startup] Agent model map:")
for agent_name in [
    "intent_extractor", "system_architect", "db_schema_agent", "api_schema_agent",
    "ui_schema_agent", "auth_agent", "validator_agent", "repair_agent",
    "runtime_validator", "progress_logger"
]:
    primary, fallback, _ = model_for_stage(agent_name)
    logger.info("  %-22s -> %s (fallback: %s)", agent_name, primary, fallback)

# ── Session store ─────────────────────────────────────────────────────────────
from compiler.crew import PipelineSession, run_pipeline

_session_store: dict[str, PipelineSession] = {}
_session_lock = asyncio.Lock()
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "3600"))

async def _get_session(session_id: str) -> PipelineSession:
    async with _session_lock:
        session = _session_store.get(session_id)
    if session is None:
        logger.warning("[main] Session not found: %s", session_id)
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session

async def _cleanup_expired_sessions() -> None:
    """Background task: remove sessions older than SESSION_TTL."""
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        now = time.monotonic()
        async with _session_lock:
            expired = [
                sid for sid, s in _session_store.items()
                if (now - s.started_at) > SESSION_TTL
            ]
            for sid in expired:
                session = _session_store.pop(sid)
                logger.info("[main] Expired session cleaned up: %s", sid)
        if expired:
            logger.info("[main] Cleaned up %d expired sessions.", len(expired))


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[startup] ProtoFlow backend starting up.")
    cleanup_task = asyncio.create_task(_cleanup_expired_sessions())
    yield
    cleanup_task.cancel()
    logger.info("[shutdown] ProtoFlow backend shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="ProtoFlow API",
    description="Natural language → application schema compiler",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from compiler.eval.runner import eval_router
from compiler.integrations.registry import REGISTRY
app.include_router(eval_router)



# ── Request timing middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    t0 = time.monotonic()
    response = await call_next(request)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    logger.debug(
        "[http] %s %s → %d (%dms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


# ── Request / Response models ─────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    prompt: str

class GenerateResponse(BaseModel):
    session_id: str

class ClarifyResponse(BaseModel):
    status: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/integrations")
async def get_integrations():
    """
    Return the full integration registry.
    Lists all registered integrations with their triggers, actions, and stub status.
    This is the single source of truth for valid integration IDs used in AppSpec validation.
    """
    return {
        "integrations": [integration.model_dump() for integration in REGISTRY.values()],
        "total": len(REGISTRY),
        "implemented": [k for k, v in REGISTRY.items() if not v.is_stub],
        "stubbed": [k for k, v in REGISTRY.items() if v.is_stub],
    }

@app.get("/health")
async def health():
    """Health check."""
    logger.debug("[health] ping")
    return {"status": "ok", "version": "1.0.0"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """
    Start a new pipeline run.
    Returns session_id immediately. Client then connects to GET /stream/{session_id}.
    """
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=422, detail="prompt must not be empty.")

    session_id = str(uuid.uuid4())
    session = PipelineSession(session_id=session_id, prompt=req.prompt.strip())

    async with _session_lock:
        _session_store[session_id] = session

    logger.info(
        "[generate] New session created: %s prompt_length=%d",
        session_id, len(req.prompt),
    )

    # Fire-and-forget — pipeline runs in background
    asyncio.create_task(_run_pipeline_safe(session))

    return GenerateResponse(session_id=session_id)


async def _run_pipeline_safe(session: PipelineSession) -> None:
    """Wrapper that catches top-level pipeline errors and emits a failed event."""
    try:
        await run_pipeline(session)
    except Exception as exc:
        logger.error(
            "[session:%s] Pipeline crashed: %s", session.session_id, exc, exc_info=True
        )
        try:
            await session.sse_queue.put({
                "event": "pipeline_failed",
                "session_id": session.session_id,
                "error": str(exc),
            })
            await session.sse_queue.put(None)  # close stream
        except Exception:
            pass


@app.get("/stream/{session_id}")
async def stream(session_id: str, request: Request):
    """
    SSE stream endpoint.
    Replays buffered events first (for reconnection), then streams live events.
    Closes when pipeline_complete or pipeline_failed is received.
    """
    session = await _get_session(session_id)
    logger.info("[stream] Client connected to session: %s", session_id)

    async def event_generator() -> AsyncGenerator[dict, None]:
        # Replay buffered events for reconnecting clients
        for buffered_event in session.event_buffer:
            logger.debug(
                "[stream:%s] Replaying buffered event: %s",
                session_id, buffered_event.get("event"),
            )
            yield {
                "event": buffered_event.get("event", "message"),
                "data": json.dumps(buffered_event),
            }

        # Stream live events
        while True:
            if await request.is_disconnected():
                logger.info("[stream:%s] Client disconnected.", session_id)
                break

            try:
                event = await asyncio.wait_for(session.sse_queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield {"event": "ping", "data": "keepalive"}
                continue

            if event is None:
                # Pipeline signalled completion
                logger.info("[stream:%s] Stream closing (pipeline done).", session_id)
                break

            event_type = event.get("event", "message")
            logger.debug("[stream:%s] Streaming event: %s", session_id, event_type)
            yield {
                "event": event_type,
                "data": json.dumps(event),
            }

            if event_type in ("pipeline_complete", "pipeline_failed"):
                break

    return EventSourceResponse(event_generator())


@app.post("/clarify", response_model=ClarifyResponse)
async def clarify(req: ClarifyRequest):
    """
    Resume a pipeline that is waiting for HITL input.
    Sets the asyncio.Event to unblock the pipeline.
    """
    session = await _get_session(req.session_id)
    logger.info(
        "[clarify] Received answers for session %s: %s",
        req.session_id, req.answers,
    )
    session.resume_hitl(answers=req.answers, chosen_option=req.chosen_option)
    return ClarifyResponse(status="resumed")


class RepairRequest(BaseModel):
    stage: str
    error_hint: str = ""


class RepairResponse(BaseModel):
    status: str
    session_id: str
    repair_attempt: int


class ModifyResponse(BaseModel):
    status: str
    message: str



@app.post("/generate/{session_id}/repair", response_model=RepairResponse)
async def manual_repair(session_id: str, req: RepairRequest):
    """
    Manually trigger a repair pass on a specific stage output.
    Accepts { stage, error_hint } — useful for testing the repair engine directly.
    Injects the error_hint into the repair task as an additional validation error
    and re-runs the repair stage. Does not restart the full pipeline.
    """
    session = await _get_session(session_id)

    if not session.validation_report:
        raise HTTPException(
            status_code=422,
            detail="No validation report available. Run the pipeline first."
        )

    # Build a synthetic error from the hint and inject it into the repair loop
    hint_error = {"layer": req.stage, "field": "manual", "description": req.error_hint or f"Manual repair triggered for stage: {req.stage}"}
    existing_errors = (session.validation_report or {}).get("errors", [])
    if req.error_hint:
        existing_errors = existing_errors + [hint_error]
        session.validation_report["errors"] = existing_errors

    logger.info("[manual_repair] session=%s stage=%s hint=%r", session_id, req.stage, req.error_hint)

    # Fire repair stage as a background task
    asyncio.create_task(_run_pipeline_safe(session))

    return RepairResponse(
        status="repair_queued",
        session_id=session_id,
        repair_attempt=session.repair_count + 1,
    )



@app.post("/modify", response_model=ModifyResponse)
async def modify(req: ModifyRequest):
    """
    Accept a midway modification to the running pipeline.

    The modification is stored on the session and picked up at the next stage
    boundary (before_schema_generation, before_api_schema, before_ui_schema,
    before_validation). The pipeline is NOT restarted — only future stages
    that have not yet run will incorporate the change.

    Returns immediately so the UI is not blocked.
    """
    session = await _get_session(req.session_id)

    if not req.modification or not req.modification.strip():
        raise HTTPException(status_code=422, detail="modification must not be empty.")

    if session.runtime_report is not None:
        # Pipeline already complete — no stages left to modify
        raise HTTPException(
            status_code=409,
            detail="Pipeline has already completed. Start a new session to apply changes.",
        )

    session.queue_modification(req.modification.strip())
    logger.info(
        "[modify] Modification queued for session %s: %r",
        req.session_id, req.modification[:80],
    )

    # Emit SSE immediately so the client sees acknowledgement
    import asyncio as _asyncio
    _asyncio.create_task(_emit(session, "modification_queued", {
        "modification": req.modification.strip(),
        "applied_at_stage": "pending",
    }))

    return ModifyResponse(
        status="queued",
        message="Modification queued. It will be applied at the next stage boundary.",
    )


@app.get("/result/{session_id}")
async def result(session_id: str):
    """Return the complete FinalOutput JSON for a completed session."""
    session = await _get_session(session_id)

    if session.runtime_report is None:
        logger.warning(
            "[result] Session %s pipeline not yet complete.", session_id
        )
        raise HTTPException(
            status_code=202,
            detail="Pipeline not yet complete. Poll /stream for progress.",
        )

    logger.info("[result] Returning result for session: %s", session_id)
    return {
        "session_id": session_id,
        "prompt": session.prompt,
        "original_prompt": session.original_prompt,
        "modification_history": session.modification_history,
        "intent": session.intent,
        "architecture": session.architecture,
        "db_schema": session.db_schema,
        "api_schema": session.api_schema,
        "ui_schema": session.ui_schema,
        "auth_schema": session.auth_schema,
        "validation_report": session.validation_report,
        "repair_report": session.repair_report,
        "runtime_report": session.runtime_report,
        "workflow_stubs": [s.model_dump() if hasattr(s, "model_dump") else s for s in (getattr(session, "workflow_stubs", None) or [])],
        "integration_hooks": [h.model_dump() if hasattr(h, "model_dump") else h for h in (getattr(session, "integration_hooks", None) or [])],
        "app_spec": getattr(session, "app_spec", None),
        "repair_log": getattr(session, "repair_log", []),
        "mermaid_diagrams": {
            "pipeline_flow": _sanitize_mermaid(
                (session.log_output or {}).get("mermaid_pipeline", ""), "flowchart"
            ),
            "er_diagram": _sanitize_mermaid(
                (session.log_output or {}).get("mermaid_er", ""), "er"
            ),
            "api_sequence": _sanitize_mermaid(
                (session.log_output or {}).get("mermaid_sequence", ""), "sequence"
            ),
        },
        "eval_metrics": {
            "total_latency_ms": session.elapsed_ms(),
            "total_tokens": session.total_tokens,
            "repair_count": session.repair_count,
            "hitl_count": session.hitl_count,
            "stage_latencies": session.stage_latencies,
            # Groq llama-3.3-70b-versatile: ~$0.59/M tokens (input+output blended)
            # This is an approximation for cost vs quality tradeoff analysis.
            "estimated_cost_usd": round(session.total_tokens * 0.00000059, 6),
            "stage_costs_usd": getattr(session, "stage_costs", {}),
            "stage_models_used": getattr(session, "stage_models", {}),
            "total_cost_usd": round(sum(getattr(session, "stage_costs", {}).values()), 6),
            "routing_config": routing_summary(),
        },
    }



@app.get("/logs/{session_id}", response_class=PlainTextResponse)
async def logs(session_id: str):
    """Return the markdown log file for a session as plain text."""
    session = await _get_session(session_id)
    log_path = f"backend/logs/run_{session_id}.md"

    try:
        async with aiofiles.open(log_path, "r", encoding="utf-8") as f:
            content = await f.read()
        logger.debug("[logs] Returning log file for session: %s", session_id)
        return content
    except FileNotFoundError:
        logger.warning("[logs] Log file not found for session: %s", session_id)
        # Fall back to in-memory log entries
        log_out = session.log_output or {}
        entries = log_out.get("log_entries", [])
        if entries:
            return "\n\n".join(
                json.dumps(e, indent=2) if isinstance(e, dict) else str(e)
                for e in entries
            )
        return f"# Log for session {session_id}\n\nNo log file found yet."


# ── Legacy crewai entry points (kept for `crewai run` compatibility) ──────────

def run():
    """Run the crew directly (legacy crewai CLI entry point)."""
    from compiler.crew import ProtoFlowCrew
    logger.info("[run] Starting ProtoFlow crew via legacy entry point.")
    inputs = {"user_prompt": "Build a CRM with contacts, deals, and roles."}
    ProtoFlowCrew().crew().kickoff(inputs=inputs)


def serve():
    """Start the FastAPI server with uvicorn."""
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    logger.info("[serve] Starting uvicorn on %s:%d", host, port)
    uvicorn.run("compiler.main:app", host=host, port=port, log_level=log_level, reload=True)


def train():
    import sys
    from compiler.crew import ProtoFlowCrew
    inputs = {"user_prompt": "Build a project management tool."}
    ProtoFlowCrew().crew().train(
        n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs
    )


def replay():
    import sys
    from compiler.crew import ProtoFlowCrew
    ProtoFlowCrew().crew().replay(task_id=sys.argv[1])


def test():
    import sys
    from compiler.crew import ProtoFlowCrew
    inputs = {"user_prompt": "Build an e-commerce platform."}
    ProtoFlowCrew().crew().test(
        n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs
    )


def run_with_trigger():
    import sys
    import json as _json
    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided.")
    payload = _json.loads(sys.argv[1])
    from compiler.crew import ProtoFlowCrew
    return ProtoFlowCrew().crew().kickoff(inputs={"crewai_trigger_payload": payload})


if __name__ == "__main__":
    serve()
