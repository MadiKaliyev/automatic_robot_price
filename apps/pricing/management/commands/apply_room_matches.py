from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from apps.catalog.models import (
    MatchStatus,
    SourceRoomCategory,
)
from apps.pricing.models import PriceOffer

RESORT_SOURCE = "resort_holiday"
MALDIVIANA_SOURCE = "maldiviana"


ROOM_MATCHES = [
    (
        "Berjaya Beau Vallon Bay Resort 3* (Остров Маэ)",
        "(Honeymoon Offer) Standard Room - Double (2A) / 2ADL",
        "Standard Room",
    ),
    (
        "Berjaya Beau Vallon Bay Resort 3* (Остров Маэ)",
        "(Wedding Anniversary Offer) Standard Room - Double (2A) / 2ADL",
        "Standard Room",
    ),
    (
        "Berjaya Beau Vallon Bay Resort 3* (Остров Маэ)",
        "Standard Room - Double (2A) / 2ADL",
        "Standard Room",
    ),
    (
        "Coral Strand Smart Choice (7S) 4* (Остров Маэ)",
        "(Honeymoon Offer) Standard Signature Garden & Mountains - Double (2A) / 2ADL",
        "Standard Signature Garden & Mountain View",
    ),
    (
        "Coral Strand Smart Choice (7S) 4* (Остров Маэ)",
        "Standard Signature Garden & Mountains - Double (2A) / 2ADL",
        "Standard Signature Garden & Mountain View",
    ),
    (
        "Gardens Hill Resort and Spa Hotel 5* (Остров Маэ)",
        "(Honeymoon Offer) Garden View Deluxe Room - Double (2A) / 2ADL",
        "Garden View Deluxe Room (Honeymoon Deal)",
    ),
    (
        "Gardens Hill Resort and Spa Hotel 5* (Остров Маэ)",
        "Garden View Deluxe Room - Double (2A) / 2ADL",
        "Garden View Deluxe Room (Honeymoon Deal)",
    ),
    (
        "Savoy Seychelles Resort & Spa (7S) 5* (Остров Маэ)",
        "(Honeymoon Offer) - Standard Garden Or Mountain View - Double (2A) / 2ADL",
        "Standard Room Garden View Or Mountain View",
    ),
    (
        "Savoy Seychelles Resort & Spa (7S) 5* (Остров Маэ)",
        "Standard Garden Or Mountain View - Double (2A) / 2ADL",
        "Standard Room Garden View Or Mountain View",
    ),
    (
        "STORY Seychelles (ex The H Resort) 5* (Остров Маэ)",
        "(Honeymoon Offer) Junior Suite with Balcony - Double (2A) / 2ADL",
        "Junior Suite With Balcony",
    ),
    (
        "STORY Seychelles (ex The H Resort) 5* (Остров Маэ)",
        "Junior Suite with Balcony - Double (2A) / 2ADL",
        "Junior Suite With Balcony",
    ),
]


class Command(BaseCommand):
    help = "Подтверждает сопоставление одинаковых категорий номеров двух источников"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить изменения к базе данных",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        prepared_matches = []

        for (
            hotel_name,
            resort_room_name,
            maldiviana_room_name,
        ) in ROOM_MATCHES:
            resort_rooms = list(
                SourceRoomCategory.objects.filter(
                    source_hotel__source__code=(RESORT_SOURCE),
                    source_hotel__hotel__canonical_name=(hotel_name),
                    source_name=resort_room_name,
                ).select_related(
                    "room_category",
                    "source_hotel__hotel",
                )
            )

            if not resort_rooms:
                raise CommandError(
                    "Не найден номер Resort Holiday:\n"
                    f"Отель: {hotel_name}\n"
                    f"Номер: {resort_room_name}"
                )

            maldiviana_rooms = list(
                SourceRoomCategory.objects.filter(
                    source_hotel__source__code=(MALDIVIANA_SOURCE),
                    source_hotel__hotel__canonical_name=(hotel_name),
                    source_name=maldiviana_room_name,
                ).select_related(
                    "room_category",
                    "source_hotel__hotel",
                )
            )

            if not maldiviana_rooms:
                raise CommandError(
                    "Не найден номер Мальдивианы:\n"
                    f"Отель: {hotel_name}\n"
                    f"Номер: {maldiviana_room_name}"
                )

            if len(maldiviana_rooms) > 1:
                raise CommandError(
                    "Найдено несколько одинаковых "
                    "номеров Мальдивианы:\n"
                    f"Отель: {hotel_name}\n"
                    f"Номер: {maldiviana_room_name}"
                )

            maldiviana_room = maldiviana_rooms[0]

            if maldiviana_room.room_category_id is None:
                raise CommandError(
                    "У номера Мальдивианы отсутствует "
                    "каноническая категория:\n"
                    f"{maldiviana_room_name}"
                )

            for resort_room in resort_rooms:
                prepared_matches.append(
                    (
                        resort_room,
                        maldiviana_room,
                    )
                )

            self.stdout.write(self.style.MIGRATE_HEADING(f"Отель: {hotel_name}"))

            self.stdout.write(f"Resort Holiday: {resort_room_name}")

            self.stdout.write(f"Мальдивиана:    {maldiviana_room_name}")

            self.stdout.write(f"Найдено записей Resort Holiday: {len(resort_rooms)}")

            self.stdout.write(
                f"Каноническая категория ID: {maldiviana_room.room_category_id}"
            )

            self.stdout.write("")

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Это предварительный просмотр. База данных не изменена."
                )
            )

            self.stdout.write("Для применения выполни:")

            self.stdout.write("python manage.py apply_room_matches --apply")

            return

        updated_offers = 0
        updated_resort_rooms = 0
        processed_maldiviana_rooms = set()

        with transaction.atomic():
            for (
                resort_room,
                maldiviana_room,
            ) in prepared_matches:
                canonical_room = maldiviana_room.room_category

                update_fields = []

                if resort_room.room_category_id != canonical_room.id:
                    resort_room.room_category = canonical_room
                    update_fields.append("room_category")

                if resort_room.match_status != MatchStatus.CONFIRMED:
                    resort_room.match_status = MatchStatus.CONFIRMED
                    update_fields.append("match_status")

                if update_fields:
                    resort_room.save(update_fields=update_fields)

                updated_resort_rooms += 1

                updated_offers += PriceOffer.objects.filter(
                    source_room=resort_room
                ).update(room_category=canonical_room)

                if maldiviana_room.id not in processed_maldiviana_rooms:
                    processed_maldiviana_rooms.add(maldiviana_room.id)

                    if maldiviana_room.match_status != MatchStatus.CONFIRMED:
                        maldiviana_room.match_status = MatchStatus.CONFIRMED
                        maldiviana_room.save(update_fields=("match_status",))

                    updated_offers += PriceOffer.objects.filter(
                        source_room=maldiviana_room
                    ).update(room_category=canonical_room)

        self.stdout.write(
            self.style.SUCCESS(f"Сопоставлено записей номеров: {updated_resort_rooms}")
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Подтверждено категорий Мальдивианы: {len(processed_maldiviana_rooms)}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(f"Обновлено ценовых записей: {updated_offers}")
        )
