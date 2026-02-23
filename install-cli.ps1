param(
    [ValidateSet("User", "Venv")]
    [string]$Mode = "User",
    [switch]$SkipPathUpdate,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[cronbot-install] $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string[]]$Args,
        [Parameter(Mandatory = $true)][string]$Description
    )

    Write-Step $Description
    if ($DryRun) {
        Write-Host ("DRYRUN> {0} {1}" -f $Exe, ($Args -join " "))
        return
    }

    & $Exe @Args
    if ($LASTEXITCODE -ne 0) {
        throw ("Command failed with exit code {0}: {1} {2}" -f $LASTEXITCODE, $Exe, ($Args -join " "))
    }
}

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Exe = "py"
            PrefixArgs = @("-3")
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Exe = "python"
            PrefixArgs = @()
        }
    }

    throw "Python was not found. Install Python 3.11+ and rerun."
}

function Ensure-UserPathContains {
    param([Parameter(Mandatory = $true)][string]$PathToAdd)

    $normalized = $PathToAdd.Trim()
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return
    }

    $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathEntries = @()
    if (-not [string]::IsNullOrWhiteSpace($currentUserPath)) {
        $pathEntries = $currentUserPath -split ";" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    }

    $alreadyPresent = $false
    foreach ($entry in $pathEntries) {
        if ($entry.ToLowerInvariant() -eq $normalized.ToLowerInvariant()) {
            $alreadyPresent = $true
            break
        }
    }

    if (-not $alreadyPresent) {
        $newUserPath = if ([string]::IsNullOrWhiteSpace($currentUserPath)) {
            $normalized
        } else {
            "$currentUserPath;$normalized"
        }

        if ($DryRun) {
            Write-Host ("DRYRUN> setx USER PATH += {0}" -f $normalized)
        } else {
            [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
        }
        Write-Step "Added to user PATH: $normalized"
    } else {
        Write-Step "User PATH already contains: $normalized"
    }

    if ($env:Path.ToLowerInvariant() -notlike "*$($normalized.ToLowerInvariant())*") {
        $env:Path = "$normalized;$($env:Path)"
        Write-Step "Updated current shell PATH for immediate use."
    }
}

$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath
$pyprojectPath = Join-Path $projectRoot "pyproject.toml"

if (-not (Test-Path $pyprojectPath)) {
    throw "pyproject.toml not found at $projectRoot. Run this script from the project root."
}

$python = Get-PythonCommand
$pythonExe = $python.Exe
$pythonPrefixArgs = [string[]]$python.PrefixArgs

Write-Step "Project root: $projectRoot"
Write-Step "Install mode: $Mode"

if ($Mode -eq "User") {
    $installArgs = @($pythonPrefixArgs + @("-m", "pip", "install", "--user", "--no-warn-script-location", "-e", $projectRoot))
    Invoke-Checked -Exe $pythonExe -Args $installArgs -Description "Installing cronbot as a user-level editable package..."

    $playwrightInstallArgs = @($pythonPrefixArgs + @("-m", "playwright", "install", "chromium"))
    Invoke-Checked -Exe $pythonExe -Args $playwrightInstallArgs -Description "Installing Playwright Chromium runtime..."

    # Use sysconfig nt_user scripts path so versioned scripts dir is returned on Windows.
    $scriptsPathArgs = @($pythonPrefixArgs + @("-c", "import sysconfig; print(sysconfig.get_path('scripts', scheme='nt_user'))"))
    if ($DryRun) {
        $userScriptsPath = "<USER_BASE>\\Scripts"
        Write-Host ("DRYRUN> {0} {1}" -f $pythonExe, ($scriptsPathArgs -join " "))
    } else {
        $scriptsOutput = & $pythonExe @scriptsPathArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to determine Python user scripts directory (python command failed)."
        }

        $userScriptsPath = $null
        foreach ($line in $scriptsOutput) {
            $candidate = "$line".Trim()
            if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                $userScriptsPath = $candidate
                break
            }
        }

        if ([string]::IsNullOrWhiteSpace($userScriptsPath)) {
            throw "Unable to determine Python user scripts directory."
        }
    }

    if (-not $SkipPathUpdate) {
        Ensure-UserPathContains -PathToAdd $userScriptsPath
    } else {
        Write-Step "Skipped PATH update. Ensure this path is in PATH: $userScriptsPath"
    }
} else {
    $venvDir = Join-Path $projectRoot ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    if (-not (Test-Path $venvPython)) {
        $venvCreateArgs = @($pythonPrefixArgs + @("-m", "venv", $venvDir))
        Invoke-Checked -Exe $pythonExe -Args $venvCreateArgs -Description "Creating local virtual environment..."
    } else {
        Write-Step "Using existing virtual environment: $venvDir"
    }

    $venvInstallArgs = @("-m", "pip", "install", "-e", $projectRoot)
    Invoke-Checked -Exe $venvPython -Args $venvInstallArgs -Description "Installing cronbot into local virtual environment..."

    $venvPlaywrightInstallArgs = @("-m", "playwright", "install", "chromium")
    Invoke-Checked -Exe $venvPython -Args $venvPlaywrightInstallArgs -Description "Installing Playwright Chromium runtime..."

    $venvScriptsDir = Join-Path $venvDir "Scripts"
    Write-Step "cronbot is available at: $venvScriptsDir\\cronbot.exe"
    Write-Step "Activate with: .\\.venv\\Scripts\\Activate.ps1"
}

if (-not $DryRun) {
    $cronbotCmd = Get-Command cronbot -ErrorAction SilentlyContinue
    if ($cronbotCmd) {
        Write-Step "Success. `cronbot` command is available: $($cronbotCmd.Source)"
    } else {
        Write-Warning "Install completed, but `cronbot` is not visible in this shell yet."
        Write-Warning "Open a new terminal and run: cronbot --help"
    }
}

Write-Step "Done."
