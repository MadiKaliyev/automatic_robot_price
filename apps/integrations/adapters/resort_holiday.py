import logging
import re
from decimal import Decimal
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urlparse

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ..base import (
    BaseSourceAdapter,
    NormalizedOffer,
    SearchRequest,
)

URL = "https://search.resort-holiday.com/search_hotel"
CURRENCY = "EUR"
logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def hotel_lookup_name(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\b\d+\s*\*", " ", value)
    value = re.sub(r"\b7s\b", " ", value)
    value = re.sub(r"[^a-zа-яё0-9]+", " ", value)

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
    page: Page,
) -> list[tuple[str, str]]:
    raw_options = page.locator('.HOTELS input[type="checkbox"]').evaluate_all(
        """
        (elements) => {
            const allLabels = Array.from(
                document.querySelectorAll("label")
            );

            return elements.map(element => {
                const closestLabel =
                    element.closest("label");

                const linkedLabel = allLabels.find(
                    label => label.htmlFor === element.id
                );

                const container =
                    closestLabel
                    || linkedLabel
                    || element.parentElement;

                return {
                    value: element.value || "",
                    text: (
                        container
                        && container.innerText
                    )
                        ? container.innerText.trim()
                        : ""
                };
            });
        }
        """
    )

    return [
        (
            str(option.get("value", "")),
            clean_text(str(option.get("text", ""))),
        )
        for option in raw_options
        if option.get("value")
    ]


def find_hotel_id(
    hotel_name: str,
    options: list[tuple[str, str]],
) -> str:
    target = hotel_lookup_name(hotel_name)

    if not target:
        return ""

    target_words = set(target.split())
    best_id = ""
    best_score = 0.0

    for hotel_id, option_name in options:
        candidate = hotel_lookup_name(option_name)

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
        query.pop(technical_key, None)

    query["DOLOAD"] = ["1"]
    query["PRICEPAGE"] = ["1"]

    if hotel_id:
        query["HOTELS"] = [hotel_id]
        query.pop("HOTELS_ANY", None)

    base = urlparse(URL)

    return base._replace(
        query=urlencode(
            query,
            doseq=True,
        ),
        fragment="",
    ).geturl()


def set_date(
    page: Page,
    field_name: str,
    date_value: str,
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
                new Event("input", {bubbles: true})
            );

            element.dispatchEvent(
                new Event("change", {bubbles: true})
            );

            element.dispatchEvent(
                new Event("blur", {bubbles: true})
            );
        }
        """,
        date_value,
    )


def force_select_value(
    page: Page,
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
                new Event("input", {bubbles: true})
            );
        }
        """,
        value,
    )


def set_children(
    page: Page,
    children_ages: tuple[int, ...],
) -> None:
    page.locator('select[name="CHILD"]').select_option(
        label=str(len(children_ages)),
        force=True,
    )

    if not children_ages:
        return

    page.wait_for_timeout(1000)

    for index, age in enumerate(
        children_ages,
        start=1,
    ):
        age_field = page.locator(
            f'select[name="AGE{index}"], '
            f'select[name="AGES{index}"], '
            f'select[name="CHILDAGE{index}"]'
        ).first

        if age_field.count() == 0:
            array_fields = page.locator('select[name="AGE[]"], select[name="AGES[]"]')

            if array_fields.count() >= index:
                age_field = array_fields.nth(index - 1)

        if age_field.count() == 0:
            raise RuntimeError(
                f"Resort Holiday не показал поле возраста ребёнка №{index}."
            )

        try:
            age_field.select_option(
                value=str(age),
                force=True,
            )
        except Exception:
            age_field.select_option(
                label=str(age),
                force=True,
            )


def close_popups(page: Page) -> None:
    selectors = [
        'button:has-text("Принять")',
        'button:has-text("Согласен")',
        'button:has-text("Accept")',
        'button:has-text("Закрыть")',
        '[aria-label="Закрыть"]',
        '[aria-label="Close"]',
        ".modal .close",
        ".popup .close",
    ]

    for selector in selectors:
        try:
            button = page.locator(selector).first

            if button.is_visible(timeout=500):
                button.click(timeout=1000)

        except Exception:
            pass


def parse_price(text: str) -> Decimal | None:
    match = re.search(
        r"(\d[\d\s\xa0]*[.,]\d{2})\s*EUR",
        text,
    )

    if not match:
        return None

    value = match.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")

    return Decimal(value)


def parse_result_row(
    row,
    request: SearchRequest,
    prices_url: str,
    hotel_options: list[tuple[str, str]],
) -> NormalizedOffer | None:
    cells = [clean_text(text) for text in row.locator("td").all_inner_texts()]

    if len(cells) < 14:
        return None

    price = parse_price(cells[10])

    if price is None:
        return None

    try:
        site_nights = int(cells[3])
    except ValueError:
        return None

    if site_nights != request.nights:
        return None

    hotel_name = cells[4]
    meal_name = cells[6]
    room_name = cells[7]
    offer_code = cells[13]
    cancellation = ""

    row_text = clean_text(row.inner_text())

    if "Бесплатная отмена" in row_text:
        cancellation = "Бесплатная отмена"
    hotel_external_id = find_hotel_id(
        hotel_name,
        hotel_options,
    )
    offer_url = build_offer_url(
        prices_url,
        hotel_external_id,
    )

    return NormalizedOffer(
        source_code="resort_holiday",
        source_hotel_name=hotel_name,
        source_hotel_code=hotel_external_id,
        source_room_name=room_name,
        source_room_code="",
        meal_code=meal_name,
        check_in=request.check_in,
        nights=site_nights,
        adults=request.adults,
        children_ages=list(request.children_ages),
        transfer_included=False,
        taxes_included=False,
        price=price,
        currency=CURRENCY,
        offer_url=offer_url,
        included_components={
            "hotel": True,
            "flight": False,
            "transfer": False,
            "cancellation": cancellation,
        },
        raw_data={
            "date_text": cells[1],
            "hotel": hotel_name,
            "meal": meal_name,
            "room": room_name,
            "price_text": cells[10],
            "offer_code": offer_code,
            "cancellation": cancellation,
            "hotel_external_id": hotel_external_id,
            "search_url": offer_url,
        },
    )


