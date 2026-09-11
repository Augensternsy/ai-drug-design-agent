# Qiniu LLM on Modal

The Agent uses Qiniu only as an OpenAI-compatible intent parser. Molecular
generation and scientific evaluation remain in the existing Agent Tools,
DLPS-E2PO, RDKit and optional AutoDock Vina pipeline.

## Fixed configuration

```text
LLM_ENABLED=true
LLM_BASE_URL=https://api.qnaigc.com/v1
LLM_MODEL=deepseek-flash
LLM_API_KEY=<injected by Modal Secret>
```

`modal_app.py` unconditionally binds the fixed Secret
`ai-drug-design-agent-llm` to the `fastapi_api` function. These four variables
are therefore available only in the Modal backend container and are never
exposed as `VITE_*` variables. The unconditional binding keeps the Modal Image,
Volume and Secret dependency list identical during deploy and remote hydration.

## Create the Modal Secret

Run in PowerShell and replace only the API-key placeholder:

```powershell
py -m modal secret create ai-drug-design-agent-llm `
  LLM_ENABLED=true `
  LLM_BASE_URL=https://api.qnaigc.com/v1 `
  LLM_API_KEY="<YOUR_QINIU_API_KEY>" `
  LLM_MODEL=deepseek-flash
```

## Deploy with the Secret

```powershell
Set-Location 'E:\blog\AIProjects\drug-design-agent-public'
py -m modal deploy .\modal_app.py
```

## Final real Agent test

This command creates one ESR1 task with Vina disabled. Run it only after the
deployment when a real end-to-end test is intended:

```powershell
$ApiUrl = 'https://augensternsy--ai-drug-design-agent-fastapi-api.modal.run'
$Body = @{ prompt = '帮我针对 ESR1 生成 1 个候选分子，QED 优先，不进行 Vina 对接。' } | ConvertTo-Json
$Task = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/agent/generate" -ContentType 'application/json' -Body $Body
if ($Task.plan.parser -ne 'llm') { throw "Expected LLM parser, got $($Task.plan.parser)" }
do {
  Start-Sleep -Seconds 5
  $Result = Invoke-RestMethod -Method Get -Uri "$ApiUrl/api/tasks/$($Task.task_id)"
  "$($Result.status) - $($Result.current_stage)"
} while ($Result.status -notin @('completed', 'failed'))
$Result | ConvertTo-Json -Depth 8
```

The first response must contain `plan.parser = "llm"`. If the provider is
unavailable, times out, returns invalid JSON, fails Pydantic validation, or the
key is absent, the response will instead contain `plan.parser = "rules"` and
the deterministic rule parser continues the workflow.
