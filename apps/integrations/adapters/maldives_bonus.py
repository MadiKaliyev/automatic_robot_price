import re
from html import unescape
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from ..base import BaseSourceAdapter, NormalizedOffer, SearchRequest


class MaldivesBonusAdapter(BaseSourceAdapter):
    """Collect hotel cards from the public Maldives Bonus catalogue.

    Maldives Bonus does not publish a price for these records.  The adapter
    still returns the common offer shape, but ``price`` is explicitly ``None``
    and ``currency`` is empty, so callers cannot mistake a missing quote for a
    zero-valued quote.
    """

    source_code = "maldives_bonus"
    source_name = "Maldives Bonus"
    base_url = "https://www.maldives-bonus.com/hotel-selection/seychelles/"
    partial_url = "https://www.maldives-bonus.com/hotel-selection/partial/"
    manual_quote_required = True
    status_message = (
        "Онлайн-цены отсутствуют. Получены данные каталога отелей; "
        "стоимость запрашивается у менеджера Maldives Bonus."
    )

    def __init__(self, timeout: float = 30.0, client: httpx.Client | None = None):
        self.timeout = timeout
        self._client = client
        self._last_offers_count = 0

    @staticmethod
    def _clean(value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", unescape(value)).strip()

    @staticmethod
    def _hotel_code(href: str, airport_url: str) -> str:
        match = re.search(r"/hotel/(\d+)/", airport_url)
        if match:
            return match.group(1)
        path = urlparse(href).path.rstrip("/")
        return path.rsplit("/", 1)[-1]

    def parse_html(self, html: str, request: SearchRequest) -> list[NormalizedOffer]:
        offers: list[NormalizedOffer] = []
        seen: set[str] = set()
        cards = re.split(
            r'<li class="hotels-list__item hotel-list-item-wrapper"[^>]*>',
            html,
        )[1:]

        for card in cards:
            title = re.search(
                r'<a class="hotel-card__title-link"(?P<attrs>[^>]*)>(?P<name>.*?)</a>',
                card,
                flags=re.DOTALL,
            )
            if not title:
                continue

            attrs = title.group("attrs")
            href_match = re.search(r'href="([^"]+)"', attrs)
            if not href_match:
                continue
            href = unescape(href_match.group(1))
            airport_match = re.search(
                r'data-find-nearest-airport-by-hotel-url="([^"]*)"', attrs
            )
            airport_url = airport_match.group(1) if airport_match else ""
            code = self._hotel_code(href, airport_url)
            if code in seen:
                continue
            seen.add(code)

            name = self._clean(title.group("name"))
            country_match = re.search(
                r"hotel-card__location-link--country[^>]*>(.*?)</a>", card, re.DOTALL
            )
            resort_match = re.search(
                r"hotel-card__location-link--resort[^>]*>(.*?)</a>", card, re.DOTALL
            )
            latitude = re.search(r'data-latitude="([^"]*)"', attrs)
            longitude = re.search(r'data-longitude="([^"]*)"', attrs)
            images = [
                urljoin(self.base_url, unescape(path))
                for path in re.findall(
                    r'<img[^>]+src="([^"]+)"[^>]+class="[^"]*custom-slider__image',
                    card,
                )
            ]
            query = parse_qs(urlparse(href).query)

            offers.append(
                NormalizedOffer(
                    source_code=self.source_code,
                    source_hotel_name=name,
                    source_hotel_code=code,
                    source_room_name="Не указано",
                    source_room_code="",
                    meal_code="Не указано",
                    check_in=request.check_in,
                    nights=request.nights,
                    adults=request.adults,
                    children_ages=list(request.children_ages),
                    transfer_included=False,
                    taxes_included=False,
                    price=None,
                    currency="",
                    offer_url=urljoin(self.base_url, href),
                    included_components={
                        "hotel": True,
                        "flight": False,
                        "transfer": False,
                        "price_available": False,
                        "manual_quote_required": True,
                    },
                    raw_data={
                        "country": self._clean(country_match.group(1))
                        if country_match
                        else "",
                        "resort": self._clean(resort_match.group(1))
                        if resort_match
                        else "",
                        "latitude": latitude.group(1) if latitude else "",
                        "longitude": longitude.group(1) if longitude else "",
                        "images": images,
                        "rate_code": (query.get("rate_code") or [""])[0],
                    },
                )
            )
        return offers

    def fetch(self, request: SearchRequest) -> list[NormalizedOffer]:
        owns_client = self._client is None
        client = self._client or httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "TourPriceMonitor/1.0"},
        )
        try:
            response = client.get(self.base_url)
            response.raise_for_status()
            html = response.text
            rest_ids_match = re.search(
                r'id="hotel-list"[^>]+data-rest-ids="([^"]*)"', html
            )
            rest_ids = rest_ids_match.group(1).split(",") if rest_ids_match else []
            for start in range(0, len(rest_ids), 50):
                partial = client.get(
                    self.partial_url,
                    params=[
                        ("hotel_ids", value) for value in rest_ids[start : start + 50]
                    ],
                )
                partial.raise_for_status()
                html += partial.text
            offers = self.parse_html(html, request)
            self._last_offers_count = len(offers)
            return offers
        finally:
            if owns_client:
                client.close()

    search = fetch
    collect = fetch

    def get_status(self) -> dict:
        return {
            "source_code": self.source_code,
            "source_name": self.source_name,
            "source_url": self.base_url,
            "manual_quote_required": self.manual_quote_required,
            "offers_count": self._last_offers_count,
            "message": self.status_message,
        }
