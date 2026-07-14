from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import ComparisonGroup, ComparisonItem, PriceOffer


def price_composition_key(offer: PriceOffer) -> tuple[bool, ...]:
    components = (
        offer.included_components if isinstance(offer.included_components, dict) else {}
    )

    return (
        bool(components.get("hotel", True)),
        bool(components.get("flight", False)),
        bool(
            components.get(
                "transfer",
                offer.transfer_included,
            )
        ),
        bool(offer.taxes_included),
    )


class ComparisonService:
    """Сравнивает только предложения с полностью одинаковыми параметрами."""

    @staticmethod
    def _key(offer: PriceOffer) -> tuple:
        return (
            offer.hotel_id,
            offer.room_category_id,
            offer.meal_plan_id,
            offer.check_in,
            offer.nights,
            offer.adults,
            tuple(offer.children_ages or []),
            offer.transfer_included,
            offer.taxes_included,
            offer.currency.upper(),
            price_composition_key(offer),
        )

    @staticmethod
    def _color(percent: Decimal) -> str:
        if percent == 0:
            return ComparisonItem.ColorStatus.GREEN
        if percent <= Decimal("5"):
            return ComparisonItem.ColorStatus.YELLOW
        if percent <= Decimal("10"):
            return ComparisonItem.ColorStatus.ORANGE
        return ComparisonItem.ColorStatus.RED

    @classmethod
    @transaction.atomic
    def build_for_run(cls, run):
        run.comparison_groups.all().delete()
        grouped = defaultdict(list)
        offers = PriceOffer.objects.filter(run=run).select_related(
            "source", "hotel", "room_category", "meal_plan"
        )
        for offer in offers:
            grouped[cls._key(offer)].append(offer)

        created_groups = []
        for offers_in_group in grouped.values():
            # Для честного сравнения нужны хотя бы два разных источника.
            source_ids = {offer.source_id for offer in offers_in_group}
            if len(source_ids) < 2:
                continue

            best_offer = min(offers_in_group, key=lambda item: item.price)
            group = ComparisonGroup.objects.create(
                run=run,
                hotel=best_offer.hotel,
                room_category=best_offer.room_category,
                meal_plan=best_offer.meal_plan,
                check_in=best_offer.check_in,
                nights=best_offer.nights,
                adults=best_offer.adults,
                children_ages=best_offer.children_ages,
                transfer_included=best_offer.transfer_included,
                taxes_included=best_offer.taxes_included,
                currency=best_offer.currency.upper(),
                best_offer=best_offer,
                best_price=best_offer.price,
            )

            for offer in offers_in_group:
                difference = offer.price - best_offer.price
                if best_offer.price == 0:
                    percent = Decimal("0")
                else:
                    percent = (difference / best_offer.price * Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                ComparisonItem.objects.create(
                    group=group,
                    offer=offer,
                    absolute_difference=difference,
                    percent_difference=percent,
                    color_status=cls._color(percent),
                    is_best=(offer.pk == best_offer.pk),
                )
            created_groups.append(group)
        return created_groups
