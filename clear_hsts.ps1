# Скрипт для полной очистки HSTS в Edge для 127.0.0.1
Write-Host "🔧 Очистка HSTS для 127.0.0.1 в Microsoft Edge" -ForegroundColor Green
Write-Host ""

# Закрываем все процессы Edge
Write-Host "1️⃣  Закрытие всех процессов Edge..." -ForegroundColor Yellow
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Удаляем файлы HSTS из профиля Edge
Write-Host "2️⃣  Удаление файлов HSTS из профиля пользователя..." -ForegroundColor Yellow
$edgeDataPath = "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default"
$hstsPaths = @(
    "$edgeDataPath\TransportSecurity",
    "$edgeDataPath\Network\TransportSecurity"
)

foreach ($path in $hstsPaths) {
    if (Test-Path $path) {
        Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ Удалено: $path" -ForegroundColor Green
    } else {
        Write-Host "   ℹ️  Не найдено: $path" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "3️⃣  Запуск Edge..." -ForegroundColor Yellow
Start-Process msedge.exe -ArgumentList "--inprivate","http://127.0.0.1:8000/"

Write-Host ""
Write-Host "✅ HSTS очищен! Откройте:" -ForegroundColor Green
Write-Host "   http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host ""
Write-Host "Если всё ещё не работает, откройте в режиме InPrivate:" -ForegroundColor Yellow
Write-Host "   Ctrl+Shift+N -> http://127.0.0.1:8000/" -ForegroundColor White
