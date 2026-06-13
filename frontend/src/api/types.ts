export type StageStatus = "pending"|"running"|"complete"|"failed"|"repair_triggered"|"hitl_required";
export interface StageUpdateEvent { event:"stage_update"; session_id:string; stage:string; status:StageStatus; model:string; latency_ms:number; confidence?:number; tokens_used:number; output_summary:string; assumptions:string[]; conflicts:string[]; }
export interface HITLRequiredEvent { event:"hitl_required"; session_id:string; stage:string; trigger_reason:string; questions:string[]; options:string[]|null; timeout_seconds:number; }
export interface LogUpdateEvent { event:"log_update"; session_id:string; content:string; }
export interface PipelineCompleteEvent { event:"pipeline_complete"; session_id:string; total_latency_ms:number; total_tokens:number; repair_count:number; hitl_count:number; final_schema:Record<string,unknown>; mermaid_diagrams:{pipeline_flow:string;er_diagram:string;api_sequence:string}; assumptions:string[]; conflicts:Array<{description:string;resolution_strategy:string}>; }
export interface PipelineFailedEvent { event:"pipeline_failed"; session_id:string; error:string; }
export interface ModificationAppliedEvent { event:"modification_applied"; session_id:string; modification:string; applied_at_stage:string; new_prompt:string; }
export interface ModificationQueuedEvent { event:"modification_queued"; session_id:string; modification:string; applied_at_stage:string; }
export type SSEEvent = StageUpdateEvent|HITLRequiredEvent|LogUpdateEvent|PipelineCompleteEvent|PipelineFailedEvent|ModificationQueuedEvent|ModificationAppliedEvent;
export const STAGE_META:Record<string,{label:string;model:string}> = {
  intent_extraction:{label:"Intent Extraction",model:"groq"},
  architecture_design:{label:"Architecture",model:"groq"},
  db_schema:{label:"DB Schema",model:"groq"},
  api_schema:{label:"API Schema",model:"groq"},
  ui_schema:{label:"UI Schema",model:"groq"},
  auth_schema:{label:"Auth Schema",model:"groq"},
  workflow_stubs:{label:"Workflow Stubs",model:"groq"},
  validation:{label:"Validation",model:"groq"},
  repair:{label:"Repair",model:"groq"},
  runtime_validation:{label:"Runtime",model:"groq"},
  logging:{label:"Diagrams",model:"groq"},
};
export const STAGE_ORDER = Object.keys(STAGE_META);