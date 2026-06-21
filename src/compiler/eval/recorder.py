import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("protoflow.eval.recorder")

# Path to eval_results.json inside the eval directory
EVAL_RESULTS_PATH = os.path.join(os.path.dirname(__file__), "eval_results.json")
EVAL_LOGS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend", "logs", "eval")
)


def init_results_file():
    """Ensure eval_results.json exists and contains a valid JSON array."""
    if not os.path.exists(EVAL_RESULTS_PATH):
        try:
            with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            logger.info("Initialized new eval_results.json file.")
        except Exception as e:
            logger.error(f"Failed to initialize eval_results.json: {e}")


def _count_correct_integrations(session) -> int:
    """
    Count how many requested integrations produced at least one valid workflow stub.
    A stub is correctly detected if its integration_id is in the registry and
    appears in the session workflow_stubs list.
    """
    from compiler.integrations.registry import REGISTRY

    requested = (session.intent or {}).get("integrations", []) if session.intent else []
    if not requested:
        return 0
    stubs = getattr(session, "workflow_stubs", None) or []
    detected_ids = set()
    for stub in stubs:
        iid = (
            stub.integration_id
            if hasattr(stub, "integration_id")
            else stub.get("integration_id", "")
        )
        if iid:
            detected_ids.add(iid)
    return sum(1 for r in requested if r.lower().strip() in detected_ids)


