from django.core.validators import MinValueValidator
from django.db import models

from apps.catalog.models import (
    Hotel,
    MealPlan,
    RoomCategory,
    Source,
    SourceHotel,
    SourceRoomCategory,
)


class RunStatus(models.TextChoices):
    PENDING = "pending", "Ожидает"
    RUNNING = "running", "Выполняется"
    SUCCESS = "success", "Успешно"
    PARTIAL = "partial", "Частично"
    FAILED = "failed", "Ошибка"


class SearchScenario(models.Model):
    name = models.CharField("Название", max_length=200)
    destination = models.CharField("Направление", max_length=150, default="Сейшелы")
    check_in = models.DateField("Дата заезда")
    nights = models.PositiveSmallIntegerField(
        "Количество ночей", validators=[MinValueValidator(1)]
    )
    adults = models.PositiveSmallIntegerField(
        "Взрослых", default=2, validators=[MinValueValidator(1)]
    )
    children_ages = models.JSONField("Возраст детей", default=list, blank=True)
    include_flight = models.BooleanField("Включать перелёт", default=False)
    include_transfer = models.BooleanField("Включать трансфер", default=False)
    first_available_only = models.BooleanField(
        "Только первая доступная категория", default=True
    )
    preferred_currency = models.CharField(
        "Валюта сравнения", max_length=3, default="USD"
    )
    active = models.BooleanField("Активен", default=True)
    automatic_enabled = models.BooleanField(
        "Запускать автоматически",
        default=False,
    )
    hotels = models.ManyToManyField(
        Hotel, related_name="search_scenarios", verbose_name="Отели", blank=True
    )

    class Meta:
        verbose_name = "Сценарий поиска"
        verbose_name_plural = "Сценарии поиска"
        ordering = ("-check_in", "name")
        indexes = [
            models.Index(
                fields=("active", "automatic_enabled"),
                name="scenario_schedule_idx",
            )
        ]

    def __str__(self):
        return self.name


class CollectionRun(models.Model):
    scenario = models.ForeignKey(
        SearchScenario,
        on_delete=models.PROTECT,
        related_name="runs",
        verbose_name="Сценарий",
    )
    status = models.CharField(
        "Статус", max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING
    )
    trigger = models.CharField("Способ запуска", max_length=30, default="manual")
    started_at = models.DateTimeField("Начало", auto_now_add=True)
    finished_at = models.DateTimeField("Окончание", null=True, blank=True)
    error_message = models.TextField("Ошибка", blank=True)

    class Meta:
        verbose_name = "Запуск сбора"
        verbose_name_plural = "Запуски сбора"
        ordering = ("-started_at",)
        indexes = [
            models.Index(
                fields=("status", "started_at"),
                name="run_status_started_idx",
            )
        ]

    def __str__(self):
        return f"{self.scenario} — {self.started_at:%d.%m.%Y %H:%M}"


