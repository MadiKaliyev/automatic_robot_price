import re
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand

from apps.catalog.models import SourceHotel

SOURCE_ONE = "resort_holiday"
SOURCE_TWO = "maldiviana"


STOP_WORDS = {
    "hotel",
    "resort",
    "spa",
    "seychelles",
    "seychelle",
    "the",
    "and",
    "by",
    "ex",
    "l",
    "7s",
}


def normalize_name(value: str) -> str:
    value = value.lower()

    value = re.sub(
        r"\([^)]*\)",
        " ",
        value,
    )

    value = re.sub(
        r"\b[1-5]\s*\*\s*(deluxe|luxe|superior)?",
        " ",
        value,
    )

    value = value.replace("&", " and ")

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
    first = normalize_name(first_name)
    second = normalize_name(second_name)

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

    return max(
        text_score,
        word_score,
    )


class Command(BaseCommand):
    help = "Ищет вероятные совпадения отелей Resort Holiday и Мальдивианы"

    def add_arguments(self, parser):
        parser.add_argument(
            "--minimum-score",
            type=float,
            default=0.60,
            help="Минимальная похожесть от 0 до 1",
        )

    def handle(self, *args, **options):
        minimum_score = options["minimum_score"]

        resort_hotels = list(
            SourceHotel.objects.filter(
                source__code=SOURCE_ONE,
                active=True,
            ).order_by("source_name")
        )

        maldiviana_hotels = list(
            SourceHotel.objects.filter(
                source__code=SOURCE_TWO,
                active=True,
            ).order_by("source_name")
        )

        self.stdout.write(f"Resort Holiday: {len(resort_hotels)} отелей")

        self.stdout.write(f"Мальдивиана: {len(maldiviana_hotels)} отелей")

        self.stdout.write("")

        matches_count = 0

        for resort_hotel in resort_hotels:
            candidates = []

            for maldiviana_hotel in maldiviana_hotels:
                score = calculate_score(
                    resort_hotel.source_name,
                    maldiviana_hotel.source_name,
                )

                if score >= minimum_score:
                    candidates.append(
                        (
                            score,
                            maldiviana_hotel,
                        )
                    )

            candidates.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            if not candidates:
                continue

            best_score, best_hotel = candidates[0]
            matches_count += 1

            self.stdout.write(self.style.SUCCESS(f"[{best_score:.0%}]"))

            self.stdout.write(f"  Resort Holiday: {resort_hotel.source_name}")

            self.stdout.write(f"  Мальдивиана:    {best_hotel.source_name}")

            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(f"Найдено кандидатов: {matches_count}"))
