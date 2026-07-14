from datetime import date

from django.test import SimpleTestCase

from apps.integrations.adapters.maldives_bonus import MaldivesBonusAdapter
from apps.integrations.base import SearchRequest


class MaldivesBonusAdapterTests(SimpleTestCase):
    def test_parses_hotel_without_inventing_price(self):
        html = """
        <li class="hotels-list__item hotel-list-item-wrapper" data-country-id="231">
          <img src="/media/hotel.jpg" class="custom-slider__image">
          <a class="hotel-card__title-link"
             data-find-nearest-airport-by-hotel-url="/hotel/123/find-airport/"
             data-latitude="-4.3" data-longitude="55.7"
             href="/hotel/test-hotel/?rate_code=ABC">Test Hotel 4*</a>
          <a class="hotel-card__location-link hotel-card__location-link--country">Сейшелы</a>
          <a class="hotel-card__location-link hotel-card__location-link--resort">о. Маэ</a>
        </li>
        """
        request = SearchRequest(check_in=date(2026, 9, 10), nights=7, adults=2)

        offers = MaldivesBonusAdapter().parse_html(html, request)

        self.assertEqual(len(offers), 1)
        offer = offers[0]
        self.assertEqual(offer.source_hotel_code, "123")
        self.assertEqual(offer.source_hotel_name, "Test Hotel 4*")
        self.assertEqual(offer.raw_data["resort"], "о. Маэ")
        self.assertEqual(offer.price, None)
        self.assertEqual(offer.currency, "")
        self.assertTrue(offer.included_components["manual_quote_required"])
