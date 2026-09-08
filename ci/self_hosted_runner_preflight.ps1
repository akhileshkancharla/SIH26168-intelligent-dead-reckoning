Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$failures = [System.Collections.Generic.List[string]]::new()

function Write-Check {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    Write-Host ("{0}: {1}" -f $Name, $Value)
}

function Add-Failure {
    param([Parameter(Mandatory = $true)][string]$Message)
    $failures.Add($Message)
    Write-Check -Name "FAILED" -Value $Message
}

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command -Name $Name -ErrorAction SilentlyContinue
    $visible = $null -ne $command
    Write-Check -Name ("Command visible ({0})" -f $Name) -Value $visible.ToString()
    if (-not $visible) {
        Add-Failure -Message ("Required command is unavailable to the runner service account: {0}" -f $Name)
    }
    return $command
}

function Invoke-Tool {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Executable
    $startInfo.Arguments = $Arguments -join " "
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Tool execution could not start."
    }
    $standardOutput = $process.StandardOutput.ReadToEnd()
    $standardError = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Tool execution failed."
    }
    return @(($standardOutput + "`n" + $standardError) -split "`r?`n" | Where-Object { $_ })
}

Write-Check -Name "Windows" -Value ([System.Runtime.InteropServices.RuntimeInformation]::OSDescription)
Write-Check -Name "Runner architecture" -Value ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString())
$reportedArchitecture = if ($env:RUNNER_ARCH) { $env:RUNNER_ARCH } else { "not reported" }
$reportedRunnerName = if ($env:RUNNER_NAME) { $env:RUNNER_NAME } else { "not reported" }
Write-Check -Name "Runner label architecture" -Value $reportedArchitecture
Write-Check -Name "Runner name" -Value $reportedRunnerName

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
    Add-Failure -Message "The job is not running on Windows."
}
if ($env:RUNNER_ARCH -ne "X64") {
    Add-Failure -Message "The GitHub runner did not report X64 architecture."
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$expectedServiceAccount = $identity -ieq "NT AUTHORITY\NETWORK SERVICE"
Write-Check -Name "Expected service account" -Value $expectedServiceAccount.ToString()
if (-not $expectedServiceAccount) {
    Add-Failure -Message "The runner is not executing as the expected Windows service account."
}

$git = Require-Command -Name "git"
$powershell = Require-Command -Name "powershell"
$python = Require-Command -Name "python"
$java = Require-Command -Name "java"
$gradle = Require-Command -Name "gradle"
$cmake = Require-Command -Name "cmake"

if ($git) {
    try {
        Write-Check -Name "Git" -Value ((Invoke-Tool -Executable $git.Source -Arguments @("--version") | Select-Object -First 1) -join " ")
    } catch {
        Add-Failure -Message "Git is visible but cannot be executed by the runner service account."
    }
}
Write-Check -Name "PowerShell" -Value $PSVersionTable.PSVersion.ToString()

if ($python) {
    try {
        $pythonVersion = (Invoke-Tool -Executable $python.Source -Arguments @("--version") | Select-Object -First 1) -join " "
        Write-Check -Name "Python" -Value $pythonVersion
        if ($pythonVersion -notmatch '^Python 3\.12(?:\.|$)') {
            Add-Failure -Message "Python 3.12 is required after the pinned setup action."
        }
    } catch {
        Add-Failure -Message "Python is visible but cannot be executed by the runner service account."
    }
}

if ($java) {
    try {
        $javaVersion = (Invoke-Tool -Executable $java.Source -Arguments @("-version") | Select-Object -First 1) -join " "
        Write-Check -Name "Java" -Value $javaVersion
        if ($javaVersion -notmatch '(?:version |openjdk )"?17(?:\.|"|\s)') {
            Add-Failure -Message "Java 17 is required after the pinned setup action."
        }
    } catch {
        Add-Failure -Message "Java is visible but cannot be executed by the runner service account."
    }
}

if ($gradle) {
    try {
        $gradleVersionLine = (Invoke-Tool -Executable $gradle.Source -Arguments @("--version") | Where-Object { $_ -match '^Gradle\s+' } | Select-Object -First 1) -join " "
        Write-Check -Name "Gradle" -Value ($gradleVersionLine.Trim())
        if ($gradleVersionLine -notmatch '^Gradle\s+8\.10\.2$') {
            Add-Failure -Message "Gradle 8.10.2 is required after the pinned setup action."
        }
    } catch {
        Add-Failure -Message "Gradle is visible but cannot be executed by the runner service account."
    }
}

if ($cmake) {
    try {
        $cmakeVersion = (Invoke-Tool -Executable $cmake.Source -Arguments @("--version") | Select-Object -First 1) -join " "
        Write-Check -Name "CMake" -Value $cmakeVersion
        if ($cmakeVersion -notmatch '^cmake version (\d+)\.(\d+)') {
            Add-Failure -Message "CMake version could not be determined."
        } elseif (([int]$Matches[1] -lt 3) -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 20)) {
            Add-Failure -Message "CMake 3.20 or newer is required."
        }
    } catch {
        Add-Failure -Message "CMake is visible but cannot be executed by the runner service account."
    }
}

