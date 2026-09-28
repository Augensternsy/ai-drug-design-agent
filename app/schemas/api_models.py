"""
API Request and Response Pydantic Schemas for FastAPI Backend.
"""
from typing import List, Optional, Dict, Any
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
    prompt: Optional[str] = Field(None, description="Natural language prompt")
    target: Optional[str] = Field("ESR1", description="Target protein name (e.g. ESR1, JAK1, FTO)")
    num_samples: Optional[int] = Field(3, ge=1, le=5, description="Number of candidate molecules to generate (max 5)")
    qed_threshold: Optional[float] = Field(None, description="Minimum QED threshold for filtering")
    sa_threshold: Optional[float] = Field(None, description="Maximum Synthetic Accessibility score threshold")
    run_docking: Optional[bool] = Field(True, description="Whether to run AutoDock Vina docking for candidates")


class AgentIntentParseResult(BaseModel):
    parser: str = Field("rules", description="Parser engine used: 'llm' or 'rules'")
    target: str = Field("ESR1", description="Canonical target protein name (e.g. ESR1, JAK1, FTO)")
    num_samples: int = Field(3, ge=1, le=5, description="Extracted candidate molecule count (max 5)")
    run_docking: bool = Field(True, description="Whether to run AutoDock Vina docking")
    raw_prompt: str = Field("", description="Original natural language user prompt")


class GenerateResponse(BaseModel):
    task_id: str
    status: str = Field("queued", example="queued")
    message: str = Field("Task created successfully", example="Task created successfully")
    plan: Optional[AgentIntentParseResult] = Field(None, description="Parsed execution plan from intent parser")


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
    molecule_svg: Optional[str] = None
    mol_block: Optional[str] = None


class ToolStatus(BaseModel):
    name: str
    status: str = Field(..., description="pending, running, completed, failed")


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
    protein_pdb: Optional[str] = None
    tools: List[ToolStatus] = []
    candidates: List[CandidateMolecule] = []


class EvaluationReportResponse(BaseModel):
    intent_accuracy: float = Field(..., description="Target identification accuracy percentage (0-100)")
    parameter_accuracy: float = Field(..., description="Parameter parsing accuracy percentage (0-100)")
    tool_calling_success: float = Field(..., description="Tool calling success rate percentage (0-100)")
    task_success_rate: float = Field(..., description="End-to-end task execution success rate percentage (0-100)")
    total_cases: int = Field(..., description="Total benchmark test cases evaluated")
    summary: Optional[Dict[str, Any]] = Field(None, description="Full evaluation summary metrics dictionary")

