from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.catalog.models import (
    Hotel,
    MatchStatus,
    MealPlan,
    RoomCategory,
    Source,
    SourceHotel,
    SourceRoomCategory,
)
from apps.pricing.models import CollectionRun, PriceOffer, RunStatus, SearchScenario
from apps.pricing.services import ComparisonService


class Command(BaseCommand):
    help = "Создаёт демонстрационные цены трёх источников и сравнивает их"

    def handle(self, *args, **options):
        hotel, _ = Hotel.objects.get_or_create(
            country="Сейшелы", canonical_name="Savoy Seychelles Resort & Spa"
        )
        room, _ = RoomCategory.objects.get_or_create(
            hotel=hotel, canonical_name="Standard Room"
        )
        meal, _ = MealPlan.objects.get_or_create(
            code="BB", defaults={"name": "Завтрак"}
        )
        scenario, _ = SearchScenario.objects.get_or_create(
            name="Демо: Сейшелы, 2 взрослых, 7 ночей",
            defaults={
                "destination": "Сейшелы",
                "check_in": date(2026, 9, 10),
                "nights": 7,
                "adults": 2,
            },
        )
        scenario.hotels.add(hotel)
        run = CollectionRun.objects.create(
            scenario=scenario, status=RunStatus.RUNNING, trigger="demo"
        )

        samples = [
            ("maldives_bonus", "Savoy Seychelles Resort & Spa", Decimal("1800.00")),
            ("resort_holiday", "Savoy Resort Seychelles", Decimal("1950.00")),
            ("maldiviana", "Savoy Spa Resort", Decimal("2000.00")),
        ]
        for code, source_name, price in samples:
            source, _ = Source.objects.get_or_create(
                code=code, defaults={"name": code.replace("_", " ").title()}
            )
            source_hotel, _ = SourceHotel.objects.get_or_create(
                source=source,
                source_name=source_name,
                defaults={"hotel": hotel, "match_status": MatchStatus.CONFIRMED},
            )
            if source_hotel.hotel_id != hotel.id:
                source_hotel.hotel = hotel
                source_hotel.match_status = MatchStatus.CONFIRMED
                source_hotel.save(update_fields=("hotel", "match_status"))
            source_room, _ = SourceRoomCategory.objects.get_or_create(
                source_hotel=source_hotel,
                source_name="Standard Room",
                defaults={"room_category": room, "match_status": MatchStatus.CONFIRMED},
            )
            PriceOffer.objects.create(
                run=run,
                source=source,
                source_hotel=source_hotel,
                hotel=hotel,
                source_room=source_room,
                room_category=room,
                meal_plan=meal,
                check_in=scenario.check_in,
                nights=scenario.nights,
                adults=2,
                transfer_included=False,
                taxes_included=True,
                price=price,
                currency="USD",
                raw_data={"demo": True},
            )

        groups = ComparisonService.build_for_run(run)
        run.status = RunStatus.SUCCESS
        run.finished_at = timezone.now()
        run.save(update_fields=("status", "finished_at"))

        self.stdout.write(self.style.SUCCESS(f"Создано групп сравнения: {len(groups)}"))
        for group in groups:
            self.stdout.write(
                f"Лучшая цена: {group.best_offer.source.name} — {group.best_price} {group.currency}"
            )
            for item in group.items.select_related("offer__source").all():
                self.stdout.write(
                    f"  {item.offer.source.name}: {item.offer.price} {group.currency}; "
                    f"+{item.absolute_difference}; +{item.percent_difference}%; {item.color_status}"
                )