class PriceOffer(models.Model):
    run = models.ForeignKey(
        CollectionRun,
        on_delete=models.CASCADE,
        related_name="offers",
        verbose_name="Запуск",
    )
    source = models.ForeignKey(
        Source, on_delete=models.PROTECT, related_name="offers", verbose_name="Источник"
    )
    source_hotel = models.ForeignKey(
        SourceHotel,
        on_delete=models.PROTECT,
        related_name="offers",
        verbose_name="Отель у источника",
    )
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.PROTECT,
        related_name="offers",
        verbose_name="Единый отель",
    )
    source_room = models.ForeignKey(
        SourceRoomCategory,
        on_delete=models.PROTECT,
        related_name="offers",
        verbose_name="Номер у источника",
    )
    room_category = models.ForeignKey(
        RoomCategory,
        on_delete=models.PROTECT,
        related_name="offers",
        verbose_name="Единая категория",
    )
    meal_plan = models.ForeignKey(
        MealPlan,
        on_delete=models.PROTECT,
        related_name="offers",
        verbose_name="Питание",
    )
    check_in = models.DateField("Дата заезда")
    nights = models.PositiveSmallIntegerField(
        "Ночей", validators=[MinValueValidator(1)]
    )
    adults = models.PositiveSmallIntegerField(
        "Взрослых", validators=[MinValueValidator(1)]
    )
    children_ages = models.JSONField("Возраст детей", default=list, blank=True)
    transfer_included = models.BooleanField("Трансфер включён", default=False)
    taxes_included = models.BooleanField("Налоги включены", default=True)
    price = models.DecimalField(
        "Цена", max_digits=14, decimal_places=2, validators=[MinValueValidator(0)]
    )
    currency = models.CharField("Валюта", max_length=3)
    included_components = models.JSONField("Состав цены", default=dict, blank=True)
    offer_url = models.URLField("Ссылка", blank=True, max_length=1000)
    raw_data = models.JSONField("Исходный ответ", default=dict, blank=True)
    captured_at = models.DateTimeField("Получено", auto_now_add=True)

    class Meta:
        verbose_name = "Предложение"
        verbose_name_plural = "Предложения"
        ordering = ("-captured_at",)
        indexes = [
            models.Index(
                fields=("run", "hotel", "room_category", "meal_plan"),
                name="offer_compare_idx",
            ),
            models.Index(
                fields=("source", "check_in", "nights", "adults", "currency"),
                name="offer_latest_source_idx",
            ),
            models.Index(
                fields=(
                    "hotel",
                    "room_category",
                    "meal_plan",
                    "check_in",
                    "nights",
                ),
                name="offer_match_params_idx",
            ),
        ]

    def __str__(self):
        return f"{self.source}: {self.hotel} — {self.price} {self.currency}"


class ComparisonGroup(models.Model):
    run = models.ForeignKey(
        CollectionRun,
        on_delete=models.CASCADE,
        related_name="comparison_groups",
        verbose_name="Запуск",
    )
    hotel = models.ForeignKey(Hotel, on_delete=models.PROTECT, verbose_name="Отель")
    room_category = models.ForeignKey(
        RoomCategory, on_delete=models.PROTECT, verbose_name="Категория номера"
    )
    meal_plan = models.ForeignKey(
        MealPlan, on_delete=models.PROTECT, verbose_name="Питание"
    )
    check_in = models.DateField("Дата заезда")
    nights = models.PositiveSmallIntegerField("Ночей")
    adults = models.PositiveSmallIntegerField("Взрослых")
    children_ages = models.JSONField("Возраст детей", default=list, blank=True)
    transfer_included = models.BooleanField("Трансфер включён")
    taxes_included = models.BooleanField("Налоги включены")
    currency = models.CharField("Валюта", max_length=3)
    best_offer = models.ForeignKey(
        PriceOffer,
        on_delete=models.PROTECT,
        related_name="best_for_groups",
        verbose_name="Лучшая цена",
    )
    best_price = models.DecimalField("Лучшая цена", max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Группа сравнения"
        verbose_name_plural = "Группы сравнения"
        ordering = ("hotel__canonical_name", "room_category__canonical_name")
        indexes = [
            models.Index(
                fields=("run", "hotel"),
                name="comparison_run_hotel_idx",
            )
        ]

    def __str__(self):
        return f"{self.hotel} — {self.best_price} {self.currency}"


class ComparisonItem(models.Model):
    class ColorStatus(models.TextChoices):
        GREEN = "green", "Лучшая цена"
        YELLOW = "yellow", "До 5%"
        ORANGE = "orange", "От 5% до 10%"
        RED = "red", "Более 10%"

    group = models.ForeignKey(
        ComparisonGroup,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Группа",
    )
    offer = models.OneToOneField(
        PriceOffer,
        on_delete=models.CASCADE,
        related_name="comparison_item",
        verbose_name="Предложение",
    )
    absolute_difference = models.DecimalField(
        "Разница в валюте", max_digits=14, decimal_places=2
    )
    percent_difference = models.DecimalField(
        "Разница в процентах", max_digits=9, decimal_places=2
    )
    color_status = models.CharField("Цвет", max_length=10, choices=ColorStatus.choices)
    is_best = models.BooleanField("Лучшая цена", default=False)

    class Meta:
        verbose_name = "Результат сравнения"
        verbose_name_plural = "Результаты сравнения"
        ordering = ("offer__price",)

    def __str__(self):
        return f"{self.offer.source}: +{self.absolute_difference} / {self.percent_difference}%"