$compilerName = $null
foreach ($candidate in @("cl", "clang-cl", "clang++", "g++")) {
    if (Get-Command -Name $candidate -ErrorAction SilentlyContinue) {
        $compilerName = $candidate
        break
    }
}

if (-not $compilerName) {
    $programFilesX86 = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFilesX86)
    $vswhere = if ($programFilesX86) { Join-Path $programFilesX86 "Microsoft Visual Studio\Installer\vswhere.exe" } else { $null }
    if ($vswhere -and (Test-Path -LiteralPath $vswhere -PathType Leaf)) {
        $visualStudioVersion = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion 2>$null | Select-Object -First 1)
        if ($visualStudioVersion) {
            $compilerName = "MSVC via Visual Studio $visualStudioVersion"
        }
    }
}

$reportedCompiler = if ($compilerName) { $compilerName } else { "not found" }
Write-Check -Name "C++ compiler" -Value $reportedCompiler
if (-not $compilerName) {
    Add-Failure -Message "No supported C++ compiler or Visual Studio C++ toolchain is available."
}

$sdkVariable = $null
$sdkRoot = $null
if ($env:ANDROID_SDK_ROOT) {
    $sdkVariable = "ANDROID_SDK_ROOT"
    $sdkRoot = $env:ANDROID_SDK_ROOT
} elseif ($env:ANDROID_HOME) {
    $sdkVariable = "ANDROID_HOME"
    $sdkRoot = $env:ANDROID_HOME
}

$reportedSdkVariable = if ($sdkVariable) { $sdkVariable } else { "not configured" }
Write-Check -Name "Android SDK environment" -Value $reportedSdkVariable
if (-not $sdkRoot -or -not (Test-Path -LiteralPath $sdkRoot -PathType Container)) {
    Add-Failure -Message "The Android SDK is not configured for the runner service account."
} else {
    $platformJar = Join-Path $sdkRoot "platforms\android-35\android.jar"
    $platformAvailable = Test-Path -LiteralPath $platformJar -PathType Leaf
    Write-Check -Name "Android platform 35" -Value $platformAvailable.ToString()
    if (-not $platformAvailable) {
        Add-Failure -Message "Android SDK platform 35 is unavailable."
    }

    $buildToolsRoot = Join-Path $sdkRoot "build-tools"
    $buildTools = @()
    if (Test-Path -LiteralPath $buildToolsRoot -PathType Container) {
        $buildTools = @(Get-ChildItem -LiteralPath $buildToolsRoot -Directory | Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "aapt2.exe") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "apksigner.bat") -PathType Leaf)
        } | Sort-Object Name -Descending)
    }
    $buildToolsVersion = if ($buildTools.Count) { $buildTools[0].Name } else { "not found" }
    Write-Check -Name "Android build tools" -Value $buildToolsVersion
    if (-not $buildTools.Count) {
        Add-Failure -Message "No complete Android SDK build-tools installation is available."
    }
}

$workspace = $env:GITHUB_WORKSPACE
if (-not $workspace -or -not (Test-Path -LiteralPath $workspace -PathType Container)) {
    Add-Failure -Message "GITHUB_WORKSPACE is unavailable."
} else {
    $repositoryLocation = (Resolve-Path -LiteralPath $workspace).Path
    Write-Check -Name "Repository location" -Value $repositoryLocation

    $driveRoot = [System.IO.Path]::GetPathRoot($repositoryLocation)
    $drive = [System.IO.DriveInfo]::new($driveRoot)
    $freeGiB = [Math]::Round($drive.AvailableFreeSpace / 1GB, 2)
    Write-Check -Name "Available disk space (GiB)" -Value $freeGiB.ToString()
    if ($drive.AvailableFreeSpace -lt 5GB) {
        Add-Failure -Message "At least 5 GiB of free workspace drive space is required."
    }

    $probe = Join-Path $repositoryLocation (".runner-write-probe-{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
    $writable = $false
    try {
        [System.IO.File]::WriteAllText($probe, "workspace write probe")
        $writable = Test-Path -LiteralPath $probe -PathType Leaf
    } finally {
        if (Test-Path -LiteralPath $probe -PathType Leaf) {
            Remove-Item -LiteralPath $probe -Force
        }
    }
    Write-Check -Name "Workspace writable" -Value $writable.ToString()
    if (-not $writable) {
        Add-Failure -Message "The repository workspace is not writable."
    }
}

if ($failures.Count -gt 0) {
    Write-Host ("Preflight failed with {0} required prerequisite error(s)." -f $failures.Count)
    exit 1
}

Write-Host "PASS: Windows self-hosted runner preflight"
