[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,
    [int]$TimeoutSeconds = 3600,
    [int]$PollSeconds = 10
)

$ErrorActionPreference = "Stop"
$ApiBase = $BaseUrl.TrimEnd("/")

Write-Host "Checking $ApiBase/api/health ..."
$Health = Invoke-RestMethod -Method Get -Uri "$ApiBase/api/health" -TimeoutSec 900
if ($Health.status -ne "ok") {
    throw "Health check returned unexpected status: $($Health.status)"
}
if (-not $Health.cuda_available) {
    throw "Modal endpoint is reachable, but CUDA is unavailable."
}
if (-not $Health.rdkit_available) {
    throw "Modal endpoint is reachable, but RDKit is unavailable."
}
if (-not $Health.vina_available) {
    throw "Modal endpoint is reachable, but Vina/Meeko is unavailable."
}
Write-Host "Health PASS: GPU=$($Health.gpu_name), RDKit=$($Health.rdkit_available), Vina=$($Health.vina_available)"

$Body = @{
    target = "ESR1"
    num_samples = 1
    run_docking = $false
} | ConvertTo-Json

Write-Host "Submitting one-molecule generation smoke test ..."
$Submitted = Invoke-RestMethod `
    -Method Post `
    -Uri "$ApiBase/api/generate" `
    -ContentType "application/json" `
    -Body $Body `
    -TimeoutSec 900

if (-not $Submitted.task_id) {
    throw "Generate response did not contain task_id."
}
Write-Host "Task accepted: $($Submitted.task_id)"

$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds $PollSeconds
    $Task = Invoke-RestMethod `
        -Method Get `
        -Uri "$ApiBase/api/tasks/$($Submitted.task_id)" `
        -TimeoutSec 300
    Write-Host ("Status={0} Progress={1}% Stage={2}" -f $Task.status, $Task.progress, $Task.current_stage)
    if ($Task.status -eq "failed") {
        throw "Generation failed: $($Task.error)"
    }
    if ($Task.status -eq "completed") {
        Write-Host "Generate PASS: returned=$($Task.returned), valid=$($Task.valid)"
        exit 0
    }
} while ((Get-Date) -lt $Deadline)

throw "Generation did not complete within $TimeoutSeconds seconds."
