"""
FastAPI Drug Design Agent Backend Application
"""
import time
import torch
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import json
from pathlib import Path
from app.config import INFERENCE_MODE, DEVICE_ENV, HOST, PORT, ALLOWED_ORIGINS
from app.schemas.api_models import (
    HealthResponse, TargetListResponse, TargetInfo,
    GenerateRequest, GenerateResponse, TaskStatusResponse,
    EvaluationReportResponse
)
from app.services.target_service import TargetRegistry
from app.services.docking_service import is_docking_available
from app.services.task_service import TaskService
from app.agent.parser import AgentIntentParser

app = FastAPI(
    title="AI Drug Molecule Design & Screening Agent API",
    description="GPU-accelerated drug design backend based on TG-MolDiff and ESM-2",
    version="2.0.0"
)

# Enable CORS for frontend applications (e.g. Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app" if ALLOWED_ORIGINS == ["*"] or any("vercel" in o for o in ALLOWED_ORIGINS) else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cooldown tracking
_last_generation_time = 0.0
COOLDOWN_SECONDS = 0.0


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


@app.post("/api/generate", response_model=GenerateResponse)
def create_generation_task(req: GenerateRequest, background_tasks: BackgroundTasks):
    global _last_generation_time
    now = time.time()
    if COOLDOWN_SECONDS > 0 and (now - _last_generation_time < COOLDOWN_SECONDS):
        remaining = int(COOLDOWN_SECONDS - (now - _last_generation_time))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit / cooldown active. Please wait {remaining} seconds before submitting a new task."
        )

    parsed_plan = None
    if req.prompt:
        parsed_plan = AgentIntentParser.parse_prompt(req.prompt)
        req.target = parsed_plan.target
        req.num_samples = parsed_plan.num_samples
        req.run_docking = parsed_plan.run_docking
    elif not req.target:
        req.target = "ESR1"

    # Validate target
    supported = TargetRegistry.get_supported_targets()
    if req.target.upper() not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target '{req.target}'. Supported targets: {supported}"
        )

    _last_generation_time = now
    task_id = TaskService.create_task(req, background_tasks)
    return GenerateResponse(
        task_id=task_id,
        status="queued",
        message=f"Generation task for target '{req.target.upper()}' queued successfully.",
        plan=parsed_plan
    )


@app.post("/api/agent/generate", response_model=GenerateResponse)
def create_agent_generation_task(req: GenerateRequest, background_tasks: BackgroundTasks):
    """Alias endpoint for /api/generate for Agent integrations."""
    return create_generation_task(req, background_tasks)


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task ID '{task_id}' not found.")
    return task


@app.get("/api/evaluation/report", response_model=EvaluationReportResponse)
def get_evaluation_report():
    """Read evaluation/evaluation_report.json and return accuracy and execution metrics."""
    report_path = Path(__file__).resolve().parent.parent / "evaluation" / "evaluation_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Evaluation report file evaluation_report.json not found.")

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read evaluation report file: {str(e)}")

    summary = report_data.get("summary", {})
    return EvaluationReportResponse(
        intent_accuracy=summary.get("intent_accuracy", 0.0),
        parameter_accuracy=summary.get("param_accuracy", 0.0),
        tool_calling_success=summary.get("tool_success_rate", 0.0),
        task_success_rate=summary.get("task_success_rate", 0.0),
        total_cases=summary.get("total_cases", 0),
        summary=summary
    )


if __name__ == "__main__":

    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
