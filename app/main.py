"""
FastAPI Drug Design Agent Backend Application
"""
import math

import torch
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import INFERENCE_MODE, HOST, PORT, MAX_NUM_SAMPLES, REQUEST_COOLDOWN_SECONDS
from app.schemas.api_models import (
    HealthResponse, TargetListResponse, TargetInfo,
    GenerateRequest, GenerateResponse, TaskStatusResponse,
    AgentGenerateRequest, AgentGenerateResponse,
)
from app.agent.parser import AgentParseError
from app.agent.service import AgentService
from app.services.target_service import TargetRegistry
from app.services.docking_service import is_docking_available
from app.services.rate_limit_service import SubmissionCooldown
from app.services.task_service import TaskService

submission_cooldown = SubmissionCooldown(REQUEST_COOLDOWN_SECONDS)

app = FastAPI(
    title="AI Drug Molecule Design & Screening Agent API",
    description="GPU-accelerated drug design backend based on TG-MolDiff and ESM-2",
    version="2.0.0"
)

# Enable CORS for frontend applications (e.g. Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "AI Drug Molecule Design Agent API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/api/health", response_model=HealthResponse)
def health_check():
    cuda_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if cuda_available else None

    # Check RDKit
    try:
        from rdkit import Chem
        rdkit_ok = True
    except ImportError:
        rdkit_ok = False

    return HealthResponse(
        status="ok",
        cuda_available=cuda_available,
        gpu_name=gpu_name,
        model_loaded=True,
        esm_loaded=True,
        rdkit_available=rdkit_ok,
        vina_available=is_docking_available(),
        inference_mode=INFERENCE_MODE
    )


@app.get("/api/targets", response_model=TargetListResponse)
def get_targets():
    all_info = TargetRegistry.list_all_targets_info()
    target_objs = [TargetInfo(**info) for info in all_info]
    return TargetListResponse(targets=target_objs)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _validate_generation_request(req: GenerateRequest) -> None:
    # Validate target
    supported = TargetRegistry.get_supported_targets()
    if req.target.upper() not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target '{req.target}'. Supported targets: {supported}"
        )
    if req.num_samples > MAX_NUM_SAMPLES:
        raise HTTPException(
            status_code=422,
            detail=f"num_samples must be between 1 and {MAX_NUM_SAMPLES} for the public demo.",
        )
    if req.dock_top_k is not None and req.dock_top_k > req.num_samples:
        raise HTTPException(
            status_code=422,
            detail="dock_top_k cannot exceed num_samples.",
        )


def _enforce_cooldown(request: Request) -> str:
    client_key = _client_key(request)
    remaining = submission_cooldown.check(client_key)
    if remaining > 0:
        retry_after = max(1, math.ceil(remaining))
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {retry_after} seconds before submitting another GPU task.",
            headers={"Retry-After": str(retry_after)},
        )
    return client_key


@app.post("/api/generate", response_model=GenerateResponse)
def create_generation_task(req: GenerateRequest, background_tasks: BackgroundTasks, request: Request):
    _validate_generation_request(req)
    client_key = _enforce_cooldown(request)

    task_id = TaskService.create_task(req, background_tasks, client_key=client_key)
    return GenerateResponse(
        task_id=task_id,
        status="queued",
        message=f"Generation task for target '{req.target.upper()}' queued successfully."
    )


@app.post("/api/agent/generate", response_model=AgentGenerateResponse)
def create_agent_task(req: AgentGenerateRequest, background_tasks: BackgroundTasks, request: Request):
    try:
        plan = AgentService.build_plan(req)
    except AgentParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    client_key = _enforce_cooldown(request)
    return AgentService.create_task(
        req,
        background_tasks,
        client_key=client_key,
        plan=plan,
    )


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task ID '{task_id}' not found.")
    return task


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
