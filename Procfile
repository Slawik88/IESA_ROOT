release: cd IESA_ROOT && python manage.py migrate --noinput
web: sh -c "cd IESA_ROOT && python manage.py migrate --noinput && daphne -b 0.0.0.0 -p $PORT IESA_ROOT.asgi:application"