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
# Tests are executed as files from tools/, so Python otherwise places tools/
# rather than the module root on sys.path.  Keep imports identical to the
# application and to direct developer runs.
$env:PYTHONPATH = $moduleRoot

# The owner-approved reconstruction plan explicitly retires the former
# Reconstruction/Chronicle combat product.  These tests describe that removed
# product (and in a few cases even demand that it remains the only entry), so
# treating them as release gates would silently override the product contract.
$retiredContractTests = @(
    "test_chronicle_feats_v1.py",
    "test_companion_combat_roles.py",
    # This describes the retired player crypto exchange and requires its
    # notification scheduler to start.  The approved release scope keeps no
    # such market or background writer; historical rows stay for compensation.
    "test_lore_exchange_contract.py"
)
$tests = Get-ChildItem -LiteralPath (Join-Path $moduleRoot "tools") -Filter "test_*.py" |
    Where-Object { $_.Name -notin $retiredContractTests } |
    Sort-Object Name
$failed = @()

Push-Location $moduleRoot
try {
    foreach ($test in $tests) {
        # PowerShell 7 promotes native stderr to a NativeCommandError when the
        # caller uses ErrorActionPreference=Stop. Python tests intentionally
        # emit structured ERROR logs for exercised failure paths, so capture
        # stderr separately and classify the test only by its exit code.
        $stdoutPath = [System.IO.Path]::GetTempFileName()
        $stderrPath = [System.IO.Path]::GetTempFileName()
        try {
            $testArgs = @($test.FullName)
            # A small group of isolated PostgreSQL proofs deliberately require
            # an explicit DSN instead of silently reading the environment.
            # The all-tests runner already owns the disposable preprod DSN.
            if (Select-String -LiteralPath $test.FullName -Pattern 'add_argument\(["'']--dsn' -Quiet) {
                $testArgs += @("--dsn", $localDsn)
            }
            $testProcess = Start-Process -FilePath $python -ArgumentList $testArgs `
                -WorkingDirectory $moduleRoot -RedirectStandardOutput $stdoutPath `
                -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru -Wait
            $testExitCode = $testProcess.ExitCode
            $output = @(Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue)
            $stderrOutput = @(Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue)
            if ($stderrOutput.Count) {
                $output = @($output) + $stderrOutput
            }
        } finally {
            Remove-Item -LiteralPath $stdoutPath,$stderrPath -Force -ErrorAction SilentlyContinue
        }
        if ($testExitCode -eq 0) {
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
