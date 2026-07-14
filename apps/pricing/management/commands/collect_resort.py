from datetime import date
from hashlib import sha1

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction
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
from apps.integrations.adapters.resort_holiday import (
    ResortHolidayAdapter,
)
from apps.integrations.base import SearchRequest
from apps.pricing.management.command_utils import (
    parse_children_ages,
)
from apps.pricing.models import (
    CollectionRun,
    PriceOffer,
    RunStatus,
    SearchScenario,
)

SOURCE_CODE = "resort_holiday"
SOURCE_NAME = "Resort Holiday"
SOURCE_URL = "https://search.resort-holiday.com/search_hotel"


MEAL_CODES = {
    "без питания": ("RO", "Без питания"),
    "room only": ("RO", "Без питания"),
    "bed breakfast": ("BB", "Завтрак"),
    "bed & breakfast": ("BB", "Завтрак"),
    "half board": ("HB", "Полупансион"),
    "full board": ("FB", "Полный пансион"),
    "all inclusive": ("AI", "Всё включено"),
}


def shorten_name(value: str) -> str:
    value = value.strip()

    if not value:
        return "Не указано"

    return value[:255]


def get_meal_data(source_name: str) -> tuple[str, str]:
    normalized = source_name.lower().strip()

    if normalized in MEAL_CODES:
        return MEAL_CODES[normalized]

    code = "X" + sha1(normalized.encode("utf-8")).hexdigest()[:19].upper()

    return code, source_name or "Не указано"


class Command(BaseCommand):
    help = "Собирает реальные цены Resort Holiday и сохраняет их в базу данных"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-in",
            default="2026-09-10",
            help="Дата заезда в формате ГГГГ-ММ-ДД",
        )

        parser.add_argument(
            "--nights",
            type=int,
            default=7,
            help="Количество ночей",
        )

        parser.add_argument(
            "--adults",
            type=int,
            default=2,
            help="Количество взрослых",
        )

        parser.add_argument(
            "--children-ages",
            default="",
            help="Возраст детей через запятую, например: 4,9",
        )

        parser.add_argument(
            "--show-browser",
            action="store_true",
            help="Показывать окно браузера во время сбора",
        )

        parser.add_argument(
            "--trigger",
            choices=("manual", "scheduled"),
            default="manual",
            help="Способ запуска",
        )

    def handle(self, *args, **options):
        try:
            check_in = date.fromisoformat(options["check_in"])
        except ValueError as error:
            raise CommandError("Дата должна быть в формате ГГГГ-ММ-ДД") from error

        nights = options["nights"]
        adults = options["adults"]
        children_ages = parse_children_ages(options["children_ages"])

        if nights < 1:
            raise CommandError("Количество ночей должно быть больше нуля")

        if adults < 1:
            raise CommandError("Количество взрослых должно быть больше нуля")

        scenario_name = (
            f"Resort Holiday: Сейшелы, "
            f"{check_in:%d.%m.%Y}, "
            f"{nights} ночей, "
            f"{adults} взрослых"
        )

        if children_ages:
            scenario_name += ", дети " + ",".join(map(str, children_ages))

        scenario, _ = SearchScenario.objects.update_or_create(
            name=scenario_name,
            defaults={
                "destination": "Сейшелы",
                "check_in": check_in,
                "nights": nights,
                "adults": adults,
                "children_ages": list(children_ages),
                "include_flight": False,
                "include_transfer": False,
                "first_available_only": True,
                "preferred_currency": "EUR",
                "active": True,
            },
        )

        run = CollectionRun.objects.create(
            scenario=scenario,
            status=RunStatus.RUNNING,
            trigger=options["trigger"],
        )

        request = SearchRequest(
            check_in=check_in,
            nights=nights,
            adults=adults,
            children_ages=children_ages,
            include_transfer=False,
        )

        self.stdout.write("Запускаем сбор Resort Holiday...")

        try:
            offers = ResortHolidayAdapter(
                headless=not options["show_browser"],
            ).fetch(request)

            if not offers:
                raise RuntimeError("Resort Holiday не вернул предложений")

            source, _ = Source.objects.update_or_create(
                code=SOURCE_CODE,
                defaults={
                    "name": SOURCE_NAME,
                    "base_url": SOURCE_URL,
                    "enabled": True,
                },
            )

            saved_count = 0
            hotel_ids = set()

            with transaction.atomic():
                for offer in offers:
                    hotel_name = shorten_name(offer.source_hotel_name)

                    provisional_hotel, _ = Hotel.objects.get_or_create(
                        country="Сейшелы",
                        canonical_name=hotel_name,
                        defaults={
                            "destination": "",
                            "active": True,
                        },
                    )

                    source_hotel, created = SourceHotel.objects.get_or_create(
                        source=source,
                        source_name=hotel_name,
                        defaults={
                            "source_code": (offer.source_hotel_code),
                            "hotel": provisional_hotel,
                            "match_status": (MatchStatus.REVIEW),
                            "active": True,
                        },
                    )

                    if source_hotel.hotel_id is None:
                        source_hotel.hotel = provisional_hotel
                        source_hotel.save(update_fields=("hotel",))

                    if not source_hotel.source_code and offer.source_hotel_code:
                        source_hotel.source_code = offer.source_hotel_code
                        source_hotel.save(update_fields=("source_code",))

                    hotel = source_hotel.hotel
                    hotel_ids.add(hotel.id)

                    room_name = shorten_name(offer.source_room_name)

                    provisional_room, _ = RoomCategory.objects.get_or_create(
                        hotel=hotel,
                        canonical_name=room_name,
                        defaults={
                            "active": True,
                        },
                    )

                    source_room, created = SourceRoomCategory.objects.get_or_create(
                        source_hotel=source_hotel,
                        source_name=room_name,
                        defaults={
                            "source_code": (offer.source_room_code),
                            "room_category": (provisional_room),
                            "match_status": (MatchStatus.REVIEW),
                        },
                    )

                    if source_room.room_category_id is None:
                        source_room.room_category = provisional_room
                        source_room.save(update_fields=("room_category",))

                    meal_code, meal_name = get_meal_data(offer.meal_code)

                    meal_plan, _ = MealPlan.objects.get_or_create(
                        code=meal_code,
                        defaults={
                            "name": meal_name,
                        },
                    )

                    PriceOffer.objects.create(
                        run=run,
                        source=source,
                        source_hotel=source_hotel,
                        hotel=hotel,
                        source_room=source_room,
                        room_category=(source_room.room_category),
                        meal_plan=meal_plan,
                        check_in=offer.check_in,
                        nights=offer.nights,
                        adults=offer.adults,
                        children_ages=(offer.children_ages),
                        transfer_included=(offer.transfer_included),
                        taxes_included=(offer.taxes_included),
                        price=offer.price,
                        currency=offer.currency,
                        included_components=(offer.included_components),
                        offer_url=offer.offer_url,
                        raw_data=offer.raw_data,
                    )

                    saved_count += 1

                scenario.hotels.add(*Hotel.objects.filter(id__in=hotel_ids))

            run.status = RunStatus.SUCCESS
            run.finished_at = timezone.now()
            run.save(
                update_fields=(
                    "status",
                    "finished_at",
                )
            )

        except Exception as error:
            run.status = RunStatus.FAILED
            run.finished_at = timezone.now()
            run.error_message = str(error)
            run.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "error_message",
                )
            )

            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS(f"Получено предложений: {len(offers)}"))

        self.stdout.write(self.style.SUCCESS(f"Сохранено в базу: {saved_count}"))

        self.stdout.write(self.style.SUCCESS(f"ID запуска: {run.id}"))
