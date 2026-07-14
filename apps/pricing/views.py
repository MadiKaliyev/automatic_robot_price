from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.management import call_command
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET, require_safe

from apps.pricing.models import CollectionRun, ComparisonGroup, ComparisonItem

HISTORY_LIMIT = 20
SEO_TITLE = "Сравнение цен на отели Сейшел — Island Price Monitor"
SEO_DESCRIPTION = (
    "Сравнение актуальных цен Resort Holiday и Мальдивианы на одинаковые "
    "отели и категории номеров Сейшел. История цен, экономия, Excel и PDF."
)


def describe_price_components(offer) -> str:
    components = (
        offer.included_components if isinstance(offer.included_components, dict) else {}
    )
    values = [
        "проживание" if components.get("hotel", True) else "без проживания",
        "перелёт включён" if components.get("flight", False) else "без перелёта",
        "трансфер включён" if offer.transfer_included else "без трансфера",
        "налоги включены" if offer.taxes_included else "налоги не включены",
    ]
    return ", ".join(values)


def _get_recent_run_rows() -> list[dict]:
    return list(
        ComparisonGroup.objects.values("run_id")
        .annotate(group_count=Count("id"))
        .order_by("-run_id")[:HISTORY_LIMIT]
    )


def _get_current_run_id(request, recent_run_ids: list[int]) -> int | None:
    requested_run_id = request.GET.get("run")
    if not requested_run_id:
        return recent_run_ids[0] if recent_run_ids else None

    try:
        run_id = int(requested_run_id)
    except ValueError as error:
        raise Http404("Некорректный ID запуска.") from error

    if not ComparisonGroup.objects.filter(run_id=run_id).exists():
        raise Http404("Запуск сравнения не найден.")
    return run_id


def _build_history(run_rows: list[dict]) -> list[dict]:
    run_ids = [row["run_id"] for row in run_rows]
    runs = CollectionRun.objects.filter(id__in=run_ids).select_related("scenario")
    runs_by_id = {run.id: run for run in runs}
    return [
        {
            "run": runs_by_id[row["run_id"]],
            "group_count": row["group_count"],
        }
        for row in run_rows
        if row["run_id"] in runs_by_id
    ]


def _load_comparison(run_id: int) -> tuple[CollectionRun, list, list]:
    current_run = CollectionRun.objects.select_related("scenario").get(id=run_id)
    groups = list(
        ComparisonGroup.objects.filter(run_id=run_id)
        .select_related(
            "hotel",
            "room_category",
            "meal_plan",
            "best_offer__source",
        )
        .order_by(
            "hotel__canonical_name",
            "room_category__canonical_name",
            "meal_plan__code",
        )
    )
    group_ids = [group.id for group in groups]
    items = list(
        ComparisonItem.objects.filter(group_id__in=group_ids)
        .select_related(
            "offer__source",
            "offer__source_room",
        )
        .order_by("group_id", "offer__price")
    )

    items_by_group = defaultdict(list)
    for item in items:
        item.price_components_text = describe_price_components(item.offer)
        items_by_group[item.group_id].append(item)

    for group in groups:
        group.dashboard_items = items_by_group.get(group.id, [])
        group.maximum_difference = max(
            (item.absolute_difference for item in group.dashboard_items),
            default=Decimal("0.00"),
        )
        group.maximum_percent = max(
            (item.percent_difference for item in group.dashboard_items),
            default=Decimal("0.00"),
        )
    return current_run, groups, items


def _build_summary(groups: list) -> dict:
    summary = {
        "maldiviana_wins": 0,
        "resort_wins": 0,
        "maximum_saving": Decimal("0.00"),
        "maximum_percent": Decimal("0.00"),
    }
    for group in groups:
        summary["maximum_saving"] = max(
            summary["maximum_saving"],
            group.maximum_difference,
        )
        summary["maximum_percent"] = max(
            summary["maximum_percent"],
            group.maximum_percent,
        )
        source_name = group.best_offer.source.name
        if source_name == "Мальдивиана":
            summary["maldiviana_wins"] += 1
        elif source_name == "Resort Holiday":
            summary["resort_wins"] += 1
    return summary


@require_safe
@cache_control(public=True, max_age=60, stale_while_revalidate=30)
def dashboard(request):
    run_rows = _get_recent_run_rows()
    recent_run_ids = [row["run_id"] for row in run_rows]
    current_run_id = _get_current_run_id(request, recent_run_ids)
    history = _build_history(run_rows)

    current_run = None
    groups = []
    items = []
    if current_run_id is not None:
        current_run, groups, items = _load_comparison(current_run_id)

    canonical_url = request.build_absolute_uri(reverse("pricing:dashboard"))
    context = {
        "current_run": current_run,
        "groups": groups,
        "history": history,
        "total_groups": len(groups),
        "total_items": len(items),
        "seo_title": SEO_TITLE,
        "seo_description": SEO_DESCRIPTION,
        "seo_canonical_url": canonical_url,
        "seo_image_url": request.build_absolute_uri(
            static("pricing/images/island-1.jpg")
        ),
        **_build_summary(groups),
    }
    return render(request, "pricing/dashboard.html", context)


def _download_report(run_id: int, extension: str, command_name: str) -> FileResponse:
    if not ComparisonGroup.objects.filter(run_id=run_id).exists():
        raise Http404("Запуск сравнения не найден.")

    filename = f"comparison_run_{run_id}.{extension}"
    output_path = Path(settings.BASE_DIR) / "reports_output" / filename
    if not output_path.exists() or output_path.stat().st_size == 0:
        call_command(
            command_name,
            run_id=run_id,
            output=str(output_path),
        )

    response = FileResponse(
        output_path.open("rb"),
        as_attachment=True,
        filename=filename,
    )
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@require_GET
def download_excel(request, run_id):
    return _download_report(run_id, "xlsx", "export_comparison_excel")


@require_GET
def download_pdf(request, run_id):
    return _download_report(run_id, "pdf", "export_comparison_pdf")


@require_safe
@cache_control(public=True, max_age=3600)
def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("pricing:sitemap"))
    content = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /reports/",
            f"Sitemap: {sitemap_url}",
            "",
        ]
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


@require_safe
@cache_control(public=True, max_age=3600)
def sitemap_xml(request):
    dashboard_url = escape(request.build_absolute_uri(reverse("pricing:dashboard")))
    last_modified = (
        ComparisonGroup.objects.order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    lastmod = (
        f"<lastmod>{last_modified.date().isoformat()}</lastmod>"
        if last_modified
        else ""
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{dashboard_url}</loc>{lastmod}"
        "<changefreq>daily</changefreq><priority>1.0</priority></url>"
        "</urlset>"
    )
    return HttpResponse(content, content_type="application/xml; charset=utf-8")
