param(
    [switch]$SkipInstall,
    [switch]$SkipDocker,
    [switch]$SkipMigrate,
    [switch]$SkipVerify,
    [switch]$SeedOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = "infra/compose/dev/docker-compose.yml"

function Write-Step {
    param([string]$Message)
    "[stormlead setup] $Message"
}

function Resolve-Executable {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found on PATH. Install it, reopen PowerShell, and retry."
    }
    return $command.Source
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

function Read-DotEnvValue {
    param(
        [string]$FilePath,
        [string]$Key
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $FilePath) {
        if ($line -match "^\s*#") {
            continue
        }
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)\s*$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

function Get-DatabaseUrlHost {
    $envPath = Join-Path $RepoRoot ".env"
    $examplePath = Join-Path $RepoRoot ".env.example"
    $value = Read-DotEnvValue -FilePath $envPath -Key "DATABASE_URL_HOST"
    if (-not $value) {
        $value = Read-DotEnvValue -FilePath $examplePath -Key "DATABASE_URL_HOST"
    }
    if (-not $value) {
        throw "DATABASE_URL_HOST was not found in .env or .env.example."
    }
    return $value
}

function Get-DatabaseUrlContainer {
    $envPath = Join-Path $RepoRoot ".env"
    $examplePath = Join-Path $RepoRoot ".env.example"
    $value = Read-DotEnvValue -FilePath $envPath -Key "DATABASE_URL"
    if (-not $value) {
        $value = Read-DotEnvValue -FilePath $examplePath -Key "DATABASE_URL"
    }
    if (-not $value) {
        throw "DATABASE_URL was not found in .env or .env.example."
    }
    return $value
}

function Invoke-DockerCompose {
    param([string[]]$Arguments)
    $docker = Resolve-Executable "docker"
    $previousDatabaseUrl = $env:DATABASE_URL
    try {
        # Docker Compose interpolation prefers process env over --env-file.
        # Force the in-container DSN so host migration settings never leak into services.
        $env:DATABASE_URL = Get-DatabaseUrlContainer
        Invoke-Native -FilePath $docker -Arguments (@("compose", "--env-file", ".env", "-f", $ComposeFile) + $Arguments)
    }
    finally {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}

function Wait-PostgresReady {
    $docker = Resolve-Executable "docker"
    $baseArgs = @("compose", "--env-file", ".env", "-f", $ComposeFile, "exec", "-T", "postgres", "pg_isready", "-U", "stormlead", "-d", "stormlead")
    Write-Step "Waiting for local Postgres to accept connections"
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        & $docker @baseArgs *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Step "Postgres is ready"
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out waiting for the local Postgres container. Check Docker Desktop and run 'npm run doctor'."
}

function Wait-HttpOk {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSeconds = 120
    )
    Write-Step "Waiting for $Name"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                Write-Step "$Name is ready"
                return
            }
            $lastError = "HTTP $($response.StatusCode)"
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out waiting for $Name at $Url. Last error: $lastError"
}

Push-Location -LiteralPath $RepoRoot
try {
    $npm = Resolve-Executable "npm"
    $uv = Resolve-Executable "uv"
    $docker = Resolve-Executable "docker"

    if (-not (Test-Path -LiteralPath ".env")) {
        Write-Step "Creating .env from .env.example"
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
    }
    else {
        Write-Step ".env already exists; leaving it unchanged"
    }

    $DatabaseUrlHost = Get-DatabaseUrlHost

    if ($SeedOnly) {
        Write-Step "Re-seeding local demo data only"
        $env:DATABASE_URL = $DatabaseUrlHost
        Invoke-Native -FilePath $uv -Arguments @("run", "python", "scripts/seed_dev.py")
        Write-Step "Demo data reset complete"
        exit 0
    }

    if (-not $SkipInstall) {
        Write-Step "Installing Node dependencies from package-lock.json"
        Invoke-Native -FilePath $npm -Arguments @("ci")
        Write-Step "Syncing Python workspace dependencies"
        Invoke-Native -FilePath $uv -Arguments @("sync", "--all-packages")
    }

    if (-not $SkipDocker) {
        Write-Step "Checking Docker daemon"
        Invoke-Native -FilePath $docker -Arguments @("info")
        Write-Step "Starting local pipeline stack"
        Invoke-DockerCompose -Arguments @("--profile", "pipeline", "up", "-d")
        Wait-PostgresReady
        Wait-HttpOk -Name "ping-post readiness" -Url "http://127.0.0.1:8003/readyz"
        Wait-HttpOk -Name "form-receiver health" -Url "http://127.0.0.1:8002/healthz"
    }

    if (-not $SkipMigrate) {
        $env:DATABASE_URL = $DatabaseUrlHost
        Write-Step "Initializing database tables"
        Invoke-Native -FilePath $uv -Arguments @("run", "python", "scripts/init_db.py")
        Write-Step "Running Alembic migrations"
        Push-Location -LiteralPath "libs/stormlead_db"
        try {
            Invoke-Native -FilePath $uv -Arguments @("run", "alembic", "upgrade", "head")
        }
        finally {
            Pop-Location
        }
        Write-Step "Seeding local demo data"
        Invoke-Native -FilePath $uv -Arguments @("run", "python", "scripts/seed_dev.py")
    }

    if (-not $SkipVerify) {
        Write-Step "Running local readiness doctor"
        Invoke-Native -FilePath $npm -Arguments @("run", "doctor")
    }

    ""
    "StormLead local setup is ready."
    ""
    "Admin:        http://127.0.0.1:8003/admin"
    "Landing:      http://127.0.0.1:8005"
    "Buyer Portal: http://127.0.0.1:8004"
    ""
    "Next verification commands:"
    "  npm run verify:local"
    "  npm run simulate:v1"
}
finally {
    Pop-Location
}
