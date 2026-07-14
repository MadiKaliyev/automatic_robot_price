# Развёртывание

## Временная демонстрация на Windows

```powershell
$env:DJANGO_DEBUG="1"
$env:DJANGO_ALLOWED_HOSTS="*"
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 tour_monitor.wsgi:application
```

Публичный HTTPS-туннель можно направить на `http://127.0.0.1:8000`. Такой адрес временный: он работает только пока запущены Waitress, туннель и компьютер. Не используйте демонстрационный режим для постоянной эксплуатации.

## Постоянный сервер

1. PostgreSQL передаётся через `DATABASE_URL`, Redis — через `CELERY_BROKER_URL`.
2. `DJANGO_DEBUG=0`, задаются случайный `DJANGO_SECRET_KEY` и конкретные `DJANGO_ALLOWED_HOSTS`.
3. Для HTTPS включаются secure-cookie, SSL redirect и HSTS после проверки домена.
4. Выполняются `migrate` и `collectstatic`; статика отдаётся WhiteNoise, пользовательские изображения — отдельным хранилищем или reverse proxy.
5. Web-процесс, Celery worker и Celery Beat запускаются как системные службы.
6. Настраиваются резервные копии БД и media, журналирование, алерты и ограничение доступа к `/admin/`.

Пример обязательных production-переменных:

```dotenv
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=replace-with-a-long-random-value
DJANGO_ALLOWED_HOSTS=prices.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://prices.example.com
DATABASE_URL=postgresql://user:password@db:5432/hotels
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
SECURE_SSL_REDIRECT=1
SECURE_HSTS_SECONDS=31536000
```
