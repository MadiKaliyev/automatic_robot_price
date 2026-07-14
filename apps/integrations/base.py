from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SearchRequest:
    check_in: date
    nights: int
    adults: int = 2
    children_ages: tuple[int, ...] = ()
    hotel_external_ids: tuple[str, ...] = ()
    include_transfer: bool = False


@dataclass
class NormalizedOffer:
    source_code: str
    source_hotel_name: str
    source_hotel_code: str
    source_room_name: str
    source_room_code: str
    meal_code: str
    check_in: date
    nights: int
    adults: int
    children_ages: list[int]
    transfer_included: bool
    taxes_included: bool
    # Some catalogues publish availability/details but require a manual quote.
    # ``None`` means that no price was published; it must never be converted to 0.
    price: Decimal | None
    currency: str
    offer_url: str = ""
    included_components: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)


class BaseSourceAdapter(ABC):
    source_code: str

    @abstractmethod
    def fetch(self, request: SearchRequest) -> list[NormalizedOffer]:
        """Возвращает цены источника в едином формате."""
        raise NotImplementedError
