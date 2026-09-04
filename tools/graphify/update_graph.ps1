param(
    [string]$GraphifyExecutable = "graphify",
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

function Get-InstalledGraphifyVersion {
    param([string]$PythonCommand)

    $probe = "import importlib.metadata as m; print(m.version('graphifyy'))"
    try {
        $value = & $PythonCommand -c $probe 2>$null
        if ($LASTEXITCODE -eq 0 -and $value) {
            return ($value | Select-Object -Last 1).Trim()
        }
    } catch {
        # Continue to the uv inventory fallback.
    }

    $uv = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($uv) {
        $listing = & $uv.Source tool list 2>$null
        foreach ($line in $listing) {
            if ($line -match '^graphifyy\s+v?([0-9]+\.[0-9]+\.[0-9]+)') {
                return $Matches[1]
            }
        }
    }
    throw "Unable to identify the installed Graphify package version exactly. Provide a Python executable from the Graphify environment."
}

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = (Resolve-Path (Join-Path $scriptDirectory "..\..")).Path
$expectedRepository = "akhileshkancharla/SIH26168-intelligent-dead-reckoning"

Push-Location $repositoryRoot
try {
    $gitRoot = (git rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0 -or (Resolve-Path $gitRoot).Path -ne $repositoryRoot) {
        throw "The script is not running in the expected repository root."
    }
    $origin = (git remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or $origin -notmatch 'github\.com[:/]akhileshkancharla/SIH26168-intelligent-dead-reckoning(?:\.git)?$') {
        throw "Origin does not match $expectedRepository."
    }

    $graphify = Get-Command $GraphifyExecutable -ErrorAction Stop
    $python = Get-Command $PythonExecutable -ErrorAction Stop
    $configPath = Join-Path $repositoryRoot "tools\graphify\graphify_config.json"
    $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    $installedVersion = Get-InstalledGraphifyVersion -PythonCommand $python.Source
    if ($installedVersion -ne $config.graphify_version) {
        throw "Graphify version mismatch: configured $($config.graphify_version), installed $installedVersion."
    }

    $sourceBranch = (git branch --show-current).Trim()
    $sourceParentCommit = (git rev-parse HEAD).Trim()
    $trackedChanges = git status --porcelain --untracked-files=all
    $sourceState = if ($trackedChanges) { "working-tree" } else { "clean" }
    $rawGraph = Join-Path $repositoryRoot "graphify-out\graph.json"

    Write-Output "Graphify $installedVersion; source $sourceBranch at $sourceParentCommit ($sourceState)"
    if (Test-Path -LiteralPath $rawGraph) {
        Invoke-Checked $graphify.Source "update" "."
    } else {
        Invoke-Checked $graphify.Source "extract" "." "--code-only"
    }
    Invoke-Checked $graphify.Source "cluster-only" "." "--no-label"

    $sanitize = Join-Path $repositoryRoot "tools\graphify\sanitize_graph.py"
    $verify = Join-Path $repositoryRoot "tools\graphify\verify_graph.py"
    Invoke-Checked $python.Source $sanitize `
        "--graphify-version" $installedVersion `
        "--source-branch" $sourceBranch `
        "--source-parent-commit" $sourceParentCommit `
        "--source-state" $sourceState
    Invoke-Checked $python.Source $verify

    $metadataPath = Join-Path $repositoryRoot "docs\architecture\dependency-graph\metadata.json"
    $metadata = Get-Content -Raw -LiteralPath $metadataPath | ConvertFrom-Json
    Write-Output "Snapshot verified: $($metadata.node_count) nodes, $($metadata.edge_count) edges, $($metadata.community_count) communities."
    git status --short -- ".gitignore" ".graphifyignore" "AGENTS.md" ".github/workflows/graphify-check.yml" "ci" "docs" "tools/graphify"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to print the Graphify change summary."
    }
} finally {
    Pop-Location
}
