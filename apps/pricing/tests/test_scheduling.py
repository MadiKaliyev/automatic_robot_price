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

    @patch("apps.pricing.tasks.cache.add", return_value=False)
    @patch("apps.pricing.tasks.call_command")
    def test_skips_cycle_when_previous_one_is_running(
        self,
        mocked_call_command,
        mocked_cache_add,
    ):
        result = run_scheduled_monitoring.run()

        self.assertEqual(
            result,
            {
                "completed": [],
                "failures": [],
                "skipped": "previous monitoring cycle is still running",
            },
        )
        mocked_cache_add.assert_called_once()
        mocked_call_command.assert_not_called()
