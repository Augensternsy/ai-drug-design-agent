[CmdletBinding()]
param(
    [string]$AssetPath = "E:\blog\AIProjects\runpod-assets.tar.gz",
    [string]$VolumeName = "ai-drug-design-assets"
)

$ErrorActionPreference = "Stop"
$ExpectedSha256 = "31c926aa70e03dfac4939ba1e349f14fa6cabea8ee553c00577b775f2b83d199"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-ModalCommand {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & py -m modal @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Modal command failed with exit code ${LASTEXITCODE}: py -m modal $($Arguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $AssetPath -PathType Leaf)) {
    throw "Asset archive not found: $AssetPath"
}

$ResolvedAsset = (Resolve-Path -LiteralPath $AssetPath).Path
$ActualSha256 = (Get-FileHash -LiteralPath $ResolvedAsset -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "Asset SHA-256 mismatch. Expected $ExpectedSha256, got $ActualSha256"
}

Write-Host "Asset SHA-256 verified: $ActualSha256"
Write-Host "Uploading to Modal Volume '$VolumeName'..."
Invoke-ModalCommand -Arguments @(
    "volume", "put", "--force", $VolumeName,
    $ResolvedAsset, "/runpod-assets.tar.gz"
)

$PreviousVolumeName = $env:MODAL_VOLUME_NAME
try {
    $env:MODAL_VOLUME_NAME = $VolumeName
    Push-Location $RepoRoot
    Invoke-ModalCommand -Arguments @("run", "modal_app.py::extract_assets")
}
finally {
    Pop-Location
    if ($null -eq $PreviousVolumeName) {
        Remove-Item Env:MODAL_VOLUME_NAME -ErrorAction SilentlyContinue
    }
    else {
        $env:MODAL_VOLUME_NAME = $PreviousVolumeName
    }
}

Write-Host "Assets uploaded and extracted under /workspace/models and /workspace/data."
