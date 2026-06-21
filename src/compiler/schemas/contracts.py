"""
ProtoFlow Pydantic Contracts
All pipeline schemas are defined here with strict types.
No bare dict or Any. Every field has a description.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Intent Schema
# ---------------------------------------------------------------------------


class IntentSchema(BaseModel):
    """Output of the intent extraction stage."""

    app_name: str = Field(
        default="",
        description="Application name extracted from the prompt, e.g. Real Estate CRM.",
    )
    app_type: str = Field(
        description="Application type enum: crm | project_management | ecommerce | hr_tool | inventory | content_platform | analytics | custom."
    )
    features: List[str] = Field(
        default_factory=list,
        description="List of feature names extracted from the prompt.",
    )
    entities: List[str] = Field(
        default_factory=list,
        description="List of domain entity names (e.g. 'User', 'Order', 'Product').",
    )
    user_roles: List[str] = Field(
        default_factory=list,
        description="List of user role names (e.g. 'admin', 'customer', 'manager').",
    )
    integrations: List[str] = Field(
        default_factory=list,
        description="Third-party integrations mentioned (e.g. 'Stripe', 'SendGrid').",
    )
    premium_requirements: Optional[str] = Field(
        default=None,
        description="Description of premium or paid features, if any.",
    )
    analytics_requirements: Optional[str] = Field(
        default=None,
        description="Description of analytics or reporting needs, if any.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the parsed intent (0.0 to 1.0).",
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Every assumption made during intent extraction.",
    )
    clarifications_received: List[str] = Field(
        default_factory=list,
        description="Answers received from the user during HITL clarification.",
    )
    hitl_required: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="An object containing a 'questions' array of strings for any clarifying questions you need to ask the user.",
    )


# ---------------------------------------------------------------------------
# Architecture Schema
# ---------------------------------------------------------------------------


class EntitySchema(BaseModel):
    """A domain entity in the architecture."""

    name: str = Field(description="Entity name, e.g. 'User', 'Order'.")
    attributes: List[str] = Field(
        default_factory=list,
        description="List of attribute names for this entity.",
    )
    description: str = Field(
        default="",
        description="Short description of what this entity represents.",
    )


class RelationSchema(BaseModel):
    """A relationship between two entities."""

    from_entity: str = Field(description="Source entity name.")
    to_entity: str = Field(description="Target entity name.")
    cardinality: str = Field(
        description="Cardinality: 'one-to-one', 'one-to-many', or 'many-to-many'."
    )
    description: str = Field(
        default="",
        description="Description of the relationship.",
    )


class BusinessRuleSchema(BaseModel):
    """A business rule or constraint."""

    name: str = Field(description="Short name for the rule.")
    description: str = Field(description="Full description of the rule.")
    affected_entities: List[str] = Field(
        default_factory=list,
        description="Entity names affected by this rule.",
    )


class ArchitectureSchema(BaseModel):
    """Output of the system architecture design stage."""

    entities: List[EntitySchema] = Field(
        default_factory=list,
        description="All domain entities.",
    )
    relations: List[RelationSchema] = Field(
        default_factory=list,
        description="All entity relationships.",
    )
    page_flows: List[Dict] = Field(
        default_factory=list,
        description="Page navigation flows with entry points and transitions.",
    )
    role_hierarchy: Dict[str, Dict] = Field(
        default_factory=dict,
        description="Role inheritance and permission levels.",
    )
    business_rules: List[BusinessRuleSchema] = Field(
        default_factory=list,
        description="Business rules including premium gating and admin restrictions.",
    )
    data_flows: List[Dict] = Field(
        default_factory=list,
        description="Data flows between layers.",
    )


# ---------------------------------------------------------------------------
# DB Schema
# ---------------------------------------------------------------------------


class ColumnSchema(BaseModel):
    """A single database column."""

    name: str = Field(description="Column name.")
    data_type: str = Field(
        description="SQL data type, e.g. 'UUID', 'VARCHAR(255)', 'BOOLEAN'."
    )
    nullable: bool = Field(description="Whether the column allows NULL values.")
    default_value: Optional[str] = Field(
        default=None,
        description="Default value expression, if any.",
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="Constraints such as 'UNIQUE', 'NOT NULL', 'CHECK(...)'.",
    )


class ForeignKeySchema(BaseModel):
    """A foreign key constraint."""

    column: str = Field(description="Column name in this table.")
    references_table: str = Field(description="Referenced table name.")
    references_column: str = Field(description="Referenced column name.")
    on_delete: str = Field(
        default="CASCADE",
        description="ON DELETE action: 'CASCADE', 'SET NULL', 'RESTRICT'.",
    )


class IndexSchema(BaseModel):
    """A database index."""

    name: str = Field(description="Index name.")
    columns: List[str] = Field(description="Columns included in the index.")
    unique: bool = Field(default=False, description="Whether this is a unique index.")


class TableSchema(BaseModel):
    """A database table."""

    name: str = Field(description="Table name.")
    columns: List[ColumnSchema] = Field(
        default_factory=list,
        description="All columns in this table.",
    )
    primary_key: str = Field(
        default="id",
        description="Primary key column name.",
    )
    foreign_keys: List[ForeignKeySchema] = Field(
        default_factory=list,
        description="Foreign key constraints.",
    )
    indexes: List[IndexSchema] = Field(
        default_factory=list,
        description="Indexes on this table.",
    )
    relations: List[Dict] = Field(
        default_factory=list,
        description="Logical relations to other tables (for documentation).",
    )


class DBSchema(BaseModel):
    """Output of the database schema generation stage."""

    tables: List[TableSchema] = Field(
        default_factory=list,
        description="All database tables.",
    )


# ---------------------------------------------------------------------------
# API Schema
# ---------------------------------------------------------------------------


class RequestSchema(BaseModel):
    """Request body definition for an API endpoint."""

    fields: Dict[str, str] = Field(
        default_factory=dict,
        description="Field name -> data type mapping for the request body.",
    )
    required_fields: List[str] = Field(
        default_factory=list,
        description="List of required field names.",
    )


class ResponseSchema(BaseModel):
    """Response body definition for an API endpoint."""

    fields: Dict[str, str] = Field(
        default_factory=dict,
        description="Field name -> data type mapping for the response body.",
    )
    is_list: bool = Field(
        default=False,
        description="Whether the response is a list of objects.",
    )


class EndpointSchema(BaseModel):
    """A single REST API endpoint."""

    method: str = Field(description="HTTP method: GET, POST, PUT, PATCH, DELETE.")
    path: str = Field(description="URL path, e.g. '/api/v1/users/{id}'.")
    description: str = Field(description="What this endpoint does.")
    request_body: Optional[RequestSchema] = Field(
        default=None,
        description="Request body schema (null for GET/DELETE).",
    )
    response_body: ResponseSchema = Field(description="Response body schema.")
    auth_required: bool = Field(description="Whether authentication is required.")
    required_role: Optional[str] = Field(
        default=None,
        description="Role required to access this endpoint, if any.",
    )
    validation_rules: List[str] = Field(
        default_factory=list,
        description="Input validation rules.",
    )
    error_responses: List[Dict] = Field(
        default_factory=list,
        description="Possible error responses with status_code and description.",
    )


class APISchema(BaseModel):
    """Output of the API schema generation stage."""

    endpoints: List[EndpointSchema] = Field(
        default_factory=list,
        description="All API endpoints.",
    )


# ---------------------------------------------------------------------------
# UI Schema
# ---------------------------------------------------------------------------


class FormFieldSchema(BaseModel):
    """A single form field in the UI."""

    name: str = Field(description="Field name.")
    field_type: str = Field(
        description="Input type: 'text', 'email', 'select', 'checkbox', etc."
    )
    label: str = Field(description="Display label.")
    api_field: str = Field(description="Corresponding API request body field name.")
    required: bool = Field(default=False, description="Whether this field is required.")
    validation: Optional[str] = Field(
        default=None,
        description="Validation rule description.",
    )


class FormSchema(BaseModel):
    """A form in the UI."""

    name: str = Field(description="Form name.")
    fields: List[FormFieldSchema] = Field(
        default_factory=list,
        description="Form fields.",
    )
    submit_endpoint: str = Field(description="API endpoint path this form submits to.")
    submit_method: str = Field(
        default="POST", description="HTTP method for form submission."
    )


class ComponentSchema(BaseModel):
    """A UI component on a page."""

    name: str = Field(description="Component name.")
    component_type: str = Field(
        description="Component type: 'table', 'form', 'card', 'chart', 'button', etc."
    )
    props: Dict[str, str] = Field(
        default_factory=dict,
        description="Component props as key-value pairs.",
    )
    api_endpoint: Optional[str] = Field(
        default=None,
        description="API endpoint this component fetches data from.",
    )


class PageSchema(BaseModel):
    """A page in the UI."""

    path: str = Field(description="URL path for this page.")
    title: str = Field(description="Page title.")
    role_required: Optional[str] = Field(
        default=None,
        description="Role required to access this page, if any.",
    )
    components: List[ComponentSchema] = Field(
        default_factory=list,
        description="Components on this page.",
    )
    forms: List[FormSchema] = Field(
        default_factory=list,
        description="Forms on this page.",
    )
    navigation_links: List[Dict] = Field(
        default_factory=list,
        description="Navigation links from this page.",
    )


class UISchema(BaseModel):
    """Output of the UI schema generation stage."""

    pages: List[PageSchema] = Field(
        default_factory=list,
        description="All pages in the application.",
    )


# ---------------------------------------------------------------------------
# Auth Schema
# ---------------------------------------------------------------------------


class RoleSchema(BaseModel):
    """A user role."""

    name: str = Field(description="Role name.")
    description: str = Field(default="", description="Role description.")
    parent_role: Optional[str] = Field(
        default=None,
        description="Parent role this role inherits from.",
    )


class PermissionSchema(BaseModel):
    """Permissions for a role on a resource."""

    role: str = Field(description="Role name.")
    resource: str = Field(description="Resource name (maps to a DB table).")
    actions: List[str] = Field(
        description="Allowed actions: 'create', 'read', 'update', 'delete', 'list'."
    )


class PlanSchema(BaseModel):
    """A premium plan definition."""

    name: str = Field(description="Plan name, e.g. 'free', 'pro', 'enterprise'.")
    features: List[str] = Field(
        default_factory=list,
        description="Features available on this plan.",
    )
    restrictions: List[str] = Field(
        default_factory=list,
        description="Restrictions or limits on this plan.",
    )


class TokenConfig(BaseModel):
    """JWT token configuration."""

    expiry_seconds: int = Field(
        default=3600,
        description="Access token expiry in seconds.",
    )
    refresh_expiry_seconds: int = Field(
        default=604800,
        description="Refresh token expiry in seconds (default 7 days).",
    )
    algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm.",
    )


class AuthSchema(BaseModel):
    """Output of the auth schema generation stage."""

    auth_strategy: str = Field(
        description="Authentication strategy: 'jwt', 'session', or 'oauth2'."
    )
    roles: List[str] = Field(
        default_factory=list,
        description="All role names in the system.",
    )
    permissions_matrix: Dict[str, Dict[str, List[str]]] = Field(
        default_factory=dict,
        description="Permissions matrix: role -> resource -> list of actions.",
    )
    premium_plan_gates: Dict[str, PlanSchema] = Field(
        default_factory=dict,
        description="Premium plan definitions keyed by plan name.",
    )
    token_config: TokenConfig = Field(
        default_factory=TokenConfig,
        description="Token configuration.",
    )


# ---------------------------------------------------------------------------
# Validation Report
# ---------------------------------------------------------------------------


class ErrorEntry(BaseModel):
    """A validation error."""

    layer: str = Field(
        description="Schema layer: 'db', 'api', 'ui', 'auth', 'architecture'."
    )
    field: str = Field(description="Field or element that has the error.")
    description: str = Field(description="Description of the error.")


class WarningEntry(BaseModel):
    """A validation warning (non-blocking)."""

    layer: str = Field(description="Schema layer.")
    field: str = Field(description="Field or element with the warning.")
    description: str = Field(description="Description of the warning.")


class ConflictEntry(BaseModel):
    """A conflict between schema layers."""

    description: str = Field(description="Description of the conflict.")
    resolution_strategy: str = Field(description="Suggested resolution strategy.")


class ValidationReport(BaseModel):
    """Output of the cross-layer validation stage."""

    is_valid: bool = Field(description="Whether all schemas are consistent.")
    errors: List[ErrorEntry] = Field(
        default_factory=list,
        description="Blocking errors that must be fixed.",
    )
    warnings: List[WarningEntry] = Field(
        default_factory=list,
        description="Non-blocking warnings.",
    )
    conflicts: List[ConflictEntry] = Field(
        default_factory=list,
        description="Conflicts between layers with resolution strategies.",
    )
    validated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO 8601 timestamp of when validation ran.",
    )


# ---------------------------------------------------------------------------
# Repair Report
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Repair Strategy Classification (Feature F)
# ---------------------------------------------------------------------------


class RepairStrategy(str):
    """Repair strategy label. One of: STRUCTURAL, FIELD, CONSISTENCY, ESCALATED."""

    STRUCTURAL = "STRUCTURAL"  # JSON parse failure, malformed/truncated output
    FIELD = "FIELD"  # Missing required field, wrong type
    CONSISTENCY = "CONSISTENCY"  # Cross-layer reference mismatch
    ESCALATED = "ESCALATED"  # Unresolved errors after 2+ attempts -> HITL


class RepairLogEntry(BaseModel):
    """One repair attempt log entry — logged whether repair succeeded or failed."""

    attempt_number: int = Field(description="Repair attempt number (1-indexed).")
    strategy: str = Field(
        description="Classified strategy: STRUCTURAL | FIELD | CONSISTENCY | ESCALATED."
    )
    error_input: str = Field(
        description="The error description that triggered this repair attempt."
    )
    outcome: str = Field(
        description="Result of this attempt: repaired | escalated | failed."
    )
    errors_before: int = Field(default=0, description="Number of errors before repair.")
    errors_after: int = Field(default=0, description="Number of errors after repair.")


class DiffEntry(BaseModel):
    """A single repair diff."""

    error_description: str = Field(description="The error that was fixed.")
    layer_fixed: str = Field(description="Which schema layer was modified.")
    field_fixed: str = Field(description="Which field was modified.")
    before: str = Field(description="Value before the fix.")
    after: str = Field(description="Value after the fix.")


class RepairReport(BaseModel):
    """Output of the repair stage."""

    repairs: List[DiffEntry] = Field(
        default_factory=list,
        description="All repairs made.",
    )
    updated_schemas: Dict[str, object] = Field(
        default_factory=dict,
        description="Updated schema layers (only modified layers included).",
    )
    repair_attempt_number: int = Field(
        ge=1,
        le=3,
        description="Which repair attempt this is (1, 2, or 3).",
    )
    unresolved_errors: List[str] = Field(
        default_factory=list,
        description="Errors that could not be fixed automatically.",
    )
    repair_log: List[RepairLogEntry] = Field(
        default_factory=list,
        description="Per-attempt repair log with strategy, error, and outcome.",
    )


# ---------------------------------------------------------------------------
# Runtime Report
# ---------------------------------------------------------------------------


class SimulatedFlow(BaseModel):
    """A simulated execution flow."""

    name: str = Field(description="Flow name, e.g. 'CREATE User'.")
    steps: List[str] = Field(description="Steps in the flow.")
    result: str = Field(description="'pass' or 'fail'.")
    failure_reason: Optional[str] = Field(
        default=None,
        description="Reason for failure if result is 'fail'.",
    )


class RuntimeReport(BaseModel):
    """Output of the runtime validation stage."""

    execution_viable: bool = Field(
        description="Whether the application can be executed with the current schemas."
    )
    simulated_flows: List[SimulatedFlow] = Field(
        default_factory=list,
        description="Results of simulated execution flows.",
    )
    blocking_issues: List[str] = Field(
        default_factory=list,
        description="Issues that prevent execution.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-blocking concerns.",
    )


# ---------------------------------------------------------------------------
# Final Output
# ---------------------------------------------------------------------------


class EvalMetrics(BaseModel):
    """Pipeline evaluation metrics."""

    total_latency_ms: int = Field(description="Total pipeline latency in milliseconds.")
    total_tokens: int = Field(
        default=0, description="Total tokens used across all agents."
    )
    repair_count: int = Field(
        default=0, description="Number of repair loops triggered."
    )
    hitl_count: int = Field(default=0, description="Number of HITL interactions.")
    stage_latencies: Dict[str, int] = Field(
        default_factory=dict,
        description="Per-stage latency in milliseconds.",
    )


class MermaidDiagrams(BaseModel):
    """Mermaid diagram strings generated by the logger agent."""

    pipeline_flow: str = Field(
        default="",
        description="Mermaid flowchart of the pipeline execution.",
    )
    er_diagram: str = Field(
        default="",
        description="Mermaid ER diagram from the DB schema.",
    )
    api_sequence: str = Field(
        default="",
        description="Mermaid sequence diagram for the primary entity API flow.",
    )


class FinalOutput(BaseModel):
    """The complete output of the ProtoFlow pipeline."""

    session_id: str = Field(description="Unique session identifier.")
    prompt: str = Field(description="Original user prompt.")
    intent: Optional[IntentSchema] = Field(
        default=None, description="Extracted intent."
    )
    architecture: Optional[ArchitectureSchema] = Field(
        default=None, description="Designed architecture."
    )
    db_schema: Optional[DBSchema] = Field(
        default=None, description="Generated DB schema."
    )
    api_schema: Optional[APISchema] = Field(
        default=None, description="Generated API schema."
    )
    ui_schema: Optional[UISchema] = Field(
        default=None, description="Generated UI schema."
    )
    auth_schema: Optional[AuthSchema] = Field(
        default=None, description="Generated auth schema."
    )
    validation_report: Optional[ValidationReport] = Field(
        default=None, description="Cross-layer validation report."
    )
    repair_report: Optional[RepairReport] = Field(
        default=None, description="Repair report if repairs were made."
    )
    runtime_report: Optional[RuntimeReport] = Field(
        default=None, description="Runtime simulation report."
    )
    workflow_stubs: List[WorkflowStub] = Field(
        default_factory=list,
        description="Generated workflow stubs for integrations requested in the prompt.",
    )
    integration_hooks: List[IntegrationHook] = Field(
        default_factory=list,
        description="Integration hooks — one per unique (integration_id, action_id) pair. Referenced by workflow_stubs via hook_id.",
    )
    app_spec: Optional[AppSpec] = Field(
        default=None,
        description="Unified AppSpec view assembled from all pipeline outputs. Additive — does not replace existing schema fields.",
    )
    mermaid_diagrams: MermaidDiagrams = Field(
        default_factory=MermaidDiagrams,
        description="Generated Mermaid diagrams.",
    )
    eval_metrics: Optional[EvalMetrics] = Field(
        default=None, description="Pipeline evaluation metrics."
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="All assumptions made across all stages.",
    )
    conflicts: List[ConflictEntry] = Field(
        default_factory=list,
        description="All conflicts detected and their resolutions.",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO 8601 timestamp of pipeline completion.",
    )


# ---------------------------------------------------------------------------
# Integration Reference Types (used in AppSpec — Features B, C, D)
# ---------------------------------------------------------------------------


class IntegrationRef(BaseModel):
    """
    A reference to a registered integration.
    integration_id must resolve against the integration REGISTRY at runtime.
    action_id must be a valid action on that integration.
    """

    integration_id: str = Field(
        description="Integration ID from the registry, e.g. 'slack', 'stripe'."
    )
    action_id: str = Field(
        description="Action ID within the integration, e.g. 'send_message'."
    )

    def is_valid(self) -> bool:
        """Check that both integration_id and action_id exist in the registry."""
        from compiler.integrations.registry import get_action

        return get_action(self.integration_id, self.action_id) is not None


# ---------------------------------------------------------------------------
# Workflow Stub Types (Feature B)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# AppSpec Types (Feature D)
# ---------------------------------------------------------------------------


class AppSpecMeta(BaseModel):
    """High-level application metadata derived from intent extraction."""

    app_name: str = Field(description="Application name derived from intent.")
    app_type: str = Field(description="Application type, e.g. crm, ecommerce.")
    description: str = Field(
        default="", description="Brief description from user prompt."
    )
    features: List[str] = Field(
        default_factory=list, description="Features from IntentSchema."
    )
    assumptions: List[str] = Field(
        default_factory=list, description="Assumptions from IntentSchema."
    )


class AppSpecEntity(BaseModel):
    """A domain entity with DB-level field listing. Assembled from architecture + db_schema."""

    name: str = Field(description="Entity name from ArchitectureSchema.")
    table_name: str = Field(description="Corresponding DB table name.")
    fields: List[str] = Field(
        default_factory=list, description="Column names from DBSchema."
    )
    relations: List[str] = Field(
        default_factory=list, description="FK relation descriptions."
    )


class AppSpecPage(BaseModel):
    """A UI page entry. Assembled from UISchema."""

    path: str = Field(description="URL path from UISchema.")
    title: str = Field(description="Page title from UISchema.")
    role_required: Optional[str] = Field(
        default=None, description="Role gate from UISchema."
    )
    layout: str = Field(
        default="list",
        description="Page layout type: list | detail | dashboard | settings.",
    )
    bound_entity: Optional[str] = Field(
        default=None, description="Entity name matched from page path."
    )


class AppSpecEndpoint(BaseModel):
    """A condensed API endpoint entry. Assembled from APISchema."""

    method: str = Field(description="HTTP method.")
    path: str = Field(description="Endpoint path.")
    auth_required: bool = Field(description="Whether auth is required.")
    required_role: Optional[str] = Field(
        default=None, description="Role required if any."
    )
    handler_description: str = Field(
        default="", description="What the endpoint handler does."
    )
    rate_limit_flag: bool = Field(
        default=False, description="True if rate limiting should be applied."
    )


class AppSpecAuthRules(BaseModel):
    """Auth strategy and role list. Assembled from AuthSchema."""

    auth_strategy: str = Field(description="JWT, session, or oauth2.")
    roles: List[str] = Field(default_factory=list, description="All role names.")


class AppSpec(BaseModel):
    """
    Unified application specification assembled from all validated pipeline outputs.
    Acts as a high-level consolidated view for downstream code generators.
    Does not duplicate data from db_schema / api_schema / ui_schema / auth_schema.
    References integration_hooks and workflow_stubs by value (they are already
    normalized and not duplicated elsewhere in FinalOutput).
    """

    meta: AppSpecMeta = Field(description="Application metadata.")
    entities: List[AppSpecEntity] = Field(
        default_factory=list, description="Domain entities with DB fields."
    )
    pages: List[AppSpecPage] = Field(default_factory=list, description="UI pages.")
    api_endpoints: List[AppSpecEndpoint] = Field(
        default_factory=list, description="API endpoints."
    )
    auth_rules: AppSpecAuthRules = Field(
        default_factory=lambda: AppSpecAuthRules(auth_strategy="jwt", roles=[]),
        description="Auth strategy and roles.",
    )
    integration_hooks: List[IntegrationHook] = Field(
        default_factory=list,
        description="Integration hooks from Feature C. One per unique (integration_id, action_id).",
    )
    workflow_stubs: List[WorkflowStub] = Field(
        default_factory=list,
        description="Workflow stubs from Feature B. Linked to hooks via hook_id.",
    )


# Integration Hook Types (Feature C)
# ---------------------------------------------------------------------------


class IntegrationHook(BaseModel):
    """
    Execution binding for an integration action.
    One hook per unique (integration_id, action_id) pair across all workflow stubs.
    WorkflowStubs reference hooks by hook_id — avoiding data duplication.
    """

    hook_id: str = Field(
        description="Deterministic ID: hook_{integration_id}_{action_id}."
    )
    integration_id: str = Field(description="Integration ID from the registry.")
    action_id: str = Field(description="Action ID within the integration.")
    auth_type: str = Field(
        description="Auth type from registry: oauth2 | api_key | webhook_secret | none."
    )
    required_inputs: List[str] = Field(
        default_factory=list,
        description="Required input field names from the action input_schema.",
    )
    is_stub: bool = Field(
        default=False,
        description="True if the integration HTTP call is not implemented.",
    )
    validation_status: str = Field(
        default="valid", description="Validation result: valid | invalid | stub."
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Validation error messages. Empty when validation_status is valid.",
    )


class WorkflowTrigger(BaseModel):
    """The entity event that fires a workflow stub."""

    entity: str = Field(
        description="Entity name from the DataSchema, e.g. 'Deal', 'Task', 'Order'."
    )
    event: str = Field(
        description="Event type: created | updated | deleted | status_changed."
    )
    condition: Optional[str] = Field(
        default=None,
        description="Optional filter condition, e.g. \"status == 'closed'\". LLM-generated.",
    )


class WorkflowStub(BaseModel):
    """
    A named automation stub linking an entity event to an integration action.
    integration_id and action_id are validated against the integration REGISTRY.
    A stub with is_valid=False is never included in the final AppSpec output.
    """

    name: str = Field(
        description="Human-readable description of what this workflow does."
    )
    trigger: WorkflowTrigger = Field(
        description="The entity event that triggers this workflow."
    )
    integration_id: str = Field(
        description="Integration ID from the registry, e.g. 'slack', 'stripe'."
    )
    action_id: str = Field(
        description="Action ID within the integration, e.g. 'send_message'."
    )
    payload_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Maps entity fields to action input fields. e.g. {'deal.title': 'text'}.",
    )
    description: str = Field(
        default="", description="LLM-generated human-readable summary of the workflow."
    )
    is_valid: bool = Field(
        default=True,
        description="False if integration_id or action_id do not exist in the registry.",
    )
    hook_id: Optional[str] = Field(
        default=None,
        description="Reference to the IntegrationHook.hook_id that executes this stub.",
    )


# ---------------------------------------------------------------------------
# SSE Event Models
# ---------------------------------------------------------------------------


class StageUpdateEvent(BaseModel):
    """SSE event emitted after each pipeline stage."""

    event: str = Field(default="stage_update")
    session_id: str = Field(description="Session identifier.")
    stage: str = Field(description="Stage name.")
    status: str = Field(
        description="Stage status: 'running', 'complete', 'failed', 'repair_triggered', 'hitl_required'."
    )
    model: str = Field(default="", description="Model used for this stage.")
    latency_ms: int = Field(default=0, description="Stage latency in milliseconds.")
    confidence: Optional[float] = Field(
        default=None, description="Confidence score if available."
    )
    tokens_used: int = Field(default=0, description="Tokens used in this stage.")
    output_summary: str = Field(
        default="", description="Short summary of stage output."
    )
    assumptions: List[str] = Field(
        default_factory=list, description="Assumptions made."
    )
    conflicts: List[str] = Field(
        default_factory=list, description="Conflicts detected."
    )


class HITLRequiredEvent(BaseModel):
    """SSE event emitted when human input is required."""

    event: str = Field(default="hitl_required")
    session_id: str = Field(description="Session identifier.")
    stage: str = Field(description="Stage that requires input.")
    trigger_reason: str = Field(
        description="Why HITL was triggered: 'always_on', 'low_confidence', 'ambiguous', 'repair_failed'."
    )
    questions: List[str] = Field(description="Questions to ask the user.")
    options: Optional[List[str]] = Field(
        default=None,
        description="Multiple choice options if applicable.",
    )
    timeout_seconds: int = Field(default=300, description="Timeout in seconds.")


class LogUpdateEvent(BaseModel):
    """SSE event for log updates."""

    event: str = Field(default="log_update")
    session_id: str = Field(description="Session identifier.")
    content: str = Field(description="Markdown string of the latest log entry.")


class PipelineCompleteEvent(BaseModel):
    """SSE event emitted when the pipeline finishes."""

    event: str = Field(default="pipeline_complete")
    session_id: str = Field(description="Session identifier.")
    total_latency_ms: int = Field(description="Total pipeline latency.")
    total_tokens: int = Field(default=0, description="Total tokens used.")
    repair_count: int = Field(default=0, description="Number of repair loops.")
    hitl_count: int = Field(default=0, description="Number of HITL interactions.")
    final_schema: Optional[FinalOutput] = Field(
        default=None, description="Complete final output."
    )
    mermaid_diagrams: MermaidDiagrams = Field(
        default_factory=MermaidDiagrams,
        description="Generated Mermaid diagrams.",
    )
    assumptions: List[str] = Field(default_factory=list, description="All assumptions.")
    conflicts: List[ConflictEntry] = Field(
        default_factory=list, description="All conflicts."
    )


class ClarifyRequest(BaseModel):
    """Body for POST /clarify."""

    session_id: str = Field(description="Session identifier.")
    answers: List[str] = Field(description="Answers to the HITL questions.")
    chosen_option: Optional[str] = Field(
        default=None,
        description="Chosen option if multiple choice was presented.",
    )


class ModifyRequest(BaseModel):
    """Body for POST /modify — midway prompt modification."""

    session_id: str = Field(description="Session identifier.")
    modification: str = Field(
        description="The change or addition the user wants to apply."
    )


class ModificationQueuedEvent(BaseModel):
    """SSE event emitted immediately when a modification is received."""

    event: str = Field(default="modification_queued")
    session_id: str = Field(description="Session identifier.")
    modification: str = Field(description="The modification text.")
    applied_at_stage: str = Field(
        default="pending",
        description="The stage at which this will be/was applied.",
    )


class ModificationAppliedEvent(BaseModel):
    """SSE event emitted when the pipeline picks up and applies the modification."""

    event: str = Field(default="modification_applied")
    session_id: str = Field(description="Session identifier.")
    modification: str = Field(description="The applied modification text.")
    applied_at_stage: str = Field(
        description="The pipeline stage where it was applied."
    )
    new_prompt: str = Field(
        description="The updated prompt after applying modification."
    )
