from django.urls import path

from apps.pricing import views

app_name = "pricing"


urlpatterns = [
    path(
        "",
        views.dashboard,
        name="dashboard",
    ),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap"),
    path(
        "reports/<int:run_id>/excel/",
        views.download_excel,
        name="download_excel",
    ),
    path(
        "reports/<int:run_id>/pdf/",
        views.download_pdf,
        name="download_pdf",
    ),
]
