# Запуск Django сервера в режиме HTTPS для локальной разработки
# HTTPS Development Server with SSL

Write-Host "🔒 Запуск сервера в режиме HTTPS (с SSL)..." -ForegroundColor Green
Write-Host ""

$env:DEBUG = 'True'
$env:SECURE_SSL_REDIRECT = 'False'

Write-Host "📋 Настройки:" -ForegroundColor Cyan
Write-Host "   DEBUG: True" -ForegroundColor Yellow
Write-Host "   SECURE_SSL_REDIRECT: False (для локальной разработки)" -ForegroundColor Yellow
Write-Host "   URL: https://127.0.0.1:8443/" -ForegroundColor Yellow
Write-Host ""
Write-Host "⚠️  Браузер покажет предупреждение о самоподписанном сертификате - это нормально!" -ForegroundColor Magenta
Write-Host ""

..\venv\Scripts\python.exe .\manage.py runsslserver 127.0.0.1:8443
