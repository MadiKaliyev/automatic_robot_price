import json
from dataclasses import asdict
from datetime import date
from io import BytesIO
from pathlib import Path

import httpx
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps

from apps.catalog.models import (
    Hotel,
    MatchStatus,
    Source,
    SourceHotel,
)
from apps.integrations.adapters.maldives_bonus import (
    MaldivesBonusAdapter,
)
from apps.integrations.base import SearchRequest
from apps.pricing.management.command_utils import (
    parse_children_ages,
)
from apps.pricing.models import (
    CollectionRun,
    RunStatus,
    SearchScenario,
)

IMAGE_SIZE = (720, 480)
IMAGE_QUALITY = 65


def save_compressed_image(
    client: httpx.Client,
    hotel: Hotel,
    source_hotel: SourceHotel,
    image_url: str,
    page_url: str,
    refresh_images: bool,
) -> bool:
    source_hotel.detail_url = page_url
    source_hotel.image_url = image_url
    source_hotel.save(
        update_fields=(
            "detail_url",
            "image_url",
        )
    )

    hotel.image_source_url = image_url
    hotel.image_page_url = page_url

    if not image_url:
        hotel.save(
            update_fields=(
                "image_source_url",
                "image_page_url",
            )
        )
        return False

    if hotel.image and not refresh_images:
        hotel.save(
            update_fields=(
                "image_source_url",
                "image_page_url",
            )
        )
        return False

    response = client.get(
        image_url,
        headers={
            "Referer": page_url,
        },
    )
    response.raise_for_status()

    source_image = Image.open(BytesIO(response.content))

    source_image = ImageOps.exif_transpose(source_image).convert("RGB")

    compressed_image = ImageOps.fit(
        source_image,
        IMAGE_SIZE,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )

    output = BytesIO()

    compressed_image.save(
        output,
        format="WEBP",
        quality=IMAGE_QUALITY,
        method=6,
        optimize=True,
    )

    if refresh_images and hotel.image:
        hotel.image.delete(save=False)

    file_code = source_hotel.source_code or str(source_hotel.id)

    filename = f"maldives_bonus_{file_code}.webp"

    hotel.image.save(
        filename,
        ContentFile(output.getvalue()),
        save=False,
    )

    hotel.save(
        update_fields=(
            "image",
            "image_source_url",
            "image_page_url",
        )
    )

    return True


