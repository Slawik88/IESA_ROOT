# 07 · Локальный запуск сайта и тесты

ОС пользователя — Windows 11. Системный `python` **без Django**; нужен `.venv` из корня основного
репозитория (`F:\GitsRepos\IESA_ROOT\.venv`, Python 3.11). Для git-worktree используй тот же `.venv`
по абсолютному пути.

## Запуск

Из папки `IESA_ROOT/` (там `manage.py`), PowerShell:

```powershell
$env:PYTHONUTF8 = '1'                      # консоль Windows в cp1251, старые миграции печатают «→»
$env:DJANGO_SETTINGS_MODULE = 'IESA_ROOT.settings_dev'
& F:\GitsRepos\IESA_ROOT\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

`settings_dev.py` сам: подставляет заглушку `SECRET_KEY`, снимает `sslserver`, отключает HTTPS-редирект,
печатает письма в консоль и использует **копию базы** `IESA_ROOT/dev.sqlite3` (создаётся из `db.sqlite3`
при первом запуске; `*.sqlite3` игнорируется git). Миграции: `manage.py migrate`.

Запуск через инструмент предпросмотра: серверы запускать только `preview_start`/фоновой командой, а не `&` в Bash.
Если сервер запущен с `--noreload`, **шаблоны и Python кэшируются** — после правок перезапусти процесс.
Порт занят: `netstat -ano | findstr :8000` → `taskkill /PID … /F`.

Браузер кэширует статику эвристически: после правки JS/CSS делай `fetch(url,{cache:'reload'})` и перезагрузку.
Service worker локально обычно не включён.

## Тесты

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; $env:DJANGO_SETTINGS_MODULE='IESA_ROOT.settings_dev'
python manage.py test --noinput            # весь набор, ~3–4 минуты, ~150 тестов
python manage.py test users --noinput      # только пакет users (~2 мин)
python manage.py test users.tests_auth_flows.RegistrationFlowTests --noinput   # точечно
python manage.py makemigrations --check --dry-run                               # миграции не забыты?
```

Тестовая БД создаётся автоматически (включая таблицу БД-кэша). Тесты, использующие rate-limit, чистят
`caches['ratelimit']` в `setUp`. Для POST-форм с антиботом используй `users.tests_support.human_fields()`.

## Проверка «как на проде» (DEBUG=False + хешированная статика)

Поймает падения `{% static %}` на несуществующий файл и ошибки CSP. Одноразовый файл настроек вне репозитория:

```python
# prodlike_settings.py (положить в папку вне репозитория и добавить её в PYTHONPATH)
from IESA_ROOT.settings import *
import tempfile, os
DEBUG = False; ALLOWED_HOSTS = ['*']; SECRET_KEY = 'prodlike-test-key-0123456789abcdef0123456789'
SECURE_SSL_REDIRECT = False
STATIC_ROOT = os.path.join(tempfile.gettempdir(), 'iesa_prodlike_static')
DATABASES['default']['NAME'] = r'<путь к копии dev.sqlite3>'
```

Затем: `DEBUG=False`, `manage.py collectstatic --clear --noinput`, и `django.test.Client(HTTP_HOST='iesasport.ch')`
с `secure=True` — запросить `/`, `/auth/login/`, `/auth/register/`, `/auth/password-reset/`, `/privacy/`, `/blog/`
(ожидаем 200).

## Мобильная проверка

`resize_window` пресет `mobile` (375×812) во встроенном браузере; после теста — `desktop`. Проверяй формы
реальным вводом, а не только скриптом: баги регистрации на телефоне (дисейбл кнопок после автозаполнения,
расхождение клиентской/серверной проверки пароля) находились именно так.

## Грабли среды

- В Bash-инструменте длинные heredoc с кавычками иногда ломаются — пиши скрипт в файл (инструментом Write)
  и запускай его.
- Правка файлов питоном: читай/пиши с `newline=''` и сохраняй исходные окончания строк (в репо смесь CRLF/LF).
- Фоновые команды запускай с `run_in_background`, не блокируй сессию `sleep`; ждать — `Monitor` с until-циклом.
- Скриншоты браузера масштабируются: координаты кликов брать из системы координат скриншота.
- Секреты, прочитанные из панелей, не печатать и не записывать в файлы репозитория.
