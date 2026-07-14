from django.core.management.base import BaseCommand

from apps.catalog.models import MealPlan, Source


class Command(BaseCommand):
    help = "Создаёт три источника и базовые типы питания"

    def handle(self, *args, **options):
        sources = [
            ("maldives_bonus", "Maldives Bonus", "https://maldives-bonus.ru/"),
            ("resort_holiday", "Resort Holiday", "https://resort-holiday.com/"),
            ("maldiviana", "Мальдивиана", "https://maldives.ru/"),
        ]
        for code, name, url in sources:
            Source.objects.update_or_create(
                code=code, defaults={"name": name, "base_url": url}
            )

        meals = [
            ("RO", "Без питания"),
            ("BB", "Завтрак"),
            ("HB", "Завтрак и ужин"),
            ("FB", "Трёхразовое питание"),
            ("AI", "Всё включено"),
        ]
        for code, name in meals:
            MealPlan.objects.update_or_create(code=code, defaults={"name": name})
        self.stdout.write(
            self.style.SUCCESS("Начальные источники и типы питания созданы.")
        )
