from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from apps.catalog.models import (
    Hotel,
    MatchStatus,
    SourceHotel,
)

MATCHES = [
    (
        73,
        "Berjaya Beau Vallon Bay Resort 3* (Остров Маэ)",
    ),
    (
        93,
        "Coral Strand Smart Choice (7S) 4* (Остров Маэ)",
    ),
    (
        105,
        "Gardens Hill Resort and Spa Hotel 5* (Остров Маэ)",
    ),
    (
        132,
        "STORY Seychelles (ex The H Resort) 5* (Остров Маэ)",
    ),
    (
        130,
        "Savoy Seychelles Resort & Spa (7S) 5* (Остров Маэ)",
    ),
]


class Command(BaseCommand):
    help = "Привязывает отели Maldives Bonus и их реальные фотографии"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить изменения",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        prepared = []

        for source_hotel_id, target_name in MATCHES:
            try:
                source_hotel = SourceHotel.objects.select_related(
                    "hotel", "source"
                ).get(
                    id=source_hotel_id,
                    source__code="maldives_bonus",
                )
            except SourceHotel.DoesNotExist as error:
                raise CommandError(
                    f"Не найден SourceHotel ID {source_hotel_id}"
                ) from error

            try:
                target_hotel = Hotel.objects.get(
                    country="Сейшелы",
                    canonical_name=target_name,
                )
            except Hotel.DoesNotExist as error:
                raise CommandError(f"Не найден отель: {target_name}") from error

            donor_hotel = source_hotel.hotel
            has_photo = bool(donor_hotel and donor_hotel.image)

            prepared.append(
                (
                    source_hotel,
                    donor_hotel,
                    target_hotel,
                )
            )

            self.stdout.write(f"\nMaldives Bonus: {source_hotel.source_name}")
            self.stdout.write(f"Единый отель: {target_name}")
            self.stdout.write(f"Фото найдено: {'да' if has_photo else 'нет'}")

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING("\nПредварительный просмотр. База не изменена.")
            )
            self.stdout.write("Для применения выполни:")
            self.stdout.write("python manage.py apply_bonus_photo_matches --apply")
            return

        linked = 0
        assigned_photos = 0
        missing_photos = 0

        with transaction.atomic():
            for (
                source_hotel,
                donor_hotel,
                target_hotel,
            ) in prepared:
                target_updates = []

                if not target_hotel.image and donor_hotel and donor_hotel.image:
                    # Используем уже скачанный файл.
                    # Новая копия файла не создаётся.
                    target_hotel.image = donor_hotel.image.name
                    target_updates.append("image")
                    assigned_photos += 1

                if not target_hotel.image_source_url and source_hotel.image_url:
                    target_hotel.image_source_url = source_hotel.image_url
                    target_updates.append("image_source_url")

                if not target_hotel.image_page_url and source_hotel.detail_url:
                    target_hotel.image_page_url = source_hotel.detail_url
                    target_updates.append("image_page_url")

                if target_updates:
                    target_hotel.save(update_fields=tuple(target_updates))

                if not target_hotel.image:
                    missing_photos += 1

                source_hotel.hotel = target_hotel
                source_hotel.match_status = MatchStatus.CONFIRMED
                source_hotel.save(
                    update_fields=(
                        "hotel",
                        "match_status",
                    )
                )

                linked += 1

        self.stdout.write(self.style.SUCCESS(f"\nСопоставлено отелей: {linked}"))
        self.stdout.write(
            self.style.SUCCESS(f"Привязано готовых фотографий: {assigned_photos}")
        )
        self.stdout.write(
            self.style.WARNING(f"Отелей без фотографии: {missing_photos}")
        )
