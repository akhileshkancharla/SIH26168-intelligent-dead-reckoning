[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReplayExecutable,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
$verificationRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$fixtureRoot = Join-Path $verificationRoot "fixtures"
$pythonRoot = Join-Path $verificationRoot "python"
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$replay = (Resolve-Path -LiteralPath $ReplayExecutable).Path

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$states = Join-Path $outputRoot "cpp_replay_states.csv"
$measurements = Join-Path $outputRoot "cpp_replay_measurements.csv"
$summary = Join-Path $outputRoot "parity_results.json"
$details = Join-Path $outputRoot "parity_details.jsonl"
$report = Join-Path $outputRoot "PARITY_REPORT.md"

& $replay `
    (Join-Path $fixtureRoot "trajectory_fixture.csv") `
    (Join-Path $fixtureRoot "gnss_measurements.csv") `
    (Join-Path $fixtureRoot "initial_state.csv") `
    $states `
    $measurements
if ($LASTEXITCODE -ne 0) {
    throw "The independent C++ replay failed with exit code $LASTEXITCODE."
}

& $PythonExecutable `
    (Join-Path $pythonRoot "check_parity.py") `
    $states `
    $measurements `
    $summary `
    $details `
    $report
if ($LASTEXITCODE -ne 0) {
    throw "The independent NumPy comparison failed with exit code $LASTEXITCODE."
}

$artifacts = @($states, $measurements, $summary, $details, $report)
$manifest = [ordered]@{
    schema_version = 1
    replay_executable = [System.IO.Path]::GetFileName($replay)
    artifacts = @(
        Get-FileHash -Algorithm SHA256 -LiteralPath $artifacts | ForEach-Object {
            [ordered]@{
                path = [System.IO.Path]::GetFileName($_.Path)
                sha256 = $_.Hash.ToLowerInvariant()
                bytes = (Get-Item -LiteralPath $_.Path).Length
            }
        }
    )
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (
    Join-Path $outputRoot "run_manifest.json"
) -Encoding utf8

Write-Output "Parity artifacts: $outputRoot"
