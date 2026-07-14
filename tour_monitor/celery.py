import os

from celery import Celery

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "tour_monitor.settings",
)

app = Celery("tour_monitor")
app.config_from_object(
    "django.conf:settings",
    namespace="CELERY",
)
app.autodiscover_tasks()
