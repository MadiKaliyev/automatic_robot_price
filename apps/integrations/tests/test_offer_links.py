from urllib.parse import parse_qs, urlparse

from django.test import SimpleTestCase

from apps.integrations.adapters.resort_holiday import (
    build_offer_url,
    find_hotel_id,
)


class ResortHolidayOfferLinkTests(SimpleTestCase):
    def test_finds_hotel_id_despite_name_suffixes(self):
        hotel_id = find_hotel_id(
            "Story (Seychelles) 5* (Остров Маэ)",
            [
                ("91", "Savoy Seychelles Resort & Spa 5*"),
                ("173", "STORY Seychelles (ex The H Resort) 5*"),
            ],
        )

        self.assertEqual(hotel_id, "173")

    def test_builds_prefilled_search_url(self):
        prices_url = (
            "https://search.resort-holiday.com/search_hotel"
            "?STATEINC=78&CHECKIN_BEG=20260910"
            "&CHECKIN_END=20260910&NIGHTS_FROM=7"
            "&NIGHTS_TILL=7&ADULT=2&CURRENCY=3"
            "&HOTELS_ANY=1&samo_action=PRICES"
        )

        result = build_offer_url(
            prices_url,
            "173",
        )
        query = parse_qs(urlparse(result).query)

        self.assertEqual(query["HOTELS"], ["173"])
        self.assertEqual(query["CHECKIN_BEG"], ["20260910"])
        self.assertEqual(query["NIGHTS_FROM"], ["7"])
        self.assertEqual(query["ADULT"], ["2"])
        self.assertEqual(query["DOLOAD"], ["1"])
        self.assertEqual(query["PRICEPAGE"], ["1"])
        self.assertNotIn("HOTELS_ANY", query)
        self.assertNotIn("samo_action", query)
