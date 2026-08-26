[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$moduleRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$projectRoot = (Resolve-Path (Join-Path $moduleRoot "..")).Path
$envFile = Join-Path $moduleRoot ".env.test"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Preprod requires $envFile"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment is missing: $python"
}

$fileEnv = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*#' -or $line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        continue
    }
    $key = $matches[1]
    $value = $matches[2].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    $fileEnv[$key] = $value
}

$required = @("BOT_TOKEN", "BOT_USERNAME", "DEVELOPER_ID", "PREPROD_ALLOWED_TG_IDS")
foreach ($key in $required) {
    if (-not $fileEnv[$key]) {
        throw ".env.test is missing required key '$key'."
    }
}

$miniappUrl = if ($fileEnv["PREPROD_MINIAPP_URL"]) {
    $fileEnv["PREPROD_MINIAPP_URL"]
} else {
    $fileEnv["MINIAPP_URL"]
}
if ($miniappUrl -notmatch '^https://') {
    throw ".env.test requires an HTTPS MINIAPP_URL or PREPROD_MINIAPP_URL."
}
if (-not $miniappUrl.TrimEnd('/').EndsWith('/predvestnik')) {
    throw "The preprod Mini App URL must end with /predvestnik."
}

$dbPort = if ($env:PREPROD_PG_PORT) { $env:PREPROD_PG_PORT } else { "55432" }
$apiPort = if ($env:PREPROD_API_PORT) { $env:PREPROD_API_PORT } else { "8403" }
if ($dbPort -notmatch '^\d+$' -or $apiPort -notmatch '^\d+$') {
    throw "Preprod ports must be numeric."
}

& (Join-Path $PSScriptRoot "preprod_postgres.ps1") start

# Clear production-compatible values before python-dotenv reads .env.test.
@(
    "BOT_TOKEN", "BOT_USERNAME", "DEVELOPER_ID", "TIMEZONE_OFFSET", "GEMINI_API_KEY",
    "DATABASE_URL", "PREDVESTNIK_DATABASE_URL", "MINIAPP_URL", "PREPROD_MINIAPP_URL",
    "PREPROD_ALLOWED_TG_IDS", "PREDVESTNIK_ENV", "PORT", "ROOT_PATH", "PYTHONUTF8"
) | ForEach-Object {
    Remove-Item -LiteralPath "Env:$_" -ErrorAction SilentlyContinue
}

$env:PREDVESTNIK_ENV = "preprod"
$env:PREPROD_ALLOWED_TG_IDS = $fileEnv["PREPROD_ALLOWED_TG_IDS"]
$env:DATABASE_URL = "postgresql://predvestnik_preprod@127.0.0.1:$dbPort/predvestnik_preprod"
$env:PORT = $apiPort
$env:ROOT_PATH = "/predvestnik"
$env:MINIAPP_URL = $miniappUrl
$env:PYTHONUTF8 = "1"

Push-Location $moduleRoot
try {
    & $python -m bot
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
