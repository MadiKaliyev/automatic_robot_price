# Maldives Bonus

Интеграция находится в общей структуре проекта:

- `apps/integrations/adapters/maldives_bonus.py` — загрузка и нормализация каталога;
- `apps/pricing/management/commands/collect_maldives_bonus.py` — запуск сбора и сохранение отелей;
- `apps/pricing/tests/test_maldives_bonus.py` — тесты парсера.

Запуск:

```powershell
python manage.py collect_maldives_bonus
```

Чтобы дополнительно выгрузить полные карточки (ссылки, курорт, координаты и
фотографии) в JSON:

```powershell
python manage.py collect_maldives_bonus --output reports_output/maldives_bonus_hotels.json
```

Maldives Bonus не публикует цену в открытом каталоге. Поэтому адаптер возвращает
общий формат данных с `price = None`, команда сохраняет отели в единый каталог,
но не создаёт записей `PriceOffer` и не подменяет отсутствующую цену значением 0.
