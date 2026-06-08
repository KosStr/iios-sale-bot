# PhoneStore bot — one-time setup script for Windows (PowerShell)
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== PhoneStore bot setup ===" -ForegroundColor Cyan

# --- 1. Ensure Python is installed --------------------------------------------
function Get-PythonCmd {
    foreach ($candidate in @("py", "python", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            # Skip the Microsoft Store stub that just prints an install hint
            try {
                $version = & $candidate --version 2>&1
                if ($version -match "Python\s+3\.\d+") {
                    return $candidate
                }
            } catch {}
        }
    }
    return $null
}

$python = Get-PythonCmd

if (-not $python) {
    Write-Host "Python not found. Installing via winget..." -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Error "winget is not available. Install Python 3.10+ manually from https://www.python.org/downloads/ and re-run this script."
        exit 1
    }
    winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements

    Write-Host "Python installed. Please CLOSE and REOPEN this terminal, then run setup.ps1 again so PATH is refreshed." -ForegroundColor Green
    exit 0
}

Write-Host "Using Python: $python ($(& $python --version))" -ForegroundColor Green

# --- 2. Create a virtual environment ------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
    & $python -m venv .venv
} else {
    Write-Host "Virtual environment already exists (.venv)." -ForegroundColor DarkGray
}

$venvPython = Join-Path ".venv" "Scripts\python.exe"

# --- 3. Install dependencies --------------------------------------------------
Write-Host "Upgrading pip and installing dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

# --- 4. Prepare .env ----------------------------------------------------------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example — open it and add your BOT_TOKEN." -ForegroundColor Yellow
} else {
    Write-Host ".env already exists — leaving it untouched." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=== Setup complete! ===" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit .env and paste your bot token from @BotFather"
Write-Host "  2. Run the bot:" -ForegroundColor Cyan
Write-Host "       .\.venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "       python -m store" -ForegroundColor White
