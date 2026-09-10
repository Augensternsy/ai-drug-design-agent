"""
API Request and Response Pydantic Schemas for FastAPI Backend.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., example="ok")
    cuda_available: bool = Field(..., example=True)
    gpu_name: Optional[str] = Field(None, example="NVIDIA GeForce RTX 3090")
    model_loaded: bool = Field(..., example=True)
    esm_loaded: bool = Field(..., example=True)
    rdkit_available: bool = Field(..., example=True)
    vina_available: bool = Field(..., example=True)
    inference_mode: str = Field(..., example="local")


class TargetInfo(BaseModel):
    target: str = Field(..., example="ESR1")
    pdb_id: Optional[str] = Field(None, example="2r6w")
    sequence: str
    receptor_exists: bool
    receptor_path: Optional[str] = None
    ligand_exists: bool
    ligand_path: Optional[str] = None


class TargetListResponse(BaseModel):
    targets: List[TargetInfo]


class GenerateRequest(BaseModel):
    target: str = Field("ESR1", description="Target protein name (e.g. ESR1, JAK1, FTO)")
    num_samples: int = Field(3, ge=1, le=5, description="Number of candidate molecules to generate (public demo maximum: 5)")
    qed_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum QED threshold for filtering")
    sa_threshold: Optional[float] = Field(None, ge=1.0, le=10.0, description="Maximum Synthetic Accessibility score threshold")
    run_docking: bool = Field(False, description="Whether to run AutoDock Vina docking for candidates")
    dock_top_k: Optional[int] = Field(None, ge=1, le=5, description="Optionally dock only the top K candidates by QED")


class GenerateResponse(BaseModel):
    task_id: str
    status: str = Field("queued", example="queued")
    message: str = Field("Task created successfully", example="Task created successfully")


class CandidateMolecule(BaseModel):
    rank: int
    smiles: str
    valid: bool = True
    qed: Optional[float] = None
    sa: Optional[float] = None
    molwt: Optional[float] = None
    logp: Optional[float] = None
    lipinski: Optional[bool] = None
    vina: Optional[float] = None
    structure_svg: Optional[str] = None
    sdf: Optional[str] = None


class AgentPlan(BaseModel):
    target: str
    num_samples: int = Field(ge=1, le=5)
    qed_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    sa_threshold: Optional[float] = Field(None, ge=1.0, le=10.0)
    qed_priority: bool = True
    run_docking: bool = False
    dock_top_k: Optional[int] = Field(None, ge=1, le=5)
    parser: Literal["rules", "llm"] = "rules"


class AgentGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)


class AgentGenerateResponse(BaseModel):
    task_id: str
    status: str = "queued"
    message: str
    plan: AgentPlan


class ToolExecution(BaseModel):
    name: str
    status: Literal["pending", "running", "completed", "skipped", "failed"]
    detail: Optional[str] = None


class TaskStatusResponse(BaseModel):
    task_id: str
    target: str
    status: str = Field(..., description="queued, loading, encoding, generating, evaluating, docking, ranking, completed, failed")
    progress: float = Field(0.0, description="Progress percentage from 0 to 100")
    current_stage: str = Field("queued", description="Human-readable current stage message")
    error: Optional[str] = None
    num_samples: int = 0
    requested: int = 0
    generated: int = 0
    valid: int = 0
    returned: int = 0
    candidates: List[CandidateMolecule] = Field(default_factory=list)
    requested_by_agent: bool = False
    agent_plan: Optional[AgentPlan] = None
    tool_trace: List[ToolExecution] = Field(default_factory=list)
    summary: Optional[str] = None
