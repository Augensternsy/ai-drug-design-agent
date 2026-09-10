"""Natural-language Agent orchestration entrypoint."""

from __future__ import annotations

from typing import Any

from app.agent.llm_provider import try_parse_with_llm
from app.agent.parser import parse_rule_prompt
from app.agent.tools import resolve_target
from app.config import MAX_NUM_SAMPLES
from app.schemas.api_models import AgentGenerateRequest, AgentGenerateResponse, AgentPlan, GenerateRequest
from app.services.task_service import TaskService


class AgentService:
    @staticmethod
    def build_plan(request: AgentGenerateRequest) -> AgentPlan:
        plan = try_parse_with_llm(request.prompt) or parse_rule_prompt(request.prompt)
        plan.target = resolve_target(plan.target)
        if plan.num_samples > MAX_NUM_SAMPLES:
            raise ValueError(f"num_samples must not exceed {MAX_NUM_SAMPLES}.")
        if plan.dock_top_k is not None and plan.dock_top_k > plan.num_samples:
            raise ValueError("dock_top_k cannot exceed num_samples.")
        return plan

    @staticmethod
    def create_task(
        request: AgentGenerateRequest,
        background_tasks: Any = None,
        client_key: str | None = None,
        plan: AgentPlan | None = None,
    ) -> AgentGenerateResponse:
        plan = plan or AgentService.build_plan(request)
        generation_request = GenerateRequest(
            target=plan.target,
            num_samples=plan.num_samples,
            qed_threshold=plan.qed_threshold,
            sa_threshold=plan.sa_threshold,
            run_docking=plan.run_docking,
            dock_top_k=plan.dock_top_k,
        )
        task_id = TaskService.create_task(
            generation_request,
            background_tasks,
            agent_plan=plan,
            client_key=client_key,
        )
        return AgentGenerateResponse(
            task_id=task_id,
            status="queued",
            message=f"Agent 已解析需求并创建 {plan.target} 分子设计任务。",
            plan=plan,
        )
