from celery import shared_task
from django.core.management import call_command

from apps.pricing.models import SearchScenario


@shared_task
def run_scheduled_monitoring() -> dict:
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
