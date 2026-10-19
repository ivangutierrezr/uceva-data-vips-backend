from __future__ import annotations

import csv
from typing import Iterable

from django.db.models import Count
from django.db.models.functions import ExtractYear


def write_csv_dicts(filename: str, fieldnames: list[str], rows: Iterable[dict]) -> None:
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(list(rows))


def analyze_duplicates() -> list[str]:
    from scienti.models import Article, Book, BookChapter, Thesis, ScientificEvent

    reports: list[str] = []

    duplicates = (
        Article.objects.values("title", "year")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .order_by("-count")
    )
    articles_data: list[dict] = []
    for d in duplicates:
        instances = Article.objects.filter(title=d["title"], year=d["year"]).select_related("group")
        groups = [inst.group.name for inst in instances]
        articles_data.append(
            {"Titulo": d["title"], "Año": d["year"], "Repeticiones": d["count"], "Grupos": "; ".join(groups)}
        )
    if articles_data:
        write_csv_dicts("duplicados_articulos.csv", ["Titulo", "Año", "Repeticiones", "Grupos"], articles_data)
        reports.append(f"Artículos duplicados encontrados: {len(articles_data)}")
    else:
        reports.append("No se encontraron artículos duplicados.")

    duplicates = Book.objects.values("title", "year").annotate(count=Count("id")).filter(count__gt=1).order_by("-count")
    books_data: list[dict] = []
    for d in duplicates:
        instances = Book.objects.filter(title=d["title"], year=d["year"]).select_related("group")
        groups = [inst.group.name for inst in instances]
        books_data.append(
            {"Titulo": d["title"], "Año": d["year"], "Repeticiones": d["count"], "Grupos": "; ".join(groups)}
        )
    if books_data:
        write_csv_dicts("duplicados_libros.csv", ["Titulo", "Año", "Repeticiones", "Grupos"], books_data)
        reports.append(f"Libros duplicados encontrados: {len(books_data)}")
    else:
        reports.append("No se encontraron libros duplicados.")

    duplicates = (
        BookChapter.objects.values("chapter_title", "book_title", "year")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .order_by("-count")
    )
    chapters_data: list[dict] = []
    for d in duplicates:
        instances = BookChapter.objects.filter(
            chapter_title=d["chapter_title"], book_title=d["book_title"], year=d["year"]
        ).select_related("group")
        groups = [inst.group.name for inst in instances]
        chapters_data.append(
            {
                "Capitulo": d["chapter_title"],
                "Libro": d["book_title"],
                "Año": d["year"],
                "Repeticiones": d["count"],
                "Grupos": "; ".join(groups),
            }
        )
    if chapters_data:
        write_csv_dicts("duplicados_capitulos.csv", ["Capitulo", "Libro", "Año", "Repeticiones", "Grupos"], chapters_data)
        reports.append(f"Capítulos duplicados encontrados: {len(chapters_data)}")
    else:
        reports.append("No se encontraron capítulos duplicados.")

    duplicates = Thesis.objects.values("title", "year").annotate(count=Count("id")).filter(count__gt=1).order_by("-count")
    theses_data: list[dict] = []
    for d in duplicates:
        instances = Thesis.objects.filter(title=d["title"], year=d["year"]).select_related("group")
        groups = [inst.group.name for inst in instances]
        theses_data.append(
            {"Titulo": d["title"], "Año": d["year"], "Repeticiones": d["count"], "Grupos": "; ".join(groups)}
        )
    if theses_data:
        write_csv_dicts("duplicados_tesis.csv", ["Titulo", "Año", "Repeticiones", "Grupos"], theses_data)
        reports.append(f"Tesis duplicadas encontradas: {len(theses_data)}")
    else:
        reports.append("No se encontraron tesis duplicadas.")

    duplicates = (
        ScientificEvent.objects.annotate(event_year=ExtractYear("start_date"))
        .values("title", "event_year")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .order_by("-count")
    )
    events_data: list[dict] = []
    for d in duplicates:
        instances = (
            ScientificEvent.objects.annotate(event_year=ExtractYear("start_date"))
            .filter(title=d["title"], event_year=d["event_year"])
            .select_related("group")
        )
        groups = [inst.group.name for inst in instances]
        events_data.append({"Evento": d["title"], "Año": d["event_year"], "Repeticiones": d["count"], "Grupos": "; ".join(groups)})
    if events_data:
        write_csv_dicts("duplicados_eventos.csv", ["Evento", "Año", "Repeticiones", "Grupos"], events_data)
        reports.append(f"Eventos duplicados encontrados: {len(events_data)}")
    else:
        reports.append("No se encontraron eventos duplicados.")

    return reports


