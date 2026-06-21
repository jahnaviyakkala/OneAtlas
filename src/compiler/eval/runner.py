import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from compiler.crew import PipelineSession, run_pipeline
from compiler.eval.recorder import (
    EVAL_RESULTS_PATH,
    record_auto_metrics,
    update_human_judgment,
)

logger = logging.getLogger("protoflow.eval.runner")

eval_router = APIRouter(prefix="/eval")

# Path to prompts.json
PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "prompts.json")
ASSIGNMENT_PROMPTS_PATH = os.path.join(
    os.path.dirname(__file__), "assignment_prompts.json"
)


# Request Models
class RecordJudgmentRequest(BaseModel):
    session_id: str
    human_judgment: str  # "pass" | "partial" | "fail"
    human_notes: Optional[str] = ""
    failure_category: Optional[str] = "none"


def load_prompts_file() -> List[Dict[str, Any]]:
    if not os.path.exists(PROMPTS_PATH):
        logger.error(f"prompts.json not found at {PROMPTS_PATH}")
        return []
    try:
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read prompts.json: {e}")
        return []


def load_results_file() -> List[Dict[str, Any]]:
    if not os.path.exists(EVAL_RESULTS_PATH):
        return []
    try:
        with open(EVAL_RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read eval_results.json: {e}")
        return []


async def _run_eval_pipeline_safe(
    session: PipelineSession, prompt_id: int, label: str, category: str, difficulty: str
) -> None:
    """Runs the core pipeline and records auto-metrics on completion or failure."""
    completed = False
    try:
        await run_pipeline(session)
        completed = True
    except Exception as exc:
        logger.error(
            f"[eval_session:{session.session_id}] Pipeline crashed: {exc}",
            exc_info=True,
        )
        try:
            await session.sse_queue.put(
                {
                    "event": "pipeline_failed",
                    "session_id": session.session_id,
                    "error": str(exc),
                }
            )
            await session.sse_queue.put(None)  # close stream
        except Exception:
            pass
    finally:
        # Record results automatically
        try:
            record_auto_metrics(
                prompt_id=prompt_id,
                label=label,
                category=category,
                difficulty=difficulty,
                session=session,
                pipeline_completed=completed,
            )
        except Exception as record_exc:
            logger.error(f"Failed to auto-record eval metrics: {record_exc}")


@eval_router.get("/prompts")
async def get_prompts():
    """
    Returns all 20 prompts from prompts.json with their latest run status/results.
    Returns: { prompts: [...], total: 20, completed: N }
    """
    prompts = load_prompts_file()
    results = load_results_file()

    # Find the latest result for each prompt_id
    latest_results = {}
    for res in results:
        p_id = res.get("prompt_id")
        # Overwrite to keep the latest one
        latest_results[p_id] = res

    completed_ids = set()
    prompts_with_results = []
    for p in prompts:
        p_id = p["id"]
        latest_res = latest_results.get(p_id)

        prompt_entry = dict(p)
        prompt_entry["latest_result"] = latest_res

        if latest_res:
            completed_ids.add(p_id)

        prompts_with_results.append(prompt_entry)

    return {
        "prompts": prompts_with_results,
        "total": len(prompts),
        "completed": len(completed_ids),
    }


@eval_router.post("/run/{prompt_id}")
async def run_prompt(prompt_id: int):
    """
    Triggers the ProtoFlow pipeline for a specific prompt by prompt_id.
    Streams SSE events using the same /stream/{session_id} route in main.py.
    """
    prompts = load_prompts_file()
    prompt_data = next((p for p in prompts if p["id"] == prompt_id), None)
    if not prompt_data:
        raise HTTPException(status_code=404, detail=f"Prompt ID {prompt_id} not found.")

    session_id = str(uuid.uuid4())
    session = PipelineSession(
        session_id=session_id, prompt=prompt_data["prompt"].strip(), skip_hitl=True
    )

    # Import the main session store locally to avoid circular dependency
    from compiler.main import _session_lock, _session_store

    async with _session_lock:
        _session_store[session_id] = session

    logger.info(
        f"[eval:run] Starting evaluation for prompt {prompt_id} ({prompt_data['label']}) "
        f"Session ID: {session_id}"
    )

    # Run the pipeline in the background and auto-record metrics on finish
    asyncio.create_task(
        _run_eval_pipeline_safe(
            session=session,
            prompt_id=prompt_id,
            label=prompt_data["label"],
            category=prompt_data["category"],
            difficulty=prompt_data["difficulty"],
        )
    )

    return {"session_id": session_id}


@eval_router.post("/record/{prompt_id}")
async def record_judgment(prompt_id: int, req: RecordJudgmentRequest):
    """
    Appends human judgment metrics for a completed session to eval_results.json.
    """
    success = update_human_judgment(
        session_id=req.session_id,
        human_judgment=req.human_judgment,
        human_notes=req.human_notes,
        failure_category=req.failure_category,
    )
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Session ID {req.session_id} not found in results."
        )
    return {"status": "success"}


