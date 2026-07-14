from unittest.mock import patch

from django.test import TestCase

from apps.catalog.models import Hotel
from apps.pricing.hotel_photos import (
    download_missing_hotel_photos,
)


class DownloadMissingHotelPhotosTests(TestCase):
    @patch("apps.pricing.hotel_photos.call_command")
    def test_downloads_only_for_hotels_without_image(
        self,
        mocked_call_command,
    ):
        existing = Hotel.objects.create(
            canonical_name="Existing Hotel",
            image="hotels/existing.webp",
        )
        missing = Hotel.objects.create(
            canonical_name="Missing Hotel",
        )

        def save_image(*args, **kwargs):
            hotel = Hotel.objects.get(canonical_name=kwargs["hotel_name"])
            hotel.image = "hotels/downloaded.webp"
            hotel.save(update_fields=("image",))

        mocked_call_command.side_effect = save_image

        downloaded, skipped, failures = download_missing_hotel_photos(
            {
                existing.id: "https://example.com/existing/",
                missing.id: "https://example.com/missing/",
            }
        )

        self.assertEqual(downloaded, 1)
        self.assertEqual(skipped, 1)
        self.assertEqual(failures, [])
        mocked_call_command.assert_called_once_with(
            "download_hotel_page_photo",
            hotel_name="Missing Hotel",
            page_url="https://example.com/missing/",
            apply=True,
        )
