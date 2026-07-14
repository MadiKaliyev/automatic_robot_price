from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_hotel_image_hotel_image_page_url_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="sourcehotel",
            index=models.Index(
                fields=["source", "active", "match_status"],
                name="src_hotel_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="sourcehotel",
            index=models.Index(
                fields=["hotel", "source"],
                name="src_hotel_match_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="sourceroomcategory",
            index=models.Index(
                fields=["source_hotel", "match_status"],
                name="src_room_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="sourceroomcategory",
            index=models.Index(
                fields=["room_category"],
                name="src_room_match_idx",
            ),
        ),
    ]

