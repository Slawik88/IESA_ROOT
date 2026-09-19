<#
Start a disposable, externally checked preprod tunnel and point the test bot's
menu button at it. Quick Tunnel URLs are temporary; this removes manual copy.
#>
[CmdletBinding()]
param([switch]$NoWait)

$ErrorActionPreference = 'Stop'
$apiPort = if ($env:PREPROD_API_PORT) { $env:PREPROD_API_PORT } else { '8403' }
if ($apiPort -notmatch '^\d+$') { throw 'PREPROD_API_PORT must be numeric.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.env.test'
if (-not (Test-Path -LiteralPath $envFile)) { throw '.env.test is required for the isolated preprod tunnel.' }

$cloudflared = Get-Command cloudflared.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
if (-not $cloudflared) {
    $packageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    $cloudflared = Get-ChildItem -LiteralPath $packageRoot -Directory -Filter 'Cloudflare.cloudflared*' -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter 'cloudflared.exe' -File } |
        Select-Object -ExpandProperty FullName -First 1
}
if (-not $cloudflared) { throw 'cloudflared.exe was not found. Install Cloudflare.cloudflared with winget.' }

$runId = [guid]::NewGuid().ToString('N')
$stdoutPath = Join-Path $env:TEMP "predvestnik-tunnel-$runId.out.log"
$stderrPath = Join-Path $env:TEMP "predvestnik-tunnel-$runId.err.log"
$process = Start-Process -FilePath $cloudflared -ArgumentList @(
    'tunnel', '--url', "http://127.0.0.1:$apiPort", '--protocol', 'http2', '--no-autoupdate'
) -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru

try {
    $baseUrl = $null
    for ($attempt = 0; $attempt -lt 60 -and -not $baseUrl; $attempt++) {
        Start-Sleep -Milliseconds 500
        $logs = @(
            Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue
            Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue
        ) -join "`n"
        $match = [regex]::Match($logs, 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) { $baseUrl = $match.Value }
    }
    if (-not $baseUrl) { throw 'Cloudflare did not issue a Quick Tunnel URL within 30 seconds.' }
    $menuUrl = "$baseUrl/predvestnik"

    # Do not advertise a URL until the public edge reaches the actual Mini App.
    $healthy = $false
    # DNS publication for a fresh Quick Tunnel is occasionally slower than the
    # connector registration; retain the previously advertised menu URL until
    # this full minute of external probes proves the replacement is usable.
    for ($attempt = 0; $attempt -lt 120 -and -not $healthy; $attempt++) {
        try { $healthy = (Invoke-WebRequest -UseBasicParsing -Uri "$menuUrl/" -TimeoutSec 5).StatusCode -eq 200 }
        catch { $healthy = $false }
        if (-not $healthy) { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'The new public URL did not return HTTP 200; Telegram menu was not changed.' }

    $lines = [System.IO.File]::ReadAllLines($envFile)
    $hasMiniAppUrl = $false
    $nextLines = foreach ($line in $lines) {
        if ($line -match '^MINIAPP_URL=') { $hasMiniAppUrl = $true; "MINIAPP_URL=$menuUrl" }
        elseif ($line -match '^PREPROD_MINIAPP_URL=') { "PREPROD_MINIAPP_URL=$menuUrl" }
        else { $line }
    }
    if (-not $hasMiniAppUrl) { throw '.env.test has no MINIAPP_URL entry.' }
    [System.IO.File]::WriteAllLines($envFile, [string[]]$nextLines)

    $tokenLine = $nextLines | Where-Object { $_ -match '^BOT_TOKEN=' } | Select-Object -First 1
    if (-not $tokenLine) { throw '.env.test has no BOT_TOKEN for test-menu update.' }
    $token = ($tokenLine -replace '^BOT_TOKEN=', '').Trim(' ', '"', "'")
    if (-not $token) { throw 'BOT_TOKEN is empty.' }
    # Keep this wire value ASCII: this script is also run by Windows PowerShell
    # hosts that may decode a locally edited .ps1 with the wrong legacy codepage.
    $body = @{ menu_button = @{ type = 'web_app'; text = 'Play'; web_app = @{ url = $menuUrl } } } |
        ConvertTo-Json -Depth 5 -Compress
    $telegram = Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$token/setChatMenuButton" `
        -ContentType 'application/json' -Body $body -TimeoutSec 20
    if (-not $telegram.ok) { throw 'Telegram rejected the test-menu update.' }

    Write-Output "PREPROD_TUNNEL_READY $menuUrl"
    Write-Output "PREPROD_TUNNEL_PID $($process.Id)"
    Write-Output "PREPROD_TUNNEL_LOG $stdoutPath"
    if (-not $NoWait) { Wait-Process -Id $process.Id }
} catch {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    throw
}
