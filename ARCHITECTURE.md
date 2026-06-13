# OneAtlas Architecture Documentation

## System Overview

OneAtlas AppSpec Engine is a multi-stage compilation pipeline that transforms natural language app descriptions into structured, validated AppSpec JSONs. The architecture emphasizes **reliability**, **self-repair**, and **human-in-the-loop** capabilities.

## Core Components

### 1. Intent Extraction Stage
- **Purpose**: Parse and understand user requirements
- **Input**: Natural language app description
- **Output**: Structured intent object with key requirements, constraints, and use cases
- **Tool**: CrewAI Agent with Groq/Gemini LLM

### 2. Architecture Design Stage
- **Purpose**: Generate high-level system architecture
- **Input**: Intent object
- **Output**: Architecture blueprint with component layout and relationships
- **Responsibilities**:
  - Identify core services and modules
  - Define service boundaries
  - Plan integrations

### 3. Parallel Schema Generation
The following four schema stages run in parallel:

#### Database Schema
- Entity-relationship diagram
- Field definitions with types and constraints
- Indexes and relationships

#### API Schema
- RESTful endpoint definitions
- Request/response payloads
- Authentication and authorization rules

#### UI Schema
- Component hierarchy
- Page layouts and flows
- User interaction patterns

#### Authentication Schema
- Auth methods (JWT, OAuth2, etc.)
- Permission and role definitions
- Security configurations

### 4. Validation Engine
- **Purpose**: Ensure schema consistency and completeness
- **Checks**:
  - Structural validity (JSON format)
  - Field-level validation (types, constraints)
  - Cross-layer consistency (references are valid)

### 5. Repair Engine
The self-repair mechanism with 3 tiers:

```
Repair Loop Tiers:
├─ STRUCTURAL: JSON parsing, format fixes
├─ FIELD: Type corrections, missing field additions
├─ CONSISTENCY: Cross-layer reference validation
└─ ESCALATION: Human-in-the-Loop after 3+ failures
```

### 6. Human-in-the-Loop (HITL)
- Triggers on ambiguous requirements
- Asks clarifying questions
- Allows human validation before proceeding

### 7. Integration Registry
Maps natural language requests to predefined integrations:
- Slack, Gmail, Stripe, WhatsApp, Webhook, Google Sheets
- Jira, HubSpot, Notion, Twilio SMS (stubbed)

## Data Flow

```
Natural Language Input
    ↓
Intent Extraction
    ↓
Architecture Design
    ↓
    ├─→ Database Schema ─────┐
    ├─→ API Schema ──────────┤
    ├─→ UI Schema ──────────┤
    └─→ Auth Schema ────────┤
                             ↓
                    Validation Engine
                             ↓
                    Validation Passed?
                    ├─ YES → Unified AppSpec
                    └─ NO  → Repair Engine
                             ↓
                    Repaired Successfully?
                    ├─ YES → Validation Engine (retry)
                    ├─ NO  → HITL Escalation
                    └─ MAX RETRIES → Error Response
```

## File Structure

```
oneatlas/
├── src/compiler/           # Core compilation engine
│   ├── config/            # Configuration files (agents, tasks, routing)
│   ├── eval/              # Evaluation framework and prompts
│   ├── integrations/      # Integration registry
│   ├── schemas/           # Contract definitions
│   ├── tools/             # LLM tools and utilities
│   ├── crew.py            # CrewAI crew configuration
│   └── main.py            # FastAPI application
├── frontend/              # React + Vite frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── pages/         # Page layouts
│   │   ├── api/           # API client
│   │   └── hooks/         # Custom React hooks
├── .env.example           # Environment variables template
├── boot.py               # Application bootstrap
├── pyproject.toml        # Python project configuration
└── README.md             # Project documentation
```

## Key Technologies

- **Python 3.12**: Backend runtime
- **FastAPI**: Web framework
- **CrewAI**: Multi-agent orchestration
- **Groq API**: Fast LLM inference
- **React 19**: Frontend UI
- **Vite**: Frontend build tool
- **TailwindCSS**: Styling

## Security Considerations

- Environment variables stored in `.env` (never committed)
- API keys scoped to specific providers
- Input validation at all entry points
- Rate limiting for provider degradation

## Performance Metrics

- Average generation time: ~195 seconds
- Average cost per run: ~$0.02
- Success rate: 100% (on evaluated prompts)
- Average repair attempts: 2.5 per prompt

---

For more details, see [CONTRIBUTING.md](./CONTRIBUTING.md) and [README.md](./README.md)