def record_auto_metrics(
    prompt_id: int,
    label: str,
    category: str,
    difficulty: str,
    session: Any,  # PipelineSession
    pipeline_completed: bool,
) -> Dict[str, Any]:
    """
    Constructs the run result dict, appends it to eval_results.json,
    and writes the per-run log file to backend/logs/eval/eval_{session_id}.md.
    """
    init_results_file()

    # Extract info from PipelineSession
    session_id = session.session_id
    run_at = datetime.utcnow().isoformat() + "Z"

    # Stage metadata extraction
    intent = session.intent or {}
    validation = session.validation_report or {}
    runtime = session.runtime_report or {}
    log_output = session.log_output or {}

    validation_passed = validation.get("is_valid", False)
    runtime_viable = runtime.get("execution_viable", False)
    repair_count = getattr(session, "repair_count", 0)

    # Determine repair success: if validation passed and repair count > 0, repair succeeded
    repair_succeeded = True
    if repair_count > 0 and not validation_passed:
        repair_succeeded = False

    hitl_count = getattr(session, "hitl_count", 0)
    hitl_triggered = hitl_count > 0

    # Populate hitl_stages
    hitl_stages = []
    if hitl_triggered:
        # Check if intent had clarifications
        if intent.get("clarifications_received"):
            hitl_stages.append("intent_extraction")
        # Check if validation report had repairs that failed/escalated
        if repair_count >= 2:
            hitl_stages.append("repair")

    # Populate stages completed and failed
    stages_completed = []
    stages_failed = []

    # Analyze the event buffer to determine which stages completed and failed
    stage_statuses = {}
    for event in session.event_buffer:
        if event.get("event") == "stage_update":
            stage = event.get("stage")
            status = event.get("status")
            if stage and status:
                stage_statuses[stage] = status

    for stage, status in stage_statuses.items():
        if status in ["complete", "repair_triggered", "hitl_required"]:
            stages_completed.append(stage)
        elif status == "failed":
            stages_failed.append(stage)

    assumptions_count = len(intent.get("assumptions", []))
    conflicts_count = len(validation.get("conflicts", []))

    # Extract confidence scores
    confidence_scores = {}
    if "confidence" in intent:
        confidence_scores["intent_extraction"] = intent["confidence"]

    # Construct the standard run structure
    run_result = {
        "prompt_id": prompt_id,
        "label": label,
        "category": category,
        "difficulty": difficulty,
        "session_id": session_id,
        "run_at": run_at,
        "auto_metrics": {
            "pipeline_completed": pipeline_completed,
            "total_latency_ms": session.elapsed_ms(),
            "total_tokens": getattr(session, "total_tokens", 0),
            "repair_count": repair_count,
            "repair_succeeded": repair_succeeded,
            "hitl_triggered": hitl_triggered,
            "hitl_count": hitl_count,
            "hitl_stages": hitl_stages,
            "validation_passed": validation_passed,
            "runtime_viable": runtime_viable,
            "stages_completed": stages_completed,
            "stages_failed": stages_failed,
            "assumptions_count": assumptions_count,
            "conflicts_count": conflicts_count,
            "confidence_scores": confidence_scores,
            "integrations_correctly_detected": _count_correct_integrations(session),
            "workflow_stubs_generated": len(
                getattr(session, "workflow_stubs", None) or []
            ),
            "repair_strategies_used": list(
                set(
                    entry.get("strategy", "UNKNOWN")
                    for entry in (getattr(session, "repair_log", None) or [])
                    if isinstance(entry, dict)
                )
            ),
            "repair_log": getattr(session, "repair_log", []),
            "repair_strategies_used": list(
                set(
                    entry.get("strategy", "UNKNOWN")
                    for entry in (getattr(session, "repair_log", None) or [])
                    if isinstance(entry, dict)
                )
            ),
            "repair_log": getattr(session, "repair_log", []),
        },
        "human_judgment": None,
        "human_notes": None,
        "failure_category": None,
    }

    # Append to eval_results.json
    try:
        results = []
        if os.path.exists(EVAL_RESULTS_PATH):
            with open(EVAL_RESULTS_PATH, "r", encoding="utf-8") as f:
                results = json.load(f)

        results.append(run_result)

        with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        logger.info(
            f"Recorded auto metrics for session {session_id} to eval_results.json"
        )
    except Exception as e:
        logger.error(f"Failed to write run result to eval_results.json: {e}")

    # Write per-run logs to backend/logs/eval/eval_{session_id}.md
    try:
        os.makedirs(EVAL_LOGS_DIR, exist_ok=True)
        log_path = os.path.join(EVAL_LOGS_DIR, f"eval_{session_id}.md")

        log_entries = log_output.get("log_entries", [])
        formatted_entries = ""
        for entry in log_entries:
            if isinstance(entry, dict):
                formatted_entries += (
                    f"- **{entry.get('stage', 'Log')}:** {entry.get('message', '')}\n"
                )
            else:
                formatted_entries += f"- {entry}\n"

        mermaid_pipeline = log_output.get("mermaid_pipeline", "")
        mermaid_er = log_output.get("mermaid_er", "")
        mermaid_sequence = log_output.get("mermaid_sequence", "")

        markdown_content = f"""# Evaluation Run Log — Prompt {prompt_id} ({label})
- **Session ID:** `{session_id}`
- **Category:** {category}
- **Difficulty:** {difficulty}
- **Run At:** {run_at}
- **Pipeline Completed:** {pipeline_completed}
- **Total Latency:** {session.elapsed_ms()}ms
- **Total Tokens:** {run_result['auto_metrics']['total_tokens']}
- **Repairs:** {repair_count} (Succeeded: {repair_succeeded})
- **HITL Count:** {hitl_count}

## Live Log Entries
{formatted_entries if formatted_entries else "*No log entries available.*"}

## Mermaid Diagrams

### Pipeline Flow
```mermaid
{mermaid_pipeline if mermaid_pipeline else "%% No pipeline diagram generated"}
```

### ER Diagram
```mermaid
{mermaid_er if mermaid_er else "%% No ER diagram generated"}
```

### API Sequence Diagram
```mermaid
{mermaid_sequence if mermaid_sequence else "%% No API sequence diagram generated"}
```
"""
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info(f"Saved evaluation markdown log to {log_path}")
    except Exception as e:
        logger.error(f"Failed to write evaluation run log file: {e}")

    return run_result


def update_human_judgment(
    session_id: str,
    human_judgment: str,
    human_notes: Optional[str],
    failure_category: Optional[str],
) -> bool:
    """
    Updates an existing run result in eval_results.json with human judgment details.
    Uses append-only methodology by modifying the entry in the list and rewriting the list.
    """
    init_results_file()
    if not os.path.exists(EVAL_RESULTS_PATH):
        return False

    try:
        with open(EVAL_RESULTS_PATH, "r", encoding="utf-8") as f:
            results = json.load(f)

        updated = False
        # Loop backwards to update the latest run for this session_id if multiple exist
        for run in reversed(results):
            if run.get("session_id") == session_id:
                run["human_judgment"] = human_judgment
                run["human_notes"] = human_notes
                run["failure_category"] = failure_category
                updated = True
                break

        if updated:
            with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            logger.info(f"Updated human judgment for session {session_id}")
            return True
        else:
            logger.warning(
                f"Session ID {session_id} not found in eval results for updating judgment."
            )
            return False
    except Exception as e:
        logger.error(f"Failed to update human judgment in eval_results.json: {e}")
        return False
