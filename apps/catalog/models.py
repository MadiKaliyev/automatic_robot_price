from django.db import models


class MatchStatus(models.TextChoices):
    AUTO = "auto", "Сопоставлено автоматически"
    CONFIRMED = "confirmed", "Подтверждено вручную"
    REVIEW = "review", "Требует проверки"
    IGNORE = "ignore", "Не сопоставлять"


class Source(models.Model):
    code = models.SlugField("Код", unique=True)
    name = models.CharField("Название", max_length=150)
    base_url = models.URLField("Адрес сайта", blank=True)
    enabled = models.BooleanField("Включён", default=True)

    class Meta:
        verbose_name = "Источник"
        verbose_name_plural = "Источники"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Hotel(models.Model):
    country = models.CharField(
        "Страна",
        max_length=100,
        default="Сейшелы",
    )

    destination = models.CharField(
        "Курорт/остров",
        max_length=150,
        blank=True,
    )

    canonical_name = models.CharField(
        "Единое название",
        max_length=255,
    )

    image = models.ImageField(
        "Сжатое фото",
        upload_to="hotels/",
        blank=True,
    )

    image_source_url = models.URLField(
        "Прямая ссылка на исходное фото",
        max_length=1000,
        blank=True,
    )

    image_page_url = models.URLField(
        "Страница — источник фото",
        max_length=1000,
        blank=True,
    )

    active = models.BooleanField(
        "Активен",
        default=True,
    )

    class Meta:
        verbose_name = "Отель"
        verbose_name_plural = "Отели"
        ordering = ("canonical_name",)
        constraints = [
            models.UniqueConstraint(
                fields=("country", "canonical_name"),
                name="uniq_hotel_country_name",
            )
        ]

    def __str__(self):
        return self.canonical_name


class SourceHotel(models.Model):
    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="source_hotels",
        verbose_name="Источник",
    )

    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_names",
        verbose_name="Единый отель",
    )

    source_name = models.CharField(
        "Название на сайте",
        max_length=255,
    )

    source_code = models.CharField(
        "ID на сайте",
        max_length=255,
        blank=True,
    )

    detail_url = models.URLField(
        "Страница отеля у источника",
        max_length=1000,
        blank=True,
    )

    image_url = models.URLField(
        "Фото отеля у источника",
        max_length=1000,
        blank=True,
    )

    match_status = models.CharField(
        "Статус сопоставления",
        max_length=20,
        choices=MatchStatus.choices,
        default=MatchStatus.REVIEW,
    )

    active = models.BooleanField(
        "Активен",
        default=True,
    )

    class Meta:
        verbose_name = "Название отеля у источника"
        verbose_name_plural = "Названия отелей у источников"
        ordering = ("source__name", "source_name")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "source_name"),
                name="uniq_source_hotel_name",
            )
        ]
        indexes = [
            models.Index(
                fields=("source", "active", "match_status"),
                name="src_hotel_status_idx",
            ),
            models.Index(
                fields=("hotel", "source"),
                name="src_hotel_match_idx",
            ),
        ]

    def __str__(self):
        return f"{self.source}: {self.source_name}"


class RoomCategory(models.Model):
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name="room_categories",
        verbose_name="Отель",
    )

    canonical_name = models.CharField(
        "Единое название категории",
        max_length=255,
    )

    active = models.BooleanField(
        "Активна",
        default=True,
    )

    class Meta:
        verbose_name = "Категория номера"
        verbose_name_plural = "Категории номеров"
        ordering = (
            "hotel__canonical_name",
            "canonical_name",
        )
        constraints = [
            models.UniqueConstraint(
                fields=("hotel", "canonical_name"),
                name="uniq_room_per_hotel",
            )
        ]

    def __str__(self):
        return f"{self.hotel} — {self.canonical_name}"


class SourceRoomCategory(models.Model):
    source_hotel = models.ForeignKey(
        SourceHotel,
        on_delete=models.CASCADE,
        related_name="source_rooms",
        verbose_name="Отель у источника",
    )

    room_category = models.ForeignKey(
        RoomCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_names",
        verbose_name="Единая категория",
    )

    source_name = models.CharField(
        "Название категории на сайте",
        max_length=255,
    )

    source_code = models.CharField(
        "ID категории на сайте",
        max_length=255,
        blank=True,
    )

    match_status = models.CharField(
        "Статус сопоставления",
        max_length=20,
        choices=MatchStatus.choices,
        default=MatchStatus.REVIEW,
    )

    class Meta:
        verbose_name = "Категория номера у источника"
        verbose_name_plural = "Категории номеров у источников"
        ordering = (
            "source_hotel__source__name",
            "source_name",
        )
        constraints = [
            models.UniqueConstraint(
                fields=("source_hotel", "source_name"),
                name="uniq_source_room_name",
            )
        ]
        indexes = [
            models.Index(
                fields=("source_hotel", "match_status"),
                name="src_room_status_idx",
            ),
            models.Index(
                fields=("room_category",),
                name="src_room_match_idx",
            ),
        ]

    def __str__(self):
        return f"{self.source_hotel} — {self.source_name}"


class MealPlan(models.Model):
    code = models.CharField(
        "Код",
        max_length=20,
        unique=True,
    )

    name = models.CharField(
        "Название",
        max_length=150,
    )

    class Meta:
        verbose_name = "Тип питания"
        verbose_name_plural = "Типы питания"
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} — {self.name}"
