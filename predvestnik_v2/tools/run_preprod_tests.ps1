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
        # PowerShell 7 promotes native stderr to a NativeCommandError when the
        # caller uses ErrorActionPreference=Stop. Python tests intentionally
        # emit structured ERROR logs for exercised failure paths, so capture
        # stderr separately and classify the test only by its exit code.
        $stdoutPath = [System.IO.Path]::GetTempFileName()
        $stderrPath = [System.IO.Path]::GetTempFileName()
        try {
            $testProcess = Start-Process -FilePath $python -ArgumentList @($test.FullName) `
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
