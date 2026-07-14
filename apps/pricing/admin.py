from django.contrib import admin

from .models import (
    CollectionRun,
    ComparisonGroup,
    ComparisonItem,
    PriceOffer,
    SearchScenario,
)


@admin.register(SearchScenario)
class SearchScenarioAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "destination",
        "check_in",
        "nights",
        "adults",
        "preferred_currency",
        "active",
        "automatic_enabled",
    )
    list_filter = (
        "destination",
        "active",
        "automatic_enabled",
        "include_flight",
        "include_transfer",
    )
    list_editable = ("automatic_enabled",)
    filter_horizontal = ("hotels",)


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = ("scenario", "status", "trigger", "started_at", "finished_at")
    list_filter = ("status", "trigger")
    readonly_fields = ("started_at",)


@admin.register(PriceOffer)
class PriceOfferAdmin(admin.ModelAdmin):
    list_display = (
        "hotel",
        "source",
        "room_category",
        "meal_plan",
        "price",
        "currency",
        "captured_at",
    )
    list_filter = (
        "source",
        "currency",
        "meal_plan",
        "transfer_included",
        "taxes_included",
    )
    search_fields = (
        "hotel__canonical_name",
        "source_hotel__source_name",
        "source_room__source_name",
    )
    readonly_fields = ("captured_at",)


class ComparisonItemInline(admin.TabularInline):
    model = ComparisonItem
    extra = 0
    readonly_fields = (
        "offer",
        "absolute_difference",
        "percent_difference",
        "color_status",
        "is_best",
    )
    can_delete = False


@admin.register(ComparisonGroup)
class ComparisonGroupAdmin(admin.ModelAdmin):
    list_display = (
        "hotel",
        "room_category",
        "meal_plan",
        "best_price",
        "currency",
        "run",
    )
    list_filter = ("currency", "meal_plan")
    inlines = (ComparisonItemInline,)
    readonly_fields = ("created_at",)