class Command(BaseCommand):
    help = "Собирает каталог Maldives Bonus, сохраняет отели и сжатые фотографии"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-in",
            default="2026-09-10",
        )

        parser.add_argument(
            "--nights",
            type=int,
            default=7,
        )

        parser.add_argument(
            "--adults",
            type=int,
            default=2,
        )

        parser.add_argument(
            "--output",
            help=("Необязательный путь для полного результата в JSON"),
        )

        parser.add_argument(
            "--refresh-images",
            action="store_true",
            help=("Повторно скачать и заменить существующие фотографии"),
        )

        parser.add_argument(
            "--children-ages",
            default="",
            help="Возраст детей через запятую, например: 4,9",
        )

        parser.add_argument(
            "--trigger",
            choices=("manual", "scheduled"),
            default="manual",
            help="Способ запуска",
        )

    def handle(self, *args, **options):
        children_ages = parse_children_ages(options["children_ages"])

        try:
            check_in = date.fromisoformat(options["check_in"])
        except ValueError as error:
            raise CommandError("Дата должна быть в формате ГГГГ-ММ-ДД") from error

        if options["nights"] < 1 or options["adults"] < 1:
            raise CommandError("Количество ночей и взрослых должно быть больше нуля")

        children_text = ""

        if children_ages:
            children_text = ", дети " + ",".join(map(str, children_ages))

        scenario, _ = SearchScenario.objects.update_or_create(
            name=(
                "Maldives Bonus: Сейшелы, "
                f"{check_in:%d.%m.%Y}, "
                f"{options['nights']} ночей, "
                f"{options['adults']} взрослых"
                f"{children_text}"
            ),
            defaults={
                "destination": "Сейшелы",
                "check_in": check_in,
                "nights": options["nights"],
                "adults": options["adults"],
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
            nights=options["nights"],
            adults=options["adults"],
            children_ages=children_ages,
        )

        self.stdout.write("Запускаем сбор каталога Maldives Bonus...")

        downloaded_images = 0
        skipped_images = 0
        failed_images = 0

        try:
            adapter = MaldivesBonusAdapter()
            offers = adapter.fetch(request)

            if not offers:
                raise RuntimeError("Maldives Bonus не вернул карточки отелей")

            source, _ = Source.objects.update_or_create(
                code=adapter.source_code,
                defaults={
                    "name": adapter.source_name,
                    "base_url": adapter.base_url,
                    "enabled": True,
                },
            )

            hotel_ids = set()
            image_jobs = []

            with transaction.atomic():
                for offer in offers:
                    country = offer.raw_data.get("country") or "Сейшелы"

                    resort = (offer.raw_data.get("resort", ""))[:150]

                    hotel, created = Hotel.objects.get_or_create(
                        country=country,
                        canonical_name=(offer.source_hotel_name[:255]),
                        defaults={
                            "destination": resort,
                            "active": True,
                        },
                    )

                    if not created and not hotel.destination and resort:
                        hotel.destination = resort
                        hotel.save(update_fields=("destination",))

                    source_hotel, source_created = SourceHotel.objects.get_or_create(
                        source=source,
                        source_name=(offer.source_hotel_name[:255]),
                        defaults={
                            "source_code": (offer.source_hotel_code),
                            "hotel": hotel,
                            "match_status": (MatchStatus.REVIEW),
                            "active": True,
                        },
                    )

                    source_updates = []

                    if source_hotel.source_code != offer.source_hotel_code:
                        source_hotel.source_code = offer.source_hotel_code
                        source_updates.append("source_code")

                    if source_hotel.hotel_id != hotel.id:
                        source_hotel.hotel = hotel
                        source_updates.append("hotel")

                    if not source_hotel.active:
                        source_hotel.active = True
                        source_updates.append("active")

                    images = offer.raw_data.get("images") or []

                    image_url = images[0] if images else ""

                    page_url = offer.offer_url or ""

                    if source_hotel.detail_url != page_url:
                        source_hotel.detail_url = page_url
                        source_updates.append("detail_url")

                    if source_hotel.image_url != image_url:
                        source_hotel.image_url = image_url
                        source_updates.append("image_url")

                    if source_updates:
                        source_hotel.save(update_fields=tuple(source_updates))

                    hotel_ids.add(hotel.id)

                    image_jobs.append(
                        (
                            hotel,
                            source_hotel,
                            image_url,
                            page_url,
                        )
                    )

                scenario.hotels.add(*Hotel.objects.filter(id__in=hotel_ids))

            image_client = httpx.Client(
                timeout=45,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "Chrome/142 Safari/537.36"
                    ),
                },
            )

            try:
                total_jobs = len(image_jobs)

                for number, (
                    hotel,
                    source_hotel,
                    image_url,
                    page_url,
                ) in enumerate(
                    image_jobs,
                    start=1,
                ):
                    try:
                        saved = save_compressed_image(
                            client=image_client,
                            hotel=hotel,
                            source_hotel=source_hotel,
                            image_url=image_url,
                            page_url=page_url,
                            refresh_images=options["refresh_images"],
                        )

                        if saved:
                            downloaded_images += 1
                        else:
                            skipped_images += 1

                        self.stdout.write(
                            f"[{number}/{total_jobs}] {hotel.canonical_name}"
                        )

                    except Exception as image_error:
                        failed_images += 1

                        self.stdout.write(
                            self.style.WARNING(
                                f"[{number}/{total_jobs}] "
                                "Не удалось скачать фото: "
                                f"{hotel.canonical_name}. "
                                f"{image_error}"
                            )
                        )

            finally:
                image_client.close()

            if options.get("output"):
                output = Path(options["output"])

                output.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                output.write_text(
                    json.dumps(
                        [asdict(offer) for offer in offers],
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )

            run.status = RunStatus.SUCCESS
            run.finished_at = timezone.now()
            run.error_message = ""
            run.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "error_message",
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

        self.stdout.write(self.style.WARNING(adapter.status_message))

        self.stdout.write(self.style.SUCCESS(f"Получено отелей: {len(offers)}"))

        self.stdout.write(
            self.style.SUCCESS(f"Скачано новых фотографий: {downloaded_images}")
        )

        self.stdout.write(f"Уже существовали или отсутствовали: {skipped_images}")

        self.stdout.write(f"Ошибок фотографий: {failed_images}")

        self.stdout.write(self.style.SUCCESS("Сохранено цен: 0"))

        self.stdout.write(self.style.SUCCESS(f"ID запуска: {run.id}"))
