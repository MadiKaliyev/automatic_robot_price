import hashlib
import re
from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.sync_api import (
    sync_playwright,
)

from apps.integrations.base import (
    NormalizedOffer,
    SearchRequest,
)


class MaldivianaAdapter:
    source_code = "maldiviana"

    base_url = "https://online.maldives.ru/search_hotel"

    currency = "EUR"
    currency_value = "3"

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 120000,
    ) -> None:
        self.headless = headless
        self.timeout = timeout

    @staticmethod
    def clean_text(text: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            text or "",
        ).strip()

    @staticmethod
    def stable_code(value: str) -> str:
        return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def format_date(value) -> str:
        return value.strftime("%d.%m.%Y")

    @staticmethod
    def parse_date(value: str):
        match = re.search(
            r"\d{2}\.\d{2}\.\d{4}",
            value,
        )

        if not match:
            raise ValueError(f"Не удалось определить дату: {value}")

        return datetime.strptime(
            match.group(),
            "%d.%m.%Y",
        ).date()

    @staticmethod
    def parse_price(value: str) -> Decimal:
        match = re.search(
            r"(\d[\d\s.,]*)\s*(?:EUR|RUB|USD)",
            value,
            re.IGNORECASE,
        )

        if not match:
            raise ValueError(f"Не удалось определить цену: {value}")

        price_text = match.group(1).replace("\xa0", "").replace(" ", "")

        if "," in price_text and "." not in price_text:
            price_text = price_text.replace(
                ",",
                ".",
            )
        else:
            price_text = price_text.replace(
                ",",
                "",
            )

        return Decimal(price_text)

    @staticmethod
    def normalize_meal(value: str) -> str:
        cleaned = value.strip().upper()

        mapping = {
            "БЕЗ ПИТАНИЯ": "RO",
            "NO MEAL": "RO",
            "RO": "RO",
            "BB": "BB",
            "BED BREAKFAST": "BB",
            "BED & BREAKFAST": "BB",
            "HB": "HB",
            "HALF BOARD": "HB",
            "FB": "FB",
            "FULL BOARD": "FB",
            "AI": "AI",
            "ALL INCLUSIVE": "AI",
        }

        return mapping.get(
            cleaned,
            cleaned,
        )

    @classmethod
    def normalize_room_name(
        cls,
        value: str,
    ) -> str:
        value = cls.clean_text(value)

        value = re.sub(
            r"\s*/\s*\d+\s*ADL.*$",
            "",
            value,
            flags=re.IGNORECASE,
        )

        return value.strip()

    @classmethod
    def normalize_hotel_name(
        cls,
        value: str,
    ) -> str:
        return cls.clean_text(value)

    @classmethod
    def hotel_lookup_name(
        cls,
        value: str,
    ) -> str:
        value = cls.clean_text(value).lower()

        value = value.replace(
            "&",
            " and ",
        )

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
            r"\b7s\b",
            " ",
            value,
        )

        value = re.sub(
            r"[^a-z?-??0-9]+",
            " ",
            value,
        )

        stop_words = {
            "hotel",
            "resort",
            "spa",
            "seychelles",
            "the",
            "and",
        }

        return " ".join(word for word in value.split() if word not in stop_words)

    def get_hotel_options(
        self,
        page,
    ) -> list[tuple[str, str]]:
        raw_options = page.locator('.HOTELS input[type="checkbox"]').evaluate_all(
            """
            (elements) => {
                const allLabels = Array.from(
                    document.querySelectorAll(
                        "label"
                    )
                );

                return elements.map(
                    element => {
                        const closestLabel =
                            element.closest(
                                "label"
                            );

                        const linkedLabel =
                            allLabels.find(
                                label =>
                                    label.htmlFor
                                    === element.id
                            );

                        const container =
                            closestLabel
                            || linkedLabel
                            || element.parentElement;

                        return {
                            value:
                                element.value || "",
                            text:
                                (
                                    container
                                    && container.innerText
                                )
                                ? container.innerText.trim()
                                : ""
                        };
                    }
                );
            }
            """
        )

        return [
            (
                str(option.get("value", "")),
                self.clean_text(str(option.get("text", ""))),
            )
            for option in raw_options
            if option.get("value")
        ]

    def find_hotel_id(
        self,
        hotel_name: str,
        options: list[tuple[str, str]],
    ) -> str:
        target = self.hotel_lookup_name(hotel_name)

        if not target:
            return ""

        target_words = set(target.split())

        best_id = ""
        best_score = 0.0

        for hotel_id, option_name in options:
            candidate = self.hotel_lookup_name(option_name)

            if not candidate:
                continue

            if target == candidate:
                return hotel_id

            candidate_words = set(candidate.split())

            union = target_words | candidate_words

            common = target_words & candidate_words

            token_score = len(common) / len(union) if union else 0.0

            text_score = SequenceMatcher(
                None,
                target,
                candidate,
            ).ratio()

            containment_score = 0.0

            if target in candidate or candidate in target:
                containment_score = 0.95

            score = max(
                token_score,
                text_score,
                containment_score,
            )

            if score > best_score:
                best_score = score
                best_id = hotel_id

        if best_score < 0.65:
            return ""

        return best_id

    def build_offer_url(
        self,
        prices_url: str,
        hotel_id: str,
    ) -> str:
        parsed_prices = urlparse(prices_url)

        query = parse_qs(
            parsed_prices.query,
            keep_blank_values=True,
        )

        for technical_key in (
            "samo_action",
            "ACTION",
            "action",
            "RESULT",
            "result",
            "_",
        ):
            query.pop(
                technical_key,
                None,
            )

        query["DOLOAD"] = ["1"]
        query["PRICEPAGE"] = ["1"]

        if hotel_id:
            query["HOTELS"] = [hotel_id]

            query.pop(
                "HOTELS_ANY",
                None,
            )

        base = urlparse(self.base_url)

        return base._replace(
            query=urlencode(
                query,
                doseq=True,
            ),
            fragment="",
        ).geturl()

    def set_date(
        self,
        page,
        field_name: str,
        value: str,
    ) -> None:
        field = page.locator(f'input[name="{field_name}"]')

        if field.count() == 0:
            raise RuntimeError(f"Не найдено поле даты: {field_name}")

        field.evaluate(
            """
            (element, value) => {
                element.removeAttribute("readonly");
                element.value = value;

                element.dispatchEvent(
                    new Event(
                        "input",
                        {bubbles: true}
                    )
                );

                element.dispatchEvent(
                    new Event(
                        "change",
                        {bubbles: true}
                    )
                );

                element.dispatchEvent(
                    new Event(
                        "blur",
                        {bubbles: true}
                    )
                );
            }
            """,
            value,
        )

    def select_value(
        self,
        page,
        field_name: str,
        value: str,
    ) -> None:
        field = page.locator(f'select[name="{field_name}"]')

        if field.count() == 0:
            raise RuntimeError(f"Не найден список: {field_name}")

        field.select_option(
            value=value,
            force=True,
        )

    def force_select_value(
        self,
        page,
        field_name: str,
        value: str,
    ) -> None:
        field = page.locator(f'select[name="{field_name}"]')

        if field.count() == 0:
            raise RuntimeError(f"Не найден список: {field_name}")

        field.evaluate(
            """
            (element, value) => {
                element.value = value;

                element.dispatchEvent(
                    new Event(
                        "input",
                        {bubbles: true}
                    )
                );
            }
            """,
            value,
        )

    def select_tour(self, page) -> None:
        tour_select = page.locator('select[name="TOURINC"]')

        options = tour_select.locator("option")

        for index in range(options.count()):
            option = options.nth(index)

            value = option.get_attribute("value") or ""

            text = self.clean_text(option.inner_text())

            if value != "0" and text.lower() == "seychelles":
                tour_select.select_option(
                    value=value,
                    force=True,
                )
                return

        raise RuntimeError("Тур Seychelles не найден.")

    def select_hotels(
        self,
        page,
        hotel_ids: tuple[str, ...],
    ) -> None:
        if not hotel_ids:
            return

        any_hotels = page.locator('input[name="HOTELS_ANY"]')

        if any_hotels.is_checked():
            any_hotels.uncheck(
                force=True,
            )

        selected = 0

        for hotel_id in hotel_ids:
            checkbox = page.locator(f'.HOTELS input[value="{hotel_id}"]')

            if checkbox.count() == 0:
                continue

            checkbox.check(
                force=True,
            )

            selected += 1

        if selected == 0:
            raise RuntimeError("На сайте не найдены указанные ID отелей.")

    def set_children(
        self,
        page,
        children_ages: tuple[int, ...],
    ) -> None:
        if len(children_ages) > 3:
            raise ValueError("Мальдивиана поддерживает не более трёх детей.")

        self.select_value(
            page,
            "CHILD",
            str(len(children_ages)),
        )

        page.wait_for_timeout(1000)

        for index, age in enumerate(
            children_ages,
            start=1,
        ):
            self.select_value(
                page,
                f"AGE{index}",
                str(age),
            )

    def validate_prices_url(
        self,
        prices_url: str,
        request: SearchRequest,
    ) -> None:
        query = parse_qs(urlparse(prices_url).query)

        nights_from = query.get(
            "NIGHTS_FROM",
            [""],
        )[0]

        nights_till = query.get(
            "NIGHTS_TILL",
            [""],
        )[0]

        if nights_from != str(request.nights) or nights_till != str(request.nights):
            raise RuntimeError(
                f"Сайт отправил неверный диапазон ночей: {nights_from}-{nights_till}"
            )

    def parse_rows(
        self,
        page,
        request: SearchRequest,
        prices_url: str,
    ) -> list[NormalizedOffer]:
        selectors = ".resultset tr, .resultsetPricesDynamic tr, .resultsetGrouped tr"

        rows = page.locator(selectors).filter(has_text=self.currency)

        offers = []
        duplicates = set()

        def detail_name_key(value: str) -> str:
            value = self.clean_text(value).lower()

            value = value.replace(
                "&",
                " and ",
            )

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
                r"[^a-z0-9]+",
                " ",
                value,
            )

            return " ".join(value.split())

        hotel_detail_links = {}

        raw_hotel_links = page.locator(
            'a[href*="/seychelles/hotels/"], a[href*="/hotel/seyshelskie-ostrova/"]'
        ).evaluate_all(
            """
            elements => elements.map(
                element => ({
                    text: (
                        element.textContent || ""
                    ).trim(),
                    href:
                        element.href
                        || element.getAttribute(
                            "href"
                        )
                        || ""
                })
            )
            """
        )

        for item in raw_hotel_links:
            link_text = self.clean_text(item.get("text", ""))

            link_href = item.get(
                "href",
                "",
            )

            if not link_text or not link_href:
                continue

            hotel_detail_links[detail_name_key(link_text)] = urljoin(
                self.base_url,
                link_href,
            )

        hotel_options = self.get_hotel_options(page)

        for index in range(rows.count()):
            row = rows.nth(index)

            # Не берём родительские строки,
            # содержащие вложенные таблицы.
            if row.locator("tr").count() > 0:
                continue

            cells = [
                self.clean_text(text)
                for text in row.locator(":scope > td").all_inner_texts()
            ]

            cells = [cell for cell in cells if cell]

            if len(cells) < 8:
                continue

            try:
                check_in = self.parse_date(cells[0])

                nights = int(
                    re.search(
                        r"\d+",
                        cells[2],
                    ).group()
                )

                hotel_name = self.normalize_hotel_name(cells[3])

                meal_code = self.normalize_meal(cells[4])

                room_name = self.normalize_room_name(cells[5])

                price = self.parse_price(cells[6])

                offer_code = cells[7]

            except (
                AttributeError,
                ValueError,
            ):
                continue

            if nights != request.nights:
                continue

            hotel_external_id = self.find_hotel_id(
                hotel_name,
                hotel_options,
            )

            offer_url = self.build_offer_url(
                prices_url,
                hotel_external_id,
            )

            hotel_detail_url = hotel_detail_links.get(
                detail_name_key(hotel_name),
                "",
            )

            if not hotel_detail_url:
                target_key = detail_name_key(hotel_name)

                target_words = set(target_key.split())

                best_overlap = 0.0

                for (
                    link_key,
                    link_url,
                ) in hotel_detail_links.items():
                    link_words = set(link_key.split())

                    union = target_words | link_words

                    common = target_words & link_words

                    overlap = len(common) / len(union) if union else 0.0

                    if overlap > best_overlap:
                        best_overlap = overlap
                        hotel_detail_url = link_url

                if best_overlap < 0.6:
                    hotel_detail_url = ""

            duplicate_key = (
                check_in,
                nights,
                hotel_name,
                meal_code,
                room_name,
                price,
                offer_code,
            )

            if duplicate_key in duplicates:
                continue

            duplicates.add(duplicate_key)

            hotel_code = hotel_external_id or self.stable_code(hotel_name.lower())

            room_code = self.stable_code(hotel_name.lower() + "|" + room_name.lower())

            offers.append(
                NormalizedOffer(
                    source_code=(self.source_code),
                    source_hotel_name=(hotel_name),
                    source_hotel_code=(hotel_code),
                    source_room_name=(room_name),
                    source_room_code=(room_code),
                    meal_code=meal_code,
                    check_in=check_in,
                    nights=nights,
                    adults=request.adults,
                    children_ages=list(request.children_ages),
                    transfer_included=False,
                    taxes_included=False,
                    price=price,
                    currency=self.currency,
                    offer_url=offer_url,
                    included_components={
                        "flight": False,
                        "transfer": False,
                    },
                    raw_data={
                        "offer_code": offer_code,
                        "tour_name": cells[1],
                        "hotel_raw": cells[3],
                        "meal_raw": cells[4],
                        "room_raw": cells[5],
                        "price_raw": cells[6],
                        "hotel_external_id": (hotel_external_id),
                        "search_url": offer_url,
                        "hotel_detail_url": (hotel_detail_url),
                        "cells": cells,
                    },
                )
            )

        return offers

    def search(
        self,
        request: SearchRequest,
    ) -> list[NormalizedOffer]:
        check_in_text = self.format_date(request.check_in)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-notifications",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )

            context = browser.new_context(
                locale="ru-RU",
                viewport={
                    "width": 1600,
                    "height": 900,
                },
            )

            page = context.new_page()

            try:
                page.goto(
                    self.base_url,
                    wait_until=("domcontentloaded"),
                    timeout=60000,
                )

                page.locator('select[name="STATEINC"]').wait_for(
                    state="attached",
                    timeout=30000,
                )

                self.select_value(
                    page,
                    "STATEINC",
                    "78",
                )

                page.wait_for_function(
                    """
                    () => Array.from(
                        document.querySelectorAll('select[name="TOURINC"] option')
                    ).some(option => option.textContent.trim().toLowerCase() === 'seychelles')
                    """,
                    timeout=30000,
                )

                self.select_tour(page)

                page.locator(".HOTELS input").first.wait_for(
                    state="attached",
                    timeout=30000,
                )

                self.set_date(
                    page,
                    "CHECKIN_BEG",
                    check_in_text,
                )

                self.set_date(
                    page,
                    "CHECKIN_END",
                    check_in_text,
                )

                self.select_value(
                    page,
                    "ADULT",
                    str(request.adults),
                )

                self.set_children(
                    page,
                    request.children_ages,
                )

                self.select_value(
                    page,
                    "CURRENCY",
                    self.currency_value,
                )

                self.select_hotels(
                    page,
                    request.hotel_external_ids,
                )

                # Ночи задаём последними.
                self.select_value(
                    page,
                    "NIGHTS_FROM",
                    str(request.nights),
                )

                self.select_value(
                    page,
                    "NIGHTS_TILL",
                    str(request.nights),
                )

                self.force_select_value(
                    page,
                    "NIGHTS_FROM",
                    str(request.nights),
                )

                self.force_select_value(
                    page,
                    "NIGHTS_TILL",
                    str(request.nights),
                )

                actual_from = page.locator('select[name="NIGHTS_FROM"]').input_value()

                actual_till = page.locator('select[name="NIGHTS_TILL"]').input_value()

                if actual_from != str(request.nights) or actual_till != str(
                    request.nights
                ):
                    raise RuntimeError("Не удалось установить количество ночей.")

                search_button = page.locator(
                    'button:has-text("Искать"), input[value="Искать"]'
                ).first

                with page.expect_response(
                    lambda response: "samo_action=PRICES" in response.url,
                    timeout=self.timeout,
                ) as response_info:
                    search_button.click()

                prices_response = response_info.value

                if prices_response.status != 200:
                    raise RuntimeError(
                        f"Запрос цен завершился со статусом {prices_response.status}."
                    )

                self.validate_prices_url(
                    prices_response.url,
                    request,
                )

                try:
                    page.wait_for_function(
                        """
                        () => {
                            const selectors = [
                                ".resultset",
                                ".resultsetPricesDynamic",
                                ".resultsetGrouped"
                            ];

                            return selectors.some(
                                selector => {
                                    const element =
                                        document
                                        .querySelector(
                                            selector
                                        );

                                    if (!element) {
                                        return false;
                                    }

                                    const text =
                                        element
                                        .innerText || "";

                                    return (
                                        text.includes(
                                            "EUR"
                                        )
                                        || text.includes(
                                            "Предложений "
                                            + "не найдено"
                                        )
                                        || text.includes(
                                            "Нет предложений"
                                        )
                                    );
                                }
                            );
                        }
                        """,
                        timeout=self.timeout,
                    )

                except PlaywrightTimeoutError as error:
                    raise RuntimeError(
                        "Мальдивиана не загрузила результаты за отведённое время."
                    ) from error

                page.wait_for_timeout(3000)

                return self.parse_rows(
                    page,
                    request,
                    prices_response.url,
                )

            finally:
                context.close()
                browser.close()

    def collect(
        self,
        request: SearchRequest,
    ) -> list[NormalizedOffer]:
        return self.search(request)
