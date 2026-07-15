from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command

from apps.pricing.models import SearchScenario

MONITORING_LOCK_KEY = "pricing:scheduled-monitoring:lock"


@shared_task
def run_scheduled_monitoring() -> dict:
    lock_acquired = cache.add(
        MONITORING_LOCK_KEY,
        "running",
        timeout=settings.MONITORING_LOCK_TIMEOUT_SECONDS,
    )
    if not lock_acquired:
        return {
            "completed": [],
            "failures": [],
            "skipped": "previous monitoring cycle is still running",
        }

    try:
        return _run_enabled_scenarios()
    finally:
        cache.delete(MONITORING_LOCK_KEY)


def _run_enabled_scenarios() -> dict:
    scenario_ids = list(
        SearchScenario.objects.filter(
            active=True,
            automatic_enabled=True,
        ).values_list("id", flat=True)
    )

    completed = []
    failures = []

    for index, scenario_id in enumerate(scenario_ids):
        try:
            call_command(
                "run_monitoring_cycle",
                scenario_id=scenario_id,
                trigger="scheduled",
                skip_bonus=index > 0,
            )
        except Exception as error:
            failures.append(
                {
                    "scenario_id": scenario_id,
                    "error": str(error),
                }
            )
        else:
            completed.append(scenario_id)

    return {
        "completed": completed,
        "failures": failures,
    }
