from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import MatchStatus, SourceHotel
from apps.pricing.hotel_photos import (
    download_missing_hotel_photos,
)
from apps.pricing.management.command_utils import (
    parse_children_ages,
)
from apps.pricing.models import (
    CollectionRun,
    ComparisonGroup,
    ComparisonItem,
    PriceOffer,
    RunStatus,
    SearchScenario,
)
from apps.pricing.services import price_composition_key

SOURCE_CODES = (
    "resort_holiday",
    "maldiviana",
)


def money(value: Decimal) -> Decimal:
    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def percentage(value: Decimal) -> Decimal:
    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def get_rate_type(offer: PriceOffer) -> str:
    values = []

    if offer.source_room_id:
        values.append(offer.source_room.source_name)

    if isinstance(offer.raw_data, dict):
        values.extend(
            [
                str(
                    offer.raw_data.get(
                        "room_raw",
                        "",
                    )
                ),
                str(
                    offer.raw_data.get(
                        "offer_code",
                        "",
                    )
                ),
            ]
        )

    text = " ".join(values).lower()

    if "wedding anniversary" in text or "anniversary" in text:
        return "anniversary"

    if "honeymoon" in text:
        return "honeymoon"

    return "standard"


def get_color(
    is_best: bool,
    percent_difference: Decimal,
) -> str:
    if is_best:
        return "green"

    if percent_difference <= Decimal("5"):
        return "yellow"

    if percent_difference <= Decimal("10"):
        return "orange"

    return "red"


