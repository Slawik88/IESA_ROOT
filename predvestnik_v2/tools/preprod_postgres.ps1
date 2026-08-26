[CmdletBinding()]
param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$dataDir = if ($env:PREPROD_PG_DATA_DIR) {
    [System.IO.Path]::GetFullPath($env:PREPROD_PG_DATA_DIR)
} else {
    Join-Path $projectRoot ".local\preprod-postgres"
}
$port = if ($env:PREPROD_PG_PORT) { $env:PREPROD_PG_PORT } else { "55432" }
$role = "predvestnik_preprod"

if ($port -notmatch '^\d+$') {
    throw "PREPROD_PG_PORT must be numeric."
}

$pgBin = $env:PREDVESTNIK_PG_BIN
if (-not $pgBin) {
    $install = Get-ChildItem -LiteralPath "C:\Program Files\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
        Sort-Object { if ($_.Name -match '^\d+$') { [int]$_.Name } else { -1 } } -Descending |
        Select-Object -First 1
    if ($install) {
        $pgBin = Join-Path $install.FullName "bin"
    }
}
if (-not $pgBin -or -not (Test-Path -LiteralPath (Join-Path $pgBin "pg_ctl.exe"))) {
    throw "PostgreSQL binaries were not found. Install PostgreSQL or set PREDVESTNIK_PG_BIN."
}

$initdb = Join-Path $pgBin "initdb.exe"
$pgCtl = Join-Path $pgBin "pg_ctl.exe"
$psql = Join-Path $pgBin "psql.exe"
$createdb = Join-Path $pgBin "createdb.exe"

function Initialize-PreprodCluster {
    if (Test-Path -LiteralPath (Join-Path $dataDir "PG_VERSION")) {
        return
    }
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    & $initdb --no-locale --encoding=UTF8 --auth=trust --username=$role --pgdata=$dataDir
    if ($LASTEXITCODE -ne 0) {
        throw "initdb failed with exit code $LASTEXITCODE."
    }
}

switch ($Action) {
    "start" {
        Initialize-PreprodCluster
        & $pgCtl --pgdata=$dataDir status *> $null
        if ($LASTEXITCODE -ne 0) {
            $logPath = Join-Path $dataDir "postgres.log"
            & $pgCtl --pgdata=$dataDir --wait --timeout=60 --options="-h 127.0.0.1 -p $port" --log=$logPath start
            if ($LASTEXITCODE -ne 0) {
                throw "PostgreSQL preprod cluster failed to start. See $logPath"
            }
        }

        $exists = & $psql --host=127.0.0.1 --port=$port --username=$role --dbname=postgres --tuples-only --no-align --command="SELECT 1 FROM pg_database WHERE datname='$role'"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not query the preprod PostgreSQL cluster."
        }
        if (($exists | Out-String).Trim() -ne "1") {
            & $createdb --host=127.0.0.1 --port=$port --username=$role $role
            if ($LASTEXITCODE -ne 0) {
                throw "Could not create database '$role'."
            }
        }
        Write-Output "PREPROD_POSTGRES_READY port=$port database=$role"
    }
    "stop" {
        if (Test-Path -LiteralPath (Join-Path $dataDir "postmaster.pid")) {
            & $pgCtl --pgdata=$dataDir --wait --timeout=30 stop
            if ($LASTEXITCODE -ne 0) {
                throw "PostgreSQL preprod cluster failed to stop cleanly."
            }
        }
        Write-Output "PREPROD_POSTGRES_STOPPED"
    }
    "status" {
        if (Test-Path -LiteralPath (Join-Path $dataDir "postmaster.pid")) {
            & $pgCtl --pgdata=$dataDir status
        } else {
            Write-Output "PREPROD_POSTGRES_STOPPED"
        }
    }
}
