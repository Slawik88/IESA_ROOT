release: cd IESA_ROOT && python manage.py migrate --noinput
web: sh -c "cd IESA_ROOT && python manage.py migrate --noinput && gunicorn IESA_ROOT.wsgi:application --bind 0.0.0.0:$PORT"