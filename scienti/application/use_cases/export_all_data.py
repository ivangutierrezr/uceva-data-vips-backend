from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Iterable

from django.db.models.functions import ExtractYear


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", "").strip()


def join_list(values: Iterable[object]) -> str:
    return "; ".join(clean_text(v) for v in values if clean_text(v))


def export_all_data() -> None:
    from scienti.models import (
        Article,
        Book,
        BookChapter,
        Thesis,
        ScientificEvent,
        ArticleAuthor,
        BookAuthor,
        ChapterAuthor,
    )

    articles = (
        Article.objects.select_related("group", "journal", "country", "city")
        .all()
        .order_by("-year", "title")
    )
    with open("export_articulos_completo.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Titulo", "Año", "DOI", "ISSN", "Revista", "Grupo", "Pais", "Ciudad", "Autores"])
        for article in articles:
            authors = ArticleAuthor.objects.filter(article=article).values_list("author_name", flat=True)
            writer.writerow(
                [
                    article.id,
                    clean_text(article.title),
                    article.year,
                    clean_text(article.doi),
                    clean_text(article.issn),
                    clean_text(article.journal.name) if article.journal else "",
                    clean_text(article.group.name),
                    clean_text(article.country.name) if article.country else "",
                    clean_text(article.city.name) if article.city else "",
                    join_list(authors),
                ]
            )

    books = (
        Book.objects.select_related("group", "publisher", "country", "city")
        .all()
        .order_by("-year", "title")
    )
    with open("export_libros_completo.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Titulo", "Año", "ISBN", "Editorial", "Grupo", "Pais", "Ciudad", "Autores"])
        for book in books:
            authors = BookAuthor.objects.filter(book=book).values_list("author_name", flat=True)
            writer.writerow(
                [
                    book.id,
                    clean_text(book.title),
                    book.year,
                    clean_text(book.isbn),
                    clean_text(book.publisher.name) if book.publisher else "",
                    clean_text(book.group.name),
                    clean_text(book.country.name) if book.country else "",
                    clean_text(book.city.name) if book.city else "",
                    join_list(authors),
                ]
            )

    chapters = BookChapter.objects.select_related("group", "publisher").all().order_by("-year", "chapter_title")
    with open("export_capitulos_completo.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Capitulo", "Libro", "Año", "ISBN", "Editorial", "Grupo", "Autores"])
        for chapter in chapters:
            authors = ChapterAuthor.objects.filter(chapter=chapter).values_list("author_name", flat=True)
            writer.writerow(
                [
                    chapter.id,
                    clean_text(chapter.chapter_title),
                    clean_text(chapter.book_title),
                    chapter.year,
                    clean_text(chapter.isbn),
                    clean_text(chapter.publisher.name) if chapter.publisher else "",
                    clean_text(chapter.group.name),
                    join_list(authors),
                ]
            )

    theses = (
        Thesis.objects.select_related("group", "institution_obj", "thesis_type_obj")
        .all()
        .order_by("-year", "title")
    )
    with open("export_tesis_completo.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Titulo", "Año", "Tipo", "Institucion", "Grupo", "Estudiantes", "Tutores"])
        for thesis in theses:
            students = thesis.students.all().values_list("student_name", flat=True)
            tutors = thesis.tutors.all().values_list("tutor_name", flat=True)
            writer.writerow(
                [
                    thesis.id,
                    clean_text(thesis.title),
                    thesis.year,
                    clean_text(thesis.thesis_type_obj.name) if thesis.thesis_type_obj else clean_text(thesis.thesis_type),
                    clean_text(thesis.institution_obj.name) if thesis.institution_obj else clean_text(thesis.institution),
                    clean_text(thesis.group.name),
                    join_list(students),
                    join_list(tutors),
                ]
            )

    events = (
        ScientificEvent.objects.annotate(event_year=ExtractYear("start_date"))
        .select_related("group", "country_obj", "city_obj")
        .all()
        .order_by("-event_year", "title")
    )
    with open("export_eventos_completo.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Evento", "Año", "Tipo", "Ambito", "Participacion", "Lugar", "Grupo"])
        for event in events:
            place_parts: list[str] = []
            if event.city_obj:
                place_parts.append(event.city_obj.name)
            elif event.city:
                place_parts.append(event.city)
            if event.country_obj:
                place_parts.append(event.country_obj.name)
            place = ", ".join(place_parts)

            writer.writerow(
                [
                    event.id,
                    clean_text(event.title),
                    event.event_year,
                    clean_text(event.event_type),
                    clean_text(event.scope),
                    clean_text(event.participation_type),
                    clean_text(place),
                    clean_text(event.group.name),
                ]
            )