@eval_router.get("/results")
async def get_results():
    """
    Returns all recorded results and computes summary stats across categories and difficulties.
    """
    results = load_results_file()
    total_run = len(results)

    # Counts for human judgment
    passes = 0
    partials = 0
    fails = 0

    total_latency = 0
    total_tokens = 0
    total_repair = 0
    hitl_triggers = 0

    failure_breakdown = {}

    # Category stats dictionary builder helper
    def new_stat_entry():
        return {
            "total": 0,
            "pass": 0,
            "partial": 0,
            "fail": 0,
            "total_latency_ms": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0.0,
            "avg_tokens": 0.0,
        }

    by_category = {"real": new_stat_entry(), "edge": new_stat_entry()}
    by_difficulty = {
        "medium": new_stat_entry(),
        "hard": new_stat_entry(),
        "adversarial": new_stat_entry(),
    }

    for res in results:
        judgment = res.get("human_judgment")
        if judgment == "pass":
            passes += 1
        elif judgment == "partial":
            partials += 1
        elif judgment == "fail":
            fails += 1

        metrics = res.get("auto_metrics", {})
        total_latency += metrics.get("total_latency_ms", 0)
        total_tokens += metrics.get("total_tokens", 0)
        total_repair += metrics.get("repair_count", 0)
        if metrics.get("hitl_triggered"):
            hitl_triggers += 1

        fc = res.get("failure_category")
        if fc and fc != "none":
            failure_breakdown[fc] = failure_breakdown.get(fc, 0) + 1

        # Breakdown by Category
        cat = res.get("category", "real")
        if cat in by_category:
            cat_stats = by_category[cat]
            cat_stats["total"] += 1
            if judgment in ("pass", "partial", "fail"):
                cat_stats[judgment] += 1
            cat_stats["total_latency_ms"] += metrics.get("total_latency_ms", 0)
            cat_stats["total_tokens"] += metrics.get("total_tokens", 0)

        # Breakdown by Difficulty
        diff = res.get("difficulty", "medium")
        if diff in by_difficulty:
            diff_stats = by_difficulty[diff]
            diff_stats["total"] += 1
            if judgment in ("pass", "partial", "fail"):
                diff_stats[judgment] += 1
            diff_stats["total_latency_ms"] += metrics.get("total_latency_ms", 0)
            diff_stats["total_tokens"] += metrics.get("total_tokens", 0)

    # Compute averages for overall metrics
    pass_rate = (passes / total_run) if total_run > 0 else 0.0
    partial_rate = (partials / total_run) if total_run > 0 else 0.0
    fail_rate = (fails / total_run) if total_run > 0 else 0.0

    avg_latency = (total_latency / total_run) if total_run > 0 else 0.0
    avg_tokens = (total_tokens / total_run) if total_run > 0 else 0.0
    avg_repair = (total_repair / total_run) if total_run > 0 else 0.0
    hitl_rate = (hitl_triggers / total_run) if total_run > 0 else 0.0

    # Compute averages for breakdowns
    for cat, stats in by_category.items():
        if stats["total"] > 0:
            stats["avg_latency_ms"] = stats["total_latency_ms"] / stats["total"]
            stats["avg_tokens"] = stats["total_tokens"] / stats["total"]

    for diff, stats in by_difficulty.items():
        if stats["total"] > 0:
            stats["avg_latency_ms"] = stats["total_latency_ms"] / stats["total"]
            stats["avg_tokens"] = stats["total_tokens"] / stats["total"]

    return {
        "results": results,
        "summary": {
            "total_run": total_run,
            "pass_rate": pass_rate,
            "partial_rate": partial_rate,
            "fail_rate": fail_rate,
            "avg_latency_ms": avg_latency,
            "avg_tokens": avg_tokens,
            "avg_repair_count": avg_repair,
            "hitl_trigger_rate": hitl_rate,
            "failure_breakdown": failure_breakdown,
            "by_category": by_category,
            "by_difficulty": by_difficulty,
        },
    }


@eval_router.get("/export")
async def export_results():
    """
    Returns eval_results.json as a downloadable file response.
    """
    if not os.path.exists(EVAL_RESULTS_PATH):
        raise HTTPException(
            status_code=404, detail="No evaluation results found to export."
        )
    return FileResponse(
        path=EVAL_RESULTS_PATH,
        media_type="application/json",
        filename="eval_results.json",
    )


@eval_router.get("/assignment-prompts")
async def get_assignment_prompts():
    """
    Returns the 12 required OneAtlas assignment evaluation prompts.
    These are the exact prompts from the trial task specification.
    Run via POST /eval/run/{id} where id is 1-12.
    """
    if not os.path.exists(ASSIGNMENT_PROMPTS_PATH):
        raise HTTPException(
            status_code=404, detail="assignment_prompts.json not found."
        )
    try:
        with open(ASSIGNMENT_PROMPTS_PATH, "r", encoding="utf-8") as f:
            prompts = json.load(f)
        return {
            "prompts": prompts,
            "total": len(prompts),
            "note": "These are the 12 required prompts from the OneAtlas trial task specification.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load assignment prompts: {e}"
        )
