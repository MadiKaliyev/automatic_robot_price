from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import (
    Hotel,
    MealPlan,
    RoomCategory,
    Source,
    SourceHotel,
    SourceRoomCategory,
)
from apps.pricing.models import CollectionRun, PriceOffer, SearchScenario
from apps.pricing.services import ComparisonService


class ComparisonServiceTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            country="Сейшелы", canonical_name="Test Hotel"
        )
        self.room = RoomCategory.objects.create(
            hotel=self.hotel, canonical_name="Standard"
        )
        self.meal = MealPlan.objects.create(code="BB", name="Завтрак")
        self.scenario = SearchScenario.objects.create(
            name="Test", check_in=date(2026, 9, 10), nights=7
        )
        self.run = CollectionRun.objects.create(scenario=self.scenario)

    def add_offer(
        self,
        code,
        price,
        room=None,
        included_components=None,
    ):
        source = Source.objects.create(code=code, name=code)
        source_hotel = SourceHotel.objects.create(
            source=source, hotel=self.hotel, source_name=f"Hotel {code}"
        )
        room = room or self.room
        source_room = SourceRoomCategory.objects.create(
            source_hotel=source_hotel,
            room_category=room,
            source_name=room.canonical_name,
        )
        return PriceOffer.objects.create(
            run=self.run,
            source=source,
            source_hotel=source_hotel,
            hotel=self.hotel,
            source_room=source_room,
            room_category=room,
            meal_plan=self.meal,
            check_in=date(2026, 9, 10),
            nights=7,
            adults=2,
            price=price,
            currency="USD",
            transfer_included=False,
            taxes_included=True,
            included_components=(included_components or {}),
        )

    def test_calculates_best_price_and_percent(self):
        self.add_offer("one", Decimal("1800"))
        self.add_offer("two", Decimal("1980"))
        groups = ComparisonService.build_for_run(self.run)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group.best_price, Decimal("1800"))
        expensive = group.items.get(offer__source__code="two")
        self.assertEqual(expensive.absolute_difference, Decimal("180"))
        self.assertEqual(expensive.percent_difference, Decimal("10.00"))
        self.assertEqual(expensive.color_status, "orange")

    def test_does_not_compare_different_room_categories(self):
        other_room = RoomCategory.objects.create(
            hotel=self.hotel, canonical_name="Deluxe"
        )
        self.add_offer("one", Decimal("1800"), room=self.room)
        self.add_offer("two", Decimal("1700"), room=other_room)
        groups = ComparisonService.build_for_run(self.run)
        self.assertEqual(groups, [])

    def test_does_not_compare_different_price_composition(self):
        self.add_offer(
            "one",
            Decimal("1800"),
            included_components={
                "hotel": True,
                "flight": False,
            },
        )
        self.add_offer(
            "two",
            Decimal("1700"),
            included_components={
                "hotel": True,
                "flight": True,
            },
        )

        groups = ComparisonService.build_for_run(self.run)

        self.assertEqual(groups, [])
