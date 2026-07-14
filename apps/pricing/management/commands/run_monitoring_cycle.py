from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from apps.pricing.models import (
    CollectionRun,
    SearchScenario,
)


class Command(BaseCommand):
    help = (
        "Собирает справочник Maldives Bonus, цены Resort Holiday "
        "и Мальдивианы, затем строит сравнение и отчёты"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario-id",
            type=int,
            required=True,
            help="ID сценария поиска",
        )
        parser.add_argument(
            "--trigger",
            choices=("manual", "scheduled"),
            default="manual",
        )
        parser.add_argument(
            "--skip-bonus",
            action="store_true",
            help="Не обновлять справочник Maldives Bonus",
        )
        parser.add_argument(
            "--no-reports",
            action="store_true",
            help="Не создавать Excel и PDF",
        )

    def handle(self, *args, **options):
        try:
            scenario = SearchScenario.objects.get(
                id=options["scenario_id"],
                active=True,
            )
        except SearchScenario.DoesNotExist as error:
            raise CommandError("Активный сценарий поиска не найден.") from error

        if scenario.include_flight:
            raise CommandError("Первый этап поддерживает только туры без перелёта.")

        if scenario.include_transfer:
            raise CommandError(
                "Первый этап поддерживает только предложения без трансфера."
            )

        children_ages = ",".join(str(age) for age in (scenario.children_ages or []))
        check_in = scenario.check_in.isoformat()
        common_options = {
            "check_in": check_in,
            "nights": scenario.nights,
            "adults": scenario.adults,
            "children_ages": children_ages,
            "trigger": options["trigger"],
        }

        if not options["skip_bonus"]:
            self.stdout.write("Обновляем справочник Maldives Bonus (без цен)...")
            call_command(
                "collect_maldives_bonus",
                **common_options,
            )

        self.stdout.write("Собираем цены Resort Holiday...")
        call_command(
            "collect_resort",
            **common_options,
        )

        self.stdout.write("Собираем цены Мальдивианы...")
        call_command(
            "collect_maldiviana",
            **common_options,
        )

        selected_hotel_ids = ",".join(
            str(hotel_id)
            for hotel_id in scenario.hotels.values_list(
                "id",
                flat=True,
            )
        )

        previous_run_ids = set(
            CollectionRun.objects.filter(
                comparison_groups__isnull=False,
            ).values_list("id", flat=True)
        )

        self.stdout.write("Строим сравнение...")
        call_command(
            "build_comparisons",
            check_in=check_in,
            nights=scenario.nights,
            adults=scenario.adults,
            children_ages=children_ages,
            currency=scenario.preferred_currency,
            hotel_ids=selected_hotel_ids,
            trigger=options["trigger"],
            apply=True,
        )

        comparison_run = (
            CollectionRun.objects.filter(
                comparison_groups__isnull=False,
            )
            .exclude(id__in=previous_run_ids)
            .order_by("-id")
            .first()
        )

        if comparison_run is None:
            raise CommandError("Новый запуск сравнения не был создан.")

        if not options["no_reports"]:
            output_dir = Path(settings.BASE_DIR) / "reports_output"
            output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
            base_name = f"comparison_run_{comparison_run.id}"

            call_command(
                "export_comparison_excel",
                run_id=comparison_run.id,
                output=str(output_dir / f"{base_name}.xlsx"),
            )
            call_command(
                "export_comparison_pdf",
                run_id=comparison_run.id,
                output=str(output_dir / f"{base_name}.pdf"),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Цикл мониторинга завершён. ID сравнения: {comparison_run.id}"
            )
        )
