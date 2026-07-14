from django.contrib import admin

from .models import (
    Hotel,
    MealPlan,
    RoomCategory,
    Source,
    SourceHotel,
    SourceRoomCategory,
)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "enabled")
    list_editable = ("enabled",)
    search_fields = ("name", "code")


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ("canonical_name", "country", "destination", "active")
    list_filter = ("country", "active")
    search_fields = ("canonical_name", "destination")


@admin.register(SourceHotel)
class SourceHotelAdmin(admin.ModelAdmin):
    list_display = ("source_name", "source", "hotel", "match_status", "active")
    list_filter = ("source", "match_status", "active")
    search_fields = ("source_name", "source_code", "hotel__canonical_name")
    autocomplete_fields = ("hotel",)


@admin.register(RoomCategory)
class RoomCategoryAdmin(admin.ModelAdmin):
    list_display = ("canonical_name", "hotel", "active")
    list_filter = ("active",)
    search_fields = ("canonical_name", "hotel__canonical_name")
    autocomplete_fields = ("hotel",)


@admin.register(SourceRoomCategory)
class SourceRoomCategoryAdmin(admin.ModelAdmin):
    list_display = ("source_name", "source_hotel", "room_category", "match_status")
    list_filter = ("source_hotel__source", "match_status")
    search_fields = ("source_name", "source_code", "room_category__canonical_name")
    autocomplete_fields = ("source_hotel", "room_category")


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
