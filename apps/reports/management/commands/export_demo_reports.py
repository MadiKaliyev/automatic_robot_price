from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, call_command

from apps.pricing.models import CollectionRun
from apps.reports.services import ExcelReportService, PdfReportService


class Command(BaseCommand):
    help = "Создаёт демонстрационные Excel- и PDF-отчёты"

    def handle(self, *args, **options):
        run = (
            CollectionRun.objects.filter(
                trigger="demo", comparison_groups__isnull=False
            )
            .distinct()
            .first()
        )
        if run is None:
            call_command("demo_comparison")
            run = (
                CollectionRun.objects.filter(
                    trigger="demo", comparison_groups__isnull=False
                )
                .distinct()
                .first()
            )

        output_dir = Path(settings.BASE_DIR) / "reports_output"
        excel_path = ExcelReportService.export_run(
            run, output_dir / "demo_comparison.xlsx"
        )
        pdf_path = PdfReportService.export_run(run, output_dir / "demo_comparison.pdf")
        self.stdout.write(self.style.SUCCESS(f"Excel: {excel_path}"))
        self.stdout.write(self.style.SUCCESS(f"PDF: {pdf_path}"))
