[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$apiPort = if ($env:PREPROD_API_PORT) { $env:PREPROD_API_PORT } else { "8403" }
if ($apiPort -notmatch '^\d+$') {
    throw "PREPROD_API_PORT must be numeric."
}

$cloudflared = Get-Command cloudflared.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
if (-not $cloudflared) {
    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $cloudflared = Get-ChildItem -LiteralPath $packageRoot -Directory -Filter "Cloudflare.cloudflared*" -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter "cloudflared.exe" -File } |
        Select-Object -ExpandProperty FullName -First 1
}
if (-not $cloudflared) {
    throw "cloudflared.exe was not found. Install Cloudflare.cloudflared with winget."
}

Write-Output "When the tunnel URL appears, append /predvestnik and save it as MINIAPP_URL and PREPROD_MINIAPP_URL in predvestnik_v2/.env.test."
& $cloudflared tunnel --url "http://127.0.0.1:$apiPort" --no-autoupdate
exit $LASTEXITCODE
