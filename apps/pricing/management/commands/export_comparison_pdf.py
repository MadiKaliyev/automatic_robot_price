from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from apps.pricing.models import CollectionRun
from apps.reports.services import PdfReportService


class Command(BaseCommand):
    help = "Экспортирует сохранённое сравнение цен в PDF"

    def add_arguments(self, parser):
        parser.add_argument(
            "--run-id",
            type=int,
            required=True,
            help="ID запуска сравнения",
        )
        parser.add_argument(
            "--output",
            required=True,
            help="Путь к PDF-файлу",
        )

    def handle(self, *args, **options):
        try:
            run = CollectionRun.objects.get(
                id=options["run_id"],
            )
        except CollectionRun.DoesNotExist as error:
            raise CommandError("Запуск сравнения не найден.") from error

        if not run.comparison_groups.exists():
            raise CommandError("В выбранном запуске нет результатов сравнения.")

        output_path = PdfReportService.export_run(
            run,
            Path(options["output"]),
        )

        self.stdout.write(self.style.SUCCESS(f"PDF сохранён: {output_path}"))
