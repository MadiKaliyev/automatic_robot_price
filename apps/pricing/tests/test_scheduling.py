from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.pricing.models import SearchScenario
from apps.pricing.tasks import run_scheduled_monitoring


class ScheduledMonitoringTests(TestCase):
    @patch("apps.pricing.tasks.call_command")
    def test_runs_only_enabled_scenarios(
        self,
        mocked_call_command,
    ):
        enabled = SearchScenario.objects.create(
            name="Enabled",
            check_in=date(2026, 9, 10),
            nights=7,
            automatic_enabled=True,
        )
        SearchScenario.objects.create(
            name="Disabled",
            check_in=date(2026, 9, 10),
            nights=7,
            automatic_enabled=False,
        )

        result = run_scheduled_monitoring.run()

        self.assertEqual(
            result,
            {
                "completed": [enabled.id],
                "failures": [],
            },
        )
        mocked_call_command.assert_called_once_with(
            "run_monitoring_cycle",
            scenario_id=enabled.id,
            trigger="scheduled",
            skip_bonus=False,
        )