class Command(BaseCommand):
    help = "Строит сравнение актуальных цен Resort Holiday и Мальдивианы"

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
            "--currency",
            default="EUR",
            help="Валюта сравнения",
        )

        parser.add_argument(
            "--apply",
            action="store_true",
            help="Сохранить сравнение в базу",
        )

        parser.add_argument(
            "--children-ages",
            default="",
            help="Возраст детей через запятую, например: 4,9",
        )

        parser.add_argument(
            "--hotel-ids",
            default="",
            help="ID выбранных отелей через запятую",
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
        currency = options["currency"].upper()
        apply_changes = options["apply"]

        try:
            hotel_ids = tuple(
                int(value.strip())
                for value in options["hotel_ids"].split(",")
                if value.strip()
            )
        except ValueError as error:
            raise CommandError(
                "ID отелей нужно указать числами через запятую."
            ) from error

        if nights < 1:
            raise CommandError("Количество ночей должно быть больше нуля")

        if adults < 1:
            raise CommandError("Количество взрослых должно быть больше нуля")

        base_filters = {
            "source__code__in": SOURCE_CODES,
            "run__status": RunStatus.SUCCESS,
            "check_in": check_in,
            "nights": nights,
            "adults": adults,
            "children_ages": list(children_ages),
            "currency": currency,
            "transfer_included": False,
            "source_hotel__match_status": (MatchStatus.CONFIRMED),
            "source_room__match_status": (MatchStatus.CONFIRMED),
            "hotel_id__isnull": False,
            "room_category_id__isnull": False,
            "meal_plan_id__isnull": False,
        }

        if hotel_ids:
            base_filters["hotel_id__in"] = hotel_ids

        latest_run_ids = {}

        for source_code in SOURCE_CODES:
            latest_offer = (
                PriceOffer.objects.filter(
                    **base_filters,
                    source__code=source_code,
                )
                .select_related("run")
                .order_by(
                    "-run__started_at",
                    "-captured_at",
                    "-id",
                )
                .first()
            )

            if latest_offer is None:
                self.stdout.write(
                    self.style.WARNING(f"Нет подходящих цен: {source_code}")
                )
                continue

            latest_run_ids[source_code] = latest_offer.run_id

            self.stdout.write(
                f"{source_code}: используется запуск ID {latest_offer.run_id}"
            )

        if len(latest_run_ids) < 2:
            raise CommandError(
                "Для сравнения нужны актуальные цены минимум из двух источников."
            )

        offers = list(
            PriceOffer.objects.filter(
                **base_filters,
                run_id__in=latest_run_ids.values(),
            )
            .select_related(
                "source",
                "source_hotel",
                "source_room",
                "hotel",
                "room_category",
                "meal_plan",
                "run",
            )
            .order_by(
                "hotel__canonical_name",
                "room_category__canonical_name",
                "meal_plan__code",
                "source__code",
                "price",
            )
        )

        grouped_offers = defaultdict(list)

        for offer in offers:
            children_key = tuple(offer.children_ages or [])

            rate_type = get_rate_type(offer)

            group_key = (
                offer.hotel_id,
                offer.room_category_id,
                offer.meal_plan_id,
                offer.check_in,
                offer.nights,
                offer.adults,
                children_key,
                offer.transfer_included,
                offer.taxes_included,
                offer.currency,
                rate_type,
                price_composition_key(offer),
            )

            grouped_offers[group_key].append(offer)

        comparison_candidates = []

        for group_key, group_offers in grouped_offers.items():
            best_by_source = {}

            for offer in group_offers:
                source_code = offer.source.code

                current = best_by_source.get(source_code)

                if current is None or offer.price < current.price:
                    best_by_source[source_code] = offer

            if len(best_by_source) < 2:
                continue

            selected_offers = sorted(
                best_by_source.values(),
                key=lambda item: (
                    item.price,
                    item.source.code,
                ),
            )

            comparison_candidates.append(
                (
                    group_key,
                    selected_offers,
                )
            )

        comparison_candidates.sort(
            key=lambda item: (
                item[1][0].hotel.canonical_name,
                item[1][0].room_category.canonical_name,
                item[1][0].meal_plan.code,
                item[0][-2],
            )
        )

        self.stdout.write("")
        self.stdout.write(f"Найдено групп для сравнения: {len(comparison_candidates)}")
        self.stdout.write("")

        for number, (
            group_key,
            selected_offers,
        ) in enumerate(
            comparison_candidates,
            start=1,
        ):
            first_offer = selected_offers[0]
            rate_type = group_key[-2]

            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"{number}. {first_offer.hotel.canonical_name}"
                )
            )

            self.stdout.write(f"Номер: {first_offer.room_category.canonical_name}")

            self.stdout.write(f"Питание: {first_offer.meal_plan.code}")

            self.stdout.write(f"Тариф: {rate_type}")

            self.stdout.write(
                f"Дата: {first_offer.check_in:%d.%m.%Y}, "
                f"ночей: {first_offer.nights}, "
                f"взрослых: {first_offer.adults}"
            )

            for offer in selected_offers:
                self.stdout.write(
                    f"  {offer.source.name}: {offer.price} {offer.currency}"
                )

            self.stdout.write("")

        if not comparison_candidates:
            self.stdout.write(
                self.style.WARNING(
                    "Полностью одинаковых предложений "
                    "из двух источников пока не найдено."
                )
            )
            return

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Это предварительный просмотр. База данных не изменена."
                )
            )

            self.stdout.write("Для сохранения выполни:")

            self.stdout.write("python manage.py build_comparisons --apply")
            return

        scenario_name = (
            f"Сравнение: Сейшелы, "
            f"{check_in:%d.%m.%Y}, "
            f"{nights} ночей, "
            f"{adults} взрослых, "
            f"{currency}"
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
                "first_available_only": False,
                "preferred_currency": currency,
                "active": True,
            },
        )

        comparison_run = CollectionRun.objects.create(
            scenario=scenario,
            status=RunStatus.RUNNING,
            trigger=options["trigger"],
        )

        groups_created = 0
        items_created = 0
        selected_hotel_ids = set()
        photos_downloaded = 0
        photos_skipped = 0
        photo_failures = []

        try:
            with transaction.atomic():
                for (
                    _group_key,
                    selected_offers,
                ) in comparison_candidates:
                    best_offer = min(
                        selected_offers,
                        key=lambda item: item.price,
                    )

                    best_price = money(best_offer.price)
                    selected_hotel_ids.add(best_offer.hotel_id)

                    group = ComparisonGroup.objects.create(
                        run=comparison_run,
                        hotel=best_offer.hotel,
                        room_category=(best_offer.room_category),
                        meal_plan=(best_offer.meal_plan),
                        check_in=(best_offer.check_in),
                        nights=best_offer.nights,
                        adults=best_offer.adults,
                        children_ages=(best_offer.children_ages or []),
                        transfer_included=(best_offer.transfer_included),
                        taxes_included=(best_offer.taxes_included),
                        currency=(best_offer.currency),
                        best_offer=best_offer,
                        best_price=best_price,
                    )

                    groups_created += 1

                    for offer in selected_offers:
                        absolute_difference = money(offer.price - best_price)

                        if best_price == 0:
                            percent_difference = Decimal("0.00")
                        else:
                            percent_difference = percentage(
                                (absolute_difference / best_price) * Decimal("100")
                            )

                        is_best = offer.id == best_offer.id

                        color_status = get_color(
                            is_best,
                            percent_difference,
                        )

                        ComparisonItem.objects.create(
                            group=group,
                            offer=offer,
                            absolute_difference=(absolute_difference),
                            percent_difference=(percent_difference),
                            color_status=color_status,
                            is_best=is_best,
                        )

                        items_created += 1

            comparison_run.status = RunStatus.SUCCESS
            comparison_run.finished_at = timezone.now()
            comparison_run.error_message = ""
            comparison_run.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "error_message",
                )
            )

        except Exception as error:
            comparison_run.status = RunStatus.FAILED
            comparison_run.finished_at = timezone.now()
            comparison_run.error_message = str(error)
            comparison_run.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "error_message",
                )
            )

            raise CommandError(str(error)) from error

        photo_jobs = dict(
            SourceHotel.objects.filter(
                hotel_id__in=selected_hotel_ids,
                source__code="maldiviana",
            )
            .exclude(detail_url="")
            .values_list("hotel_id", "detail_url")
        )

        try:
            (
                photos_downloaded,
                photos_skipped,
                photo_failures,
            ) = download_missing_hotel_photos(photo_jobs)
        except Exception as error:
            photo_failures = [("список выбранных отелей", str(error))]

        for hotel_name, photo_error in photo_failures:
            self.stderr.write(
                self.style.WARNING(
                    f"Не удалось загрузить фото для «{hotel_name}»: {photo_error}"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Создано групп: {groups_created}"))

        self.stdout.write(self.style.SUCCESS(f"Создано элементов: {items_created}"))

        self.stdout.write(
            self.style.SUCCESS(
                "Загружено новых фото: "
                f"{photos_downloaded}; "
                "пропущено существующих: "
                f"{photos_skipped}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(f"ID запуска сравнения: {comparison_run.id}")
        )
