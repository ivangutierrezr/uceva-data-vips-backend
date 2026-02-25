from __future__ import annotations

from typing import Iterable

from django.db.models import QuerySet

from .csv_io import write_csv


def export_articles_queryset(queryset: QuerySet, filename: str) -> None:
    model = queryset.model
    field_names = [field.name for field in model._meta.fields]
    headers = [*field_names, "author_names", "group_name", "country_name"]

    def iter_rows() -> Iterable[list[object]]:
        for obj in queryset.iterator():
            row: list[object] = [getattr(obj, field) for field in field_names]
            row.append(", ".join(a.author_name for a in obj.authors.all()))
            row.append(obj.group.name if obj.group else "")
            row.append(obj.country.name if obj.country else "")
            yield row

    write_csv(filename, headers, iter_rows())


def main() -> None:
    from .django_setup import setup_django

    setup_django()
    from scienti.models import Article

    all_articles = Article.objects.all().order_by("year")
    export_articles_queryset(all_articles, "export_articles_cleaned.csv")

    no_year = Article.objects.filter(year__isnull=True)
    if no_year.exists():
        export_articles_queryset(no_year, "export_articles_no_year.csv")

    future = Article.objects.filter(year__gt=2026)
    if future.exists():
        export_articles_queryset(future, "export_articles_future_err.csv")


if __name__ == "__main__":
    main()
