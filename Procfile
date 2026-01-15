release: cd IESA_ROOT && python manage.py migrate --noinput
web: cd IESA_ROOT && gunicorn IESA_ROOT.wsgi:application --bind 0.0.0.0:$PORT