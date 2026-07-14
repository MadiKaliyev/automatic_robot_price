from django.core.management import call_command

from apps.catalog.models import Hotel


def download_missing_hotel_photos(
    photo_jobs: dict[int, str],
) -> tuple[int, int, list[tuple[str, str]]]:
    downloaded = 0
    skipped = 0
    failures = []

    for hotel_id, page_url in photo_jobs.items():
        hotel = Hotel.objects.get(id=hotel_id)

        if hotel.image:
            skipped += 1
            continue

        try:
            call_command(
                "download_hotel_page_photo",
                hotel_name=hotel.canonical_name,
                page_url=page_url,
                apply=True,
            )
        except Exception as error:
            failures.append(
                (
                    hotel.canonical_name,
                    str(error),
                )
            )
            continue

        hotel.refresh_from_db(fields=("image",))

        if hotel.image:
            downloaded += 1
        else:
            failures.append(
                (
                    hotel.canonical_name,
                    "Фотография не сохранилась.",
                )
            )

    return downloaded, skipped, failures
