<#
.SYNOPSIS
Thin Windows competition-day wrapper for Sovereign AI launcher.

Usage:
  .\scripts\sovereign.ps1 doctor --profile judge
  .\scripts\sovereign.ps1 start --profile judge
  .\scripts\sovereign.ps1 start --profile vision
  .\scripts\sovereign.ps1 start --profile coder
  .\scripts\sovereign.ps1 status
  .\scripts\sovereign.ps1 stop
#>

$ErrorActionPreference = "Stop"

# Resolve repo root from script location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# Verify conda environment
$condaEnv = $env:CONDA_DEFAULT_ENV
if (-not $condaEnv -or $condaEnv -ne "sovereign-ai") {
    Write-Host "ERROR: Wrong conda environment: $condaEnv" -ForegroundColor Red
    Write-Host "Run: conda activate sovereign-ai" -ForegroundColor Yellow
    exit 2
}

# Resolve python from PATH (should resolve to sovereign-ai python)
$pythonExe = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonExe) {
    Write-Host "ERROR: python not found in PATH" -ForegroundColor Red
    exit 2
}

$pythonPath = $pythonExe.Source

# Parse arguments manually to support both -Name and --name styles
$Command = "help"
$Profile = $null
$Json = $false

for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = $args[$i]
    switch ($arg) {
        "doctor" { $Command = "doctor" }
        "start" { $Command = "start" }
        "status" { $Command = "status" }
        "stop" { $Command = "stop" }
        "--profile" {
            $i++
            if ($i -lt $args.Count) { $Profile = $args[$i] }
        }
        "-profile" {
            $i++
            if ($i -lt $args.Count) { $Profile = $args[$i] }
        }
        "--json" { $Json = $true }
        "-json" { $Json = $true }
    }
}

# Build arguments
$argsList = @($Command)
if ($Profile) {
    $argsList += @("--profile", $Profile)
}
if ($Json) {
    $argsList += "--json"
}

# Call scripts/sovereign.py
$scriptPath = Join-Path $ScriptDir "sovereign.py"
& $pythonPath $scriptPath @argsList
exit $LASTEXITCODE
