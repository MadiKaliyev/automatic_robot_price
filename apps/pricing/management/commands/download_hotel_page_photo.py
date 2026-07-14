import re
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

from apps.catalog.models import Hotel

IMAGE_SIZE = (720, 480)
IMAGE_QUALITY = 65


def normalize(value: str) -> set[str]:
    value = value.lower()

    value = re.sub(
        r"\([^)]*\)",
        " ",
        value,
    )

    value = re.sub(
        r"\b\d+\s*\*",
        " ",
        value,
    )

    value = re.sub(
        r"[^a-zа-яё0-9]+",
        " ",
        value,
    )

    stop_words = {
        "hotel",
        "resort",
        "spa",
        "seychelles",
        "mahe",
        "остров",
        "маэ",
        "the",
        "and",
    }

    return {word for word in value.split() if word not in stop_words}


def candidate_score(
    candidate: dict,
    hotel_name: str,
) -> float:
    width = int(candidate.get("width") or 0)
    height = int(candidate.get("height") or 0)

    area = width * height

    candidate_words = normalize(
        " ".join(
            [
                candidate.get("alt", ""),
                candidate.get("title", ""),
                candidate.get("url", ""),
            ]
        )
    )

    hotel_words = normalize(hotel_name)

    common_words = candidate_words & hotel_words

    name_bonus = len(common_words) * 10_000_000

    return area + name_bonus


class Command(BaseCommand):
    help = "Берёт главное фото непосредственно со страницы конкретного отеля"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hotel-name",
            required=True,
        )

        parser.add_argument(
            "--page-url",
            required=True,
        )

        parser.add_argument(
            "--apply",
            action="store_true",
            help="Скачать и сохранить фотографию",
        )

        parser.add_argument(
            "--replace",
            action="store_true",
            help="Заменить уже сохранённую фотографию",
        )

    def handle(self, *args, **options):
        hotel_name = options["hotel_name"]
        page_url = options["page_url"]
        apply_changes = options["apply"]
        replace_existing = options["replace"]

        try:
            hotel = Hotel.objects.get(canonical_name=hotel_name)
        except Hotel.DoesNotExist as error:
            raise CommandError(f"Отель не найден: {hotel_name}") from error

        if hotel.image and not replace_existing:
            self.stdout.write(
                self.style.WARNING(
                    "У отеля уже есть фотография. Повторное скачивание отменено."
                )
            )

            self.stdout.write(f"Файл: {hotel.image.name}")
            return

        downloaded_image = None
        selected_url = ""

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)

            context = browser.new_context(
                locale="ru-RU",
                viewport={
                    "width": 1600,
                    "height": 1000,
                },
            )

            page = context.new_page()

            try:
                page.goto(
                    page_url,
                    wait_until="domcontentloaded",
                    timeout=90000,
                )

                page.wait_for_timeout(6000)

                candidates = page.evaluate(
                    """
                    () => {
                        const blocked = [
                            "logo",
                            "icon",
                            "sprite",
                            "avatar",
                            "cookie",
                            "holder.js",
                            "placeholder",
                            "banner",
                            "svg"
                        ];

                        return Array.from(
                            document.images
                        )
                        .map(image => {
                            const url =
                                image.currentSrc
                                || image.src
                                || image.dataset.src
                                || "";

                            return {
                                url: url,
                                alt: image.alt || "",
                                title:
                                    image.title || "",
                                width:
                                    image.naturalWidth
                                    || 0,
                                height:
                                    image.naturalHeight
                                    || 0
                            };
                        })
                        .filter(item => {
                            const lower =
                                item.url.toLowerCase();

                            if (
                                !item.url
                                || item.url.startsWith(
                                    "data:"
                                )
                                || item.width < 600
                                || item.height < 250
                            ) {
                                return false;
                            }

                            return !blocked.some(
                                word =>
                                    lower.includes(word)
                            );
                        });
                    }
                    """
                )

                if not candidates:
                    raise CommandError(
                        "На странице не найдено подходящих крупных фотографий."
                    )

                candidates.sort(
                    key=lambda item: candidate_score(
                        item,
                        hotel_name,
                    ),
                    reverse=True,
                )

                selected = candidates[0]

                self.stdout.write(f"Отель: {hotel.canonical_name}")

                self.stdout.write(f"Найдено крупных фотографий: {len(candidates)}")

                self.stdout.write(
                    f"Выбрано фото: {selected['width']}x{selected['height']}"
                )

                self.stdout.write(f"ALT: {selected['alt']}")

                self.stdout.write(f"URL: {selected['url']}")

                if not apply_changes:
                    self.stdout.write(
                        self.style.WARNING(
                            "\nПредварительный просмотр. Фото пока не сохранено."
                        )
                    )

                    self.stdout.write("Для сохранения добавь --apply")
                    return

                response = context.request.get(
                    selected["url"],
                    headers={
                        "Referer": page_url,
                    },
                    timeout=90000,
                )

                if not response.ok:
                    raise CommandError(
                        f"Не удалось скачать фото. HTTP {response.status}"
                    )

                source_image = Image.open(BytesIO(response.body()))

                source_image = ImageOps.exif_transpose(source_image).convert("RGB")

                compressed = ImageOps.fit(
                    source_image,
                    IMAGE_SIZE,
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )

                output = BytesIO()

                compressed.save(
                    output,
                    format="WEBP",
                    quality=IMAGE_QUALITY,
                    method=6,
                    optimize=True,
                )

                downloaded_image = output.getvalue()
                selected_url = selected["url"]

            finally:
                context.close()
                browser.close()

        if not downloaded_image:
            raise CommandError("Фотография не была загружена.")

        filename = f"hotel_{hotel.id}_detail.webp"

        hotel.image.save(
            filename,
            ContentFile(downloaded_image),
            save=False,
        )
        hotel.image_source_url = selected_url
        hotel.image_page_url = page_url
        hotel.save(
            update_fields=(
                "image",
                "image_source_url",
                "image_page_url",
            )
        )

        self.stdout.write(self.style.SUCCESS("\nФотография сохранена."))
        self.stdout.write(f"Файл: {hotel.image.name}")
        self.stdout.write(f"Размер после сжатия: {len(downloaded_image)} байт")
