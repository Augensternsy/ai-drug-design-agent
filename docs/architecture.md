# System Architecture

本文描述公开 Demo 的工程边界。LLM/Rule Parser 只把用户语言转换为结构化计划；ESM-2、DLPS-E2PO、RDKit 和 AutoDock Vina 才承担专业计算。

## End-to-end architecture

```mermaid
flowchart LR
    U[Browser / User] --> FE[Vercel React Frontend]
    FE --> AO[Agent Orchestrator]
    AO --> GATE{LLM_ENABLED and complete config?}
    GATE -->|yes| LLM[OpenAI-compatible LLM Parser]
    GATE -->|no| RULE[Rule Parser Fallback]
    LLM -->|valid JSON| PLAN[Pydantic Agent Plan]
    LLM -->|timeout / invalid / schema error| RULE
    RULE --> PLAN
    PLAN --> API[FastAPI Async Task API]
    API --> MODAL[Modal Serverless A10 GPU]
    MODAL --> ESM[ESM-2]
    ESM --> E2PO[DLPS-E2PO]
    E2PO --> RDK[RDKit]
    RDK --> DOCK{Docking requested?}
    DOCK -->|yes| VINA[AutoDock Vina]
    DOCK -->|no| RANK[Ranking]
    VINA --> RANK
    RANK --> VIEW[Result Visualization]
    VIEW --> FE
```

## Agent Tool Calling

```mermaid
sequenceDiagram
    actor User
    participant UI as React UI
    participant Agent as Agent Orchestrator
    participant Parser as LLM / Rule Parser
    participant API as FastAPI TaskService
    participant Tools as Scientific Tools

    User->>UI: Natural-language request
    UI->>Agent: POST /api/agent/generate
    Agent->>Parser: Parse intent
    alt LLM succeeds and AgentPlan validates
        Parser-->>Agent: Pydantic AgentPlan
    else disabled, missing key, timeout, invalid JSON or schema error
        Parser->>Parser: Deterministic rule fallback
        Parser-->>Agent: Pydantic AgentPlan
    end
    Agent->>API: Create bounded async task
    API->>Tools: resolve_target
    API->>Tools: generate_molecules
    Tools->>Tools: ESM-2 → DLPS-E2PO
    API->>Tools: evaluate_properties
    Tools->>Tools: RDKit metrics + SVG + SDF
    opt run_docking=true
        API->>Tools: molecular_docking
        Tools->>Tools: Meeko → AutoDock Vina
    end
    API->>Tools: rank_candidates
    API->>Tools: generate_result_summary
    loop Until completed or failed
        UI->>API: GET /api/tasks/{task_id}
        API-->>UI: status + tool trace + results
    end
    UI-->>User: Cards, 2D/3D, exports and history
```

## Deployment and trust boundaries

```mermaid
flowchart TB
    subgraph Public[Public browser boundary]
        B[Browser]
        V[Vercel frontend]
        LS[(localStorage task history)]
        B <--> V
        V <--> LS
    end

    subgraph Backend[Modal backend boundary]
        H[HTTPS ASGI endpoint]
        F[FastAPI + Agent]
        GPU[A10 GPU container]
        H --> F --> GPU
    end

    subgraph Private[Private assets and secrets]
        S[Modal Secret: optional LLM variables]
        VOL[(Modal Volume)]
        M[/workspace/models]
        D[/workspace/data]
        VOL --> M
        VOL --> D
    end

    V -->|Only public API base URL| H
    S -->|Server-side injection only| F
    VOL --> GPU
    GPU -. idle .-> ZERO[Scale to zero]
```

## Invariants

- `checkpoint = models/e2po/direct_ki_e2po_15k.pt`
- `sampling_steps = 200`
- `clamp_mode = none`
- Public requests are limited to at most five candidates.
- The LLM API key never crosses the backend trust boundary.
- The formally evaluated research scope is 12 test targets, not arbitrary targets.