class ResortHolidayAdapter(BaseSourceAdapter):
    source_code = "resort_holiday"

    def __init__(self, headless: bool = True):
        self.headless = headless

    def fetch(
        self,
        request: SearchRequest,
    ) -> list[NormalizedOffer]:
        offers: list[NormalizedOffer] = []
        duplicates: set[tuple] = set()

        check_in_text = request.check_in.strftime("%d.%m.%Y")

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

            page.on(
                "dialog",
                lambda dialog: dialog.accept(),
            )

            page.on(
                "popup",
                lambda popup: popup.close(),
            )

            try:
                page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                close_popups(page)

                state_field = page.locator('select[name="STATEINC"]')
                state_field.wait_for(state="attached", timeout=30000)
                state_field.select_option(
                    label="Сейшельские острова",
                    force=True,
                )

                try:
                    page.locator('.HOTELS input[type="checkbox"]').first.wait_for(
                        state="attached",
                        timeout=30000,
                    )
                except PlaywrightTimeoutError as error:
                    raise RuntimeError(
                        "Resort Holiday не загрузил список отелей."
                    ) from error

                hotel_options = get_hotel_options(page)

                set_date(
                    page,
                    "CHECKIN_BEG",
                    check_in_text,
                )

                set_date(
                    page,
                    "CHECKIN_END",
                    check_in_text,
                )

                page.locator('select[name="NIGHTS_FROM"]').select_option(
                    value=str(request.nights),
                    force=True,
                )

                page.locator('select[name="NIGHTS_TILL"]').select_option(
                    value=str(request.nights),
                    force=True,
                )

                force_select_value(
                    page,
                    "NIGHTS_FROM",
                    str(request.nights),
                )
                force_select_value(
                    page,
                    "NIGHTS_TILL",
                    str(request.nights),
                )

                actual_nights_from = page.locator(
                    'select[name="NIGHTS_FROM"]'
                ).input_value()
                actual_nights_till = page.locator(
                    'select[name="NIGHTS_TILL"]'
                ).input_value()

                if actual_nights_from != str(
                    request.nights
                ) or actual_nights_till != str(request.nights):
                    raise RuntimeError(
                        "Resort Holiday не установил точное количество ночей."
                    )

                page.locator('select[name="ADULT"]').select_option(
                    label=str(request.adults),
                    force=True,
                )

                set_children(
                    page,
                    request.children_ages,
                )

                page.locator('select[name="CURRENCY"]').select_option(
                    label=CURRENCY,
                    force=True,
                )

                search_button = page.locator(
                    'button:has-text("Искать"), input[value="Искать"]'
                ).first

                if search_button.count() == 0:
                    raise RuntimeError("Не найдена кнопка «Искать»")

                with page.expect_response(
                    lambda response: "samo_action=PRICES" in response.url,
                    timeout=120000,
                ) as response_info:
                    search_button.click()

                prices_response = response_info.value

                if prices_response.status != 200:
                    raise RuntimeError(
                        "Запрос цен Resort Holiday "
                        "завершился со статусом "
                        f"{prices_response.status}."
                    )

                try:
                    page.wait_for_function(
                        """
                        (currency) => {
                            const text = document.body.innerText || "";
                            return text.includes(currency)
                                || text.includes("Предложений не найдено")
                                || text.includes("Нет предложений");
                        }
                        """,
                        CURRENCY,
                        timeout=30000,
                    )
                except PlaywrightTimeoutError:
                    logger.warning(
                        "Resort Holiday не показал явный статус выдачи за 30 секунд"
                    )

                result_rows = page.locator("tr").filter(has_text=CURRENCY)
                logger.info(
                    "Resort Holiday: найдено %s строк с ценами и %s строк "
                    "с бесплатной отменой",
                    result_rows.count(),
                    page.locator("tr").filter(has_text="Бесплатная отмена").count(),
                )
                for index in range(result_rows.count()):
                    row = result_rows.nth(index)

                    if row.locator("tr").count() > 0:
                        continue

                    offer = parse_result_row(
                        row,
                        request,
                        prices_response.url,
                        hotel_options,
                    )

                    if offer is None:
                        continue

                    duplicate_key = (
                        offer.source_hotel_name,
                        offer.source_room_name,
                        offer.meal_code,
                        offer.price,
                    )

                    if duplicate_key in duplicates:
                        continue

                    duplicates.add(duplicate_key)
                    offers.append(offer)

            finally:
                context.close()
                browser.close()

        return offers
