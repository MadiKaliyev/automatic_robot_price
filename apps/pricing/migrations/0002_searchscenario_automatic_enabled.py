from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="searchscenario",
            name="automatic_enabled",
            field=models.BooleanField(
                default=False,
                verbose_name="Запускать автоматически",
            ),
        ),
    ]

