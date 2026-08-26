[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$moduleRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$projectRoot = (Resolve-Path (Join-Path $moduleRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$dbPort = if ($env:PREPROD_PG_PORT) { $env:PREPROD_PG_PORT } else { "55432" }

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment is missing: $python"
}

& (Join-Path $PSScriptRoot "preprod_postgres.ps1") start

@(
    "BOT_TOKEN", "BOT_USERNAME", "DEVELOPER_ID", "DATABASE_URL",
    "PREDVESTNIK_DATABASE_URL", "COSMETIC_TEST_DATABASE_URL",
    "THEME_TEST_DATABASE_URL", "MINIAPP_URL", "PREPROD_MINIAPP_URL",
    "PREPROD_ALLOWED_TG_IDS", "PREDVESTNIK_ENV", "PORT", "ROOT_PATH"
) | ForEach-Object {
    Remove-Item -LiteralPath "Env:$_" -ErrorAction SilentlyContinue
}

$localDsn = "postgresql://predvestnik_preprod@127.0.0.1:$dbPort/predvestnik_preprod"
$env:PREDVESTNIK_ENV = "preprod"
$env:DATABASE_URL = $localDsn
$env:COSMETIC_TEST_DATABASE_URL = $localDsn
$env:THEME_TEST_DATABASE_URL = $localDsn
$env:BOT_TOKEN = "123456:offline-preprod-tests"
$env:BOT_USERNAME = "offline_preprod_test_bot"
$env:DEVELOPER_ID = "101"
$env:PREPROD_ALLOWED_TG_IDS = "101,202"
$env:MINIAPP_URL = "https://preprod.invalid/predvestnik"
$env:PORT = "0"
$env:PYTHONUTF8 = "1"

$tests = Get-ChildItem -LiteralPath (Join-Path $moduleRoot "tools") -Filter "test_*.py" |
    Sort-Object Name
$failed = @()

Push-Location $moduleRoot
try {
    foreach ($test in $tests) {
        $output = & $python $test.FullName 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Output "PASS $($test.Name)"
            continue
        }
        Write-Output "FAIL $($test.Name)"
        $output | Write-Output
        $failed += $test.Name
    }
} finally {
    Pop-Location
}

Write-Output "PREPROD_TESTS total=$($tests.Count) passed=$($tests.Count - $failed.Count) failed=$($failed.Count)"
if ($failed.Count -gt 0) {
    exit 1
}
