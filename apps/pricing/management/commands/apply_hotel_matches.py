from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from apps.catalog.models import (
    MatchStatus,
    SourceHotel,
)
from apps.pricing.models import PriceOffer

RESORT_SOURCE = "resort_holiday"
MALDIVIANA_SOURCE = "maldiviana"


HOTEL_MATCHES = [
    (
        "Berjaya Beau Vallon Bay Resort & Casino 3* (Бо-Валлон)",
        "Berjaya Beau Vallon Bay Resort 3* (Остров Маэ)",
    ),
    (
        "Coral Strand Smart Choice Hotel 4* (Бо-Валлон)",
        "Coral Strand Smart Choice (7S) 4* (Остров Маэ)",
    ),
    (
        "Gardens Hill Resort & Spa Hotel 5* (Маэ)",
        "Gardens Hill Resort and Spa Hotel 5* (Остров Маэ)",
    ),
    (
        "Romance Bungalows Гостевой Дом (Маэ)",
        "Romance Bungalows 2* (Остров Маэ)",
    ),
    (
        "Savoy Resort Seychelles",
        "Savoy Seychelles Resort & Spa (7S) 5* (Остров Маэ)",
    ),
    (
        "Savoy Seychelles Resort & Spa 5* (Бо-Валлон)",
        "Savoy Seychelles Resort & Spa (7S) 5* (Остров Маэ)",
    ),
    (
        "Story (Seychelles) 5* (Бо-Валлон)",
        "STORY Seychelles (ex The H Resort) 5* (Остров Маэ)",
    ),
]


class Command(BaseCommand):
    help = "Подтверждает сопоставление одинаковых отелей Resort Holiday и Мальдивианы"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить изменения к базе данных",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        prepared_matches = []

        for resort_name, maldiviana_name in HOTEL_MATCHES:
            resort_hotel = (
                SourceHotel.objects.filter(
                    source__code=RESORT_SOURCE,
                    source_name=resort_name,
                    active=True,
                )
                .select_related("hotel")
                .first()
            )

            if resort_hotel is None:
                raise CommandError(f"Не найден отель Resort Holiday: {resort_name}")

            maldiviana_hotel = (
                SourceHotel.objects.filter(
                    source__code=MALDIVIANA_SOURCE,
                    source_name=maldiviana_name,
                    active=True,
                )
                .select_related("hotel")
                .first()
            )

            if maldiviana_hotel is None:
                raise CommandError(f"Не найден отель Мальдивианы: {maldiviana_name}")

            if maldiviana_hotel.hotel_id is None:
                raise CommandError(
                    "У отеля Мальдивианы отсутствует "
                    f"канонический Hotel: {maldiviana_name}"
                )

            prepared_matches.append(
                (
                    resort_hotel,
                    maldiviana_hotel,
                )
            )

            self.stdout.write(f"Resort Holiday: {resort_name}")

            self.stdout.write(f"Мальдивиана:    {maldiviana_name}")

            self.stdout.write(f"Канонический Hotel ID: {maldiviana_hotel.hotel_id}")

            self.stdout.write("")

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Это предварительный просмотр. База данных не изменена."
                )
            )

            self.stdout.write("Для применения выполни:")

            self.stdout.write("python manage.py apply_hotel_matches --apply")

            return

        updated_offers = 0

        with transaction.atomic():
            for (
                resort_hotel,
                maldiviana_hotel,
            ) in prepared_matches:
                canonical_hotel = maldiviana_hotel.hotel

                resort_hotel.hotel = canonical_hotel
                resort_hotel.match_status = MatchStatus.CONFIRMED
                resort_hotel.save(
                    update_fields=(
                        "hotel",
                        "match_status",
                    )
                )

                if maldiviana_hotel.match_status != MatchStatus.CONFIRMED:
                    maldiviana_hotel.match_status = MatchStatus.CONFIRMED
                    maldiviana_hotel.save(update_fields=("match_status",))

                updated_offers += PriceOffer.objects.filter(
                    source_hotel=resort_hotel
                ).update(hotel=canonical_hotel)

                updated_offers += PriceOffer.objects.filter(
                    source_hotel=maldiviana_hotel
                ).update(hotel=canonical_hotel)

        self.stdout.write(
            self.style.SUCCESS(f"Сопоставлено связей: {len(prepared_matches)}")
        )

        self.stdout.write(
            self.style.SUCCESS(f"Обновлено ценовых записей: {updated_offers}")
        )
