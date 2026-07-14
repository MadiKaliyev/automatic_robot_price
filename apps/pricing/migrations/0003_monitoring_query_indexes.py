from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0002_searchscenario_automatic_enabled"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="searchscenario",
            index=models.Index(
                fields=["active", "automatic_enabled"],
                name="scenario_schedule_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="collectionrun",
            index=models.Index(
                fields=["status", "started_at"],
                name="run_status_started_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="priceoffer",
            index=models.Index(
                fields=["source", "check_in", "nights", "adults", "currency"],
                name="offer_latest_source_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="priceoffer",
            index=models.Index(
                fields=[
                    "hotel",
                    "room_category",
                    "meal_plan",
                    "check_in",
                    "nights",
                ],
                name="offer_match_params_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="comparisongroup",
            index=models.Index(
                fields=["run", "hotel"],
                name="comparison_run_hotel_idx",
            ),
        ),
    ]

