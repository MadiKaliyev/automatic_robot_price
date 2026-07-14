import re
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand

from apps.catalog.models import (
    Hotel,
    SourceHotel,
    SourceRoomCategory,
)

RESORT_SOURCE = "resort_holiday"
MALDIVIANA_SOURCE = "maldiviana"


STOP_WORDS = {
    "room",
    "rooms",
    "номер",
    "accommodation",
    "with",
    "and",
    "the",
    "for",
}


def normalize_room_name(value: str) -> str:
    value = value.lower()

    value = value.replace("&", " and ")

    # Убираем количество гостей.
    value = re.sub(
        r"\b\d+\s*(adl|adult|adults|pax)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    # Убираем текст в скобках.
    value = re.sub(
        r"\([^)]*\)",
        " ",
        value,
    )

    value = re.sub(
        r"[^a-zа-яё0-9]+",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    words = [word for word in value.split() if word not in STOP_WORDS]

    return " ".join(words).strip()


def calculate_score(
    first_name: str,
    second_name: str,
) -> float:
    first = normalize_room_name(first_name)
    second = normalize_room_name(second_name)

    if not first or not second:
        return 0.0

    if first == second:
        return 1.0

    first_words = set(first.split())
    second_words = set(second.split())

    common_words = first_words & second_words
    all_words = first_words | second_words

    word_score = len(common_words) / len(all_words) if all_words else 0.0

    text_score = SequenceMatcher(
        None,
        first,
        second,
    ).ratio()

    containment_score = 0.0

    if first in second or second in first:
        containment_score = min(len(first), len(second)) / max(len(first), len(second))

    return max(
        text_score,
        word_score,
        containment_score,
    )


class Command(BaseCommand):
    help = "Ищет вероятные совпадения категорий номеров Resort Holiday и Мальдивианы"

    def add_arguments(self, parser):
        parser.add_argument(
            "--minimum-score",
            type=float,
            default=0.65,
            help="Минимальная похожесть от 0 до 1",
        )

    def handle(self, *args, **options):
        minimum_score = options["minimum_score"]

        resort_hotel_ids = set(
            SourceHotel.objects.filter(
                source__code=RESORT_SOURCE,
                active=True,
                hotel_id__isnull=False,
            ).values_list(
                "hotel_id",
                flat=True,
            )
        )

        maldiviana_hotel_ids = set(
            SourceHotel.objects.filter(
                source__code=MALDIVIANA_SOURCE,
                active=True,
                hotel_id__isnull=False,
            ).values_list(
                "hotel_id",
                flat=True,
            )
        )

        common_hotel_ids = sorted(resort_hotel_ids & maldiviana_hotel_ids)

        self.stdout.write(f"Общих отелей: {len(common_hotel_ids)}")

        self.stdout.write("")

        matches_count = 0

        for hotel_id in common_hotel_ids:
            hotel = Hotel.objects.get(id=hotel_id)

            resort_rooms = list(
                SourceRoomCategory.objects.filter(
                    source_hotel__source__code=(RESORT_SOURCE),
                    source_hotel__hotel_id=hotel_id,
                )
                .select_related("source_hotel")
                .order_by("source_name")
            )

            maldiviana_rooms = list(
                SourceRoomCategory.objects.filter(
                    source_hotel__source__code=(MALDIVIANA_SOURCE),
                    source_hotel__hotel_id=hotel_id,
                )
                .select_related("source_hotel")
                .order_by("source_name")
            )

            if not resort_rooms or not maldiviana_rooms:
                continue

            self.stdout.write(
                self.style.MIGRATE_HEADING(f"Отель: {hotel.canonical_name}")
            )

            self.stdout.write(f"Resort Holiday номеров: {len(resort_rooms)}")

            self.stdout.write(f"Мальдивиана номеров: {len(maldiviana_rooms)}")

            self.stdout.write("")

            for resort_room in resort_rooms:
                candidates = []

                for maldiviana_room in maldiviana_rooms:
                    score = calculate_score(
                        resort_room.source_name,
                        maldiviana_room.source_name,
                    )

                    if score >= minimum_score:
                        candidates.append(
                            (
                                score,
                                maldiviana_room,
                            )
                        )

                candidates.sort(
                    key=lambda item: item[0],
                    reverse=True,
                )

                if not candidates:
                    continue

                best_score, best_room = candidates[0]

                matches_count += 1

                self.stdout.write(self.style.SUCCESS(f"[{best_score:.0%}]"))

                self.stdout.write(f"  Resort Holiday: {resort_room.source_name}")

                self.stdout.write(f"  Мальдивиана:    {best_room.source_name}")

                self.stdout.write(
                    f"  Нормализация 1: {normalize_room_name(resort_room.source_name)}"
                )

                self.stdout.write(
                    f"  Нормализация 2: {normalize_room_name(best_room.source_name)}"
                )

                self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(f"Найдено кандидатов номеров: {matches_count}")
        )

        self.stdout.write(self.style.WARNING("База данных не изменена."))
