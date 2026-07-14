# Island Price Monitor

Django-приложение для мониторинга и точного сравнения цен на отели Сейшел у туроператоров. Система сопоставляет только предложения с одинаковыми отелем, категорией номера, питанием, датами, составом гостей, трансфером, налогами и составом итоговой цены.

## Возможности

- сбор цен Resort Holiday и «Мальдивианы» через браузерные адаптеры;
- Maldives Bonus как справочник отелей, ссылок и фотографий — без создания фиктивных цен;
- ручное сопоставление названий отелей и категорий номеров в Django Admin;
- автоматическая загрузка фотографии только при отсутствии фото в локальной БД;
- история запусков и цен, лучшая цена, разница в валюте и процентах;
- цветовое выделение результатов и прямые ссылки на заполненный поиск источника;
- Excel- и PDF-отчёты;
- ручной запуск и запуск по расписанию через Celery Beat;
- адаптивная страница результатов, метаданные Open Graph, JSON-LD, `robots.txt` и `sitemap.xml`.

## Быстрый старт на Windows

Требуется Python 3.10+; для браузерных сборщиков также устанавливается Chromium от Playwright.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_initial_data
python manage.py createsuperuser
python manage.py runserver
```

Интерфейс: <http://127.0.0.1:8000/>  
Администрирование: <http://127.0.0.1:8000/admin/>

## Сбор и сравнение

```powershell
# Полный цикл для сценария: справочник, две цены, сравнение и отчёты
python manage.py run_monitoring_cycle --scenario-id 5

# Отдельные этапы
python manage.py collect_maldives_bonus
python manage.py collect_maldiviana --scenario-id 5
python manage.py collect_resort --scenario-id 5
python manage.py build_comparisons --run-id 10
```

Maldives Bonus намеренно не участвует в сравнении цен: источник используется для карточек отелей и фотографий. Если у отеля уже есть локальное изображение, загрузчик его не перезаписывает.

## Автоматический запуск

Включите у сценария флаг «Запускать автоматически», запустите Redis, worker и планировщик:

```powershell
celery -A tour_monitor worker -l info -P solo
celery -A tour_monitor beat -l info
```

Период задаётся переменной `MONITORING_INTERVAL_MINUTES` (60 минут по умолчанию).

## Проверка качества

```powershell
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py check
python manage.py collectstatic --noinput
```

## Развёртывание

Локально используется SQLite. Для постоянного сервера рекомендуется PostgreSQL через `DATABASE_URL`, Redis, HTTPS и отдельное файловое или объектное хранилище для `media/`. Встроенный `runserver` не предназначен для публичной эксплуатации; пример запуска через Waitress приведён в [руководстве по развёртыванию](docs/DEPLOYMENT.md).

## Документация

- [Описание решения, источники, сроки, стоимость и риски](docs/SOLUTION_OVERVIEW.md)
- [Статус требований 1–24](docs/REQUIREMENTS_STATUS.md)
- [Развёртывание](docs/DEPLOYMENT.md)
- [Данные, необходимые для проверки](docs/DATA_REQUIRED.md)
- [Роль Maldives Bonus](docs/MALDIVES_BONUS.md)

Секреты, локальная база, загруженные фотографии и сформированные отчёты не хранятся в Git.
