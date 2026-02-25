from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db import connection

from .csv_io import write_csv


@dataclass(frozen=True)
class SqlExport:
    filename: str
    query: str


def export_sql_to_csv(query: str, filename: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    write_csv(filename, columns, rows)
    return len(rows)


def get_default_exports() -> list[SqlExport]:
    return [
        SqlExport(
            filename="view_articles.csv",
            query="""
                SELECT 
                    a.title AS article_title,
                    a.year AS publication_year,
                    a.doi,
                    a.issn,
                    a.product_type,
                    rg.name AS group_name,
                    rg.code AS group_code,
                    j.name AS journal_name,
                    c.name AS city_name,
                    co.name AS country_name
                FROM scienti_article a
                LEFT JOIN scienti_research_group rg ON a.group_id = rg.id
                LEFT JOIN scienti_journal j ON a.journal_id = j.id
                LEFT JOIN scienti_city c ON a.city_id = c.id
                LEFT JOIN scienti_country co ON a.country_id = co.id;
            """,
        ),
        SqlExport(
            filename="view_article_authors.csv",
            query="""
                SELECT 
                    a.title AS article_title,
                    aa.author_name,
                    aa.order AS author_order,
                    CASE 
                        WHEN aa.is_group_member = true THEN 'YES' 
                        ELSE 'NO' 
                    END AS is_group_member,
                    rg.name AS group_name,
                    rg.code AS group_code
                FROM scienti_article_author aa
                JOIN scienti_article a ON aa.article_id = a.id
                LEFT JOIN scienti_research_group rg ON a.group_id = rg.id;
            """,
        ),
        SqlExport(
            filename="view_books.csv",
            query="""
                SELECT 
                    b.title AS book_title,
                    b.isbn,
                    b.year AS publication_year,
                    b.product_type,
                    rg.name AS group_name,
                    rg.code AS group_code,
                    p.name AS publisher_name,
                    c.name AS city_name,
                    co.name AS country_name
                FROM scienti_book b
                LEFT JOIN scienti_research_group rg ON b.group_id = rg.id
                LEFT JOIN scienti_publisher p ON b.publisher_id = p.id
                LEFT JOIN scienti_city c ON b.city_id = c.id
                LEFT JOIN scienti_country co ON b.country_id = co.id;
            """,
        ),
        SqlExport(
            filename="view_book_authors.csv",
            query="""
                SELECT 
                    b.title AS book_title,
                    ba.author_name,
                    ba.order AS author_order,
                    CASE 
                        WHEN ba.is_group_member = true THEN 'YES' 
                        ELSE 'NO' 
                    END AS is_group_member,
                    rg.name AS group_name,
                    rg.code AS group_code
                FROM scienti_book_author ba
                JOIN scienti_book b ON ba.book_id = b.id
                LEFT JOIN scienti_research_group rg ON b.group_id = rg.id;
            """,
        ),
        SqlExport(
            filename="view_chapters.csv",
            query="""
                SELECT 
                    bc.chapter_title,
                    bc.book_title,
                    bc.isbn,
                    bc.year AS publication_year,
                    bc.product_type,
                    rg.name AS group_name,
                    rg.code AS group_code,
                    p.name AS publisher_name
                FROM scienti_book_chapter bc
                LEFT JOIN scienti_research_group rg ON bc.group_id = rg.id
                LEFT JOIN scienti_publisher p ON bc.publisher_id = p.id;
            """,
        ),
        SqlExport(
            filename="view_chapter_authors.csv",
            query="""
                SELECT 
                    bc.chapter_title,
                    bc.book_title,
                    ca.author_name,
                    ca.order AS author_order,
                    CASE 
                        WHEN ca.is_group_member = true THEN 'YES' 
                        ELSE 'NO' 
                    END AS is_group_member,
                    rg.name AS group_name,
                    rg.code AS group_code
                FROM scienti_chapter_author ca
                JOIN scienti_book_chapter bc ON ca.chapter_id = bc.id
                LEFT JOIN scienti_research_group rg ON bc.group_id = rg.id;
            """,
        ),
        SqlExport(
            filename="view_theses.csv",
            query="""
                SELECT 
                    t.title AS thesis_title,
                    t.period AS full_period_text,
                    t.start_date,
                    t.end_date,
                    t.year AS defense_year,
                    t.guidance_type,
                    t.academic_program,
                    t.institution,
                    t.grade,
                    pt.name AS thesis_type_name,
                    rg.name AS group_name,
                    rg.code AS group_code
                FROM scienti_thesis t
                LEFT JOIN scienti_research_group rg ON t.group_id = rg.id
                LEFT JOIN scienti_product_type pt ON t.thesis_type_obj_id = pt.id;
            """,
        ),
        SqlExport(
            filename="view_thesis_tutors.csv",
            query="""
                SELECT 
                    t.title AS thesis_title,
                    tt.tutor_name,
                    rg.name AS group_name,
                    rg.code AS group_code
                FROM scienti_thesis_tutor tt
                JOIN scienti_thesis t ON tt.thesis_id = t.id
                LEFT JOIN scienti_research_group rg ON t.group_id = rg.id;
            """,
        ),
        SqlExport(
            filename="view_thesis_students.csv",
            query="""
                SELECT 
                    t.title AS thesis_title,
                    ts.student_name,
                    t.academic_program,
                    rg.name AS group_name,
                    rg.code AS group_code
                FROM scienti_thesis_student ts
                JOIN scienti_thesis t ON ts.thesis_id = t.id
                LEFT JOIN scienti_research_group rg ON t.group_id = rg.id;
            """,
        ),
        SqlExport(
            filename="view_article_categories_history.csv",
            query="""
                SELECT 
                    a.issn,
                    a.title AS article_title,
                    acs.name AS source_name,
                    ac.year AS category_classification_year,
                    ac.category AS category_value
                FROM scienti_article_category ac
                JOIN scienti_article_category_source acs ON ac.source_id = acs.id
                JOIN scienti_article a ON ac.article_id = a.id;
            """,
        ),
        SqlExport(
            filename="view_scientific_events.csv",
            query="""
            SELECT 
                e.hash_id AS id_evento,
                e.title AS nombre_evento,
                e.event_type AS tipo_evento,
                e.city AS ciudad,
                e.start_date AS fecha_inicio,
                e.end_date AS fecha_fin,
                e.scope AS ambito,
                e.participation_type AS tipo_participacion,
                rg.name AS nombre_grupo,
                rg.code AS codigo_grupo
            FROM scienti_scientific_event e
            LEFT JOIN scienti_research_group rg ON e.group_id = rg.id;
            """,
        ),
        SqlExport(
            filename="view_event_institutions.csv",
            query="""
            SELECT 
                e.hash_id AS id_evento,
                e.title AS nombre_evento,
                i.institution_name AS nombre_institucion,
                i.relationship_type AS tipo_vinculacion
            FROM scienti_event_institution i
            JOIN scienti_scientific_event e ON i.event_id = e.id;
            """,
        ),
    ]


def main() -> None:
    from .django_setup import setup_django

    setup_django()

    for export in get_default_exports():
        export_sql_to_csv(export.query, export.filename)


if __name__ == "__main__":
    main()
