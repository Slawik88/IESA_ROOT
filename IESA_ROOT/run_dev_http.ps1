# Запуск Django сервера в режиме HTTP для локальной разработки
# HTTP Development Server - No SSL

Write-Host "🚀 Запуск сервера в режиме HTTP (без SSL)..." -ForegroundColor Green
Write-Host ""

$env:DEBUG = 'True'
$env:SECURE_SSL_REDIRECT = 'False'

Write-Host "📋 Настройки:" -ForegroundColor Cyan
Write-Host "   DEBUG: True" -ForegroundColor Yellow
Write-Host "   SECURE_SSL_REDIRECT: False" -ForegroundColor Yellow
Write-Host "   URL: http://127.0.0.1:8000/" -ForegroundColor Yellow
Write-Host ""

..\venv\Scripts\python.exe .\manage.py runserver
